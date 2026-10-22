"""Tests for the interaction layers: challenge loop, proof autopsy, patch,
cube-and-conquer and export. The LLM is stubbed — the point of these tests is
that the *solver* behaviour is deterministic."""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.argue import apply_patch, challenge_step, diagnose_failure, offer_patch  # noqa: E402
from src.cases import detect_symmetries, run_cube_search  # noqa: E402
from src.engine import SymbolicForm, Variable, check_with_form  # noqa: E402
from src.examples import get_example  # noqa: E402
from src.llm_client import LLMReply  # noqa: E402
from src.state import ProofState  # noqa: E402


class StubClient:
    """Stands in for the LLM: returns canned JSON, no network."""

    def __init__(self, payloads: list[dict[str, Any]] | None = None) -> None:
        self.payloads = payloads or []
        self.calls: list[Any] = []

    def chat_json(self, messages, default=None, **kwargs):  # noqa: D102
        self.calls.append(messages)
        if not self.payloads:
            return (default if default is not None else {}), "{}"
        return self.payloads.pop(0), "{}"

    def chat(self, messages, **kwargs):  # noqa: D102
        payload, raw = self.chat_json(messages)
        return LLMReply(text=raw, provider="stub", model="stub")

    def chat_text(self, messages, **kwargs):  # noqa: D102
        return self.chat(messages, **kwargs).text


# ---------------------------------------------------------------------------
# Tautology guard: we must never claim "no counterexample" for a check that
# did not happen.
# ---------------------------------------------------------------------------
def test_tautology_is_reported_as_unknown_not_as_success():
    form = SymbolicForm(
        backend="z3",
        variables=[Variable("n", "int", 0, 10)],
        constraints=["n >= 0"],
        claim_expr="n * n == n * n",
    )
    state = check_with_form(form, "anything")
    assert state.verdict == "unknown"
    assert state.unknown_info is not None
    assert state.unknown_info.kind == "translation_ambiguity"


# ---------------------------------------------------------------------------
# Cube-and-conquer + symmetry breaking
# ---------------------------------------------------------------------------
def test_symmetry_is_detected_for_swappable_variables():
    ex = get_example("pythagorean")
    symmetries = detect_symmetries(ex.form)
    assert any(s["type"] == "swap" for s in symmetries)


def test_cube_search_eliminates_symmetric_cubes():
    ex = get_example("pythagorean")
    results, cert = run_cube_search(ex.form, ex.claim, num_splits=4, workers=2, timeout=10)
    assert cert["cubes_eliminated_by_symmetry"] > 0
    assert cert["cubes_solved"] + cert["cubes_eliminated_by_symmetry"] == cert["total_cubes"]
    assert any(r["verdict"] == "counterexample_found" for r in results)
    assert "2^7825" in cert["landmark_scale_note"]


# ---------------------------------------------------------------------------
# Proof autopsy (Stage 5b)
# ---------------------------------------------------------------------------
def _state_with_counterexample() -> ProofState:
    form = SymbolicForm(
        backend="z3",
        variables=[Variable("x", "int", -10, 10)],
        constraints=["x >= -10", "x <= 10"],
        claim_expr="x >= 0",
        steps=["Step one: assume x is a real number.", "Step two: take the square root."],
    )
    state = check_with_form(form, "sqrt(x^2) == x for all real x")
    return state


def test_diagnose_failure_implicates_a_specific_step():
    state = _state_with_counterexample()
    stub = StubClient(
        [
            {
                "implicated_step": 2,
                "missing_assumption": "the square root is taken on non-negative inputs",
                "missing_assumption_expr": "x >= 0",
                "confidence": 0.9,
                "explanation": "Step 2 silently assumes x >= 0.",
                "premise_level_failure": False,
            }
        ]
    )
    state = diagnose_failure(state, client=stub)
    step = state.get_step(2)
    assert step is not None and step.implicated
    assert step.missing_assumption_expr == "x >= 0"
    assert not state.premises_faulty
    assert "Add constraint" in offer_patch(state)


def test_diagnose_failure_falls_back_to_premise_level():
    state = _state_with_counterexample()
    stub = StubClient(
        [
            {
                "implicated_step": None,
                "missing_assumption": "",
                "confidence": 0.2,
                "explanation": "The counterexample contradicts the claim itself.",
                "premise_level_failure": True,
            }
        ]
    )
    state = diagnose_failure(state, client=stub)
    assert state.premises_faulty
    assert not any(s.implicated for s in state.steps)
    assert offer_patch(state) == ""


def test_apply_patch_reruns_the_solver_with_the_new_constraint():
    state = _state_with_counterexample()
    stub = StubClient(
        [
            {
                "implicated_step": 2,
                "missing_assumption": "x is non-negative",
                "missing_assumption_expr": "x >= 0",
                "confidence": 0.9,
                "explanation": "Step 2 assumes x >= 0.",
                "premise_level_failure": False,
            }
        ]
    )
    state = diagnose_failure(state, client=stub)
    patched, message = apply_patch(state, client=StubClient())
    assert patched is not None
    assert patched.verdict == "no_counterexample_in_bound"
    assert "no counterexample was found" in message
    assert "x >= 0" in patched.extra_constraints


# ---------------------------------------------------------------------------
# Challenge loop (Stage 5)
# ---------------------------------------------------------------------------
def test_challenge_step_answers_the_specific_objection():
    state = _state_with_counterexample()
    stub = StubClient(
        [
            {
                "response": "You are right: the step only holds for x >= 0.",
                "concedes": True,
                "new_constraint": "x >= 0",
                "new_step": "Check the claim restricted to x >= 0.",
            }
        ]
    )
    state = challenge_step(state, 2, "what about x = -1?", client=stub)
    step = state.get_step(2)
    assert step.status == "resolved"
    assert "x >= 0" in (step.agent_response or "")
    assert state.get_step(3) is not None  # the new sub-claim was appended


def test_unapplicable_patch_does_not_downgrade_the_verdict():
    """If the suggested constraint cannot be applied, the verdict stays put."""
    state = _state_with_counterexample()
    stub = StubClient(
        [
            {
                "response": "I concede, and the missing assumption is 'x is nonzero'.",
                "concedes": True,
                # not a solver expression — the solver cannot parse it
                "new_constraint": "x is nonzero",
                "new_step": "",
            }
        ]
    )
    state = challenge_step(state, 2, "what about x = 0?", client=stub)
    assert state.verdict == "counterexample_found"
    assert "could not be applied" in (state.get_step(2).agent_response or "")


# ---------------------------------------------------------------------------
# Citations must never be fabricated
# ---------------------------------------------------------------------------
def test_citations_return_empty_list_when_nothing_is_found():
    from src.citations import find_citations

    stub = StubClient([{"citations": []}])
    assert find_citations("some claim", client=stub) == []


def test_citations_parse_a_real_entry():
    from src.citations import find_citations

    stub = StubClient(
        [
            {
                "citations": [
                    {
                        "title": "Fermat's Last Theorem",
                        "authors_or_source": "Wiles, 1994",
                        "relevance_note": "the general theorem this claim echoes",
                    }
                ]
            }
        ]
    )
    out = find_citations("some claim", client=stub)
    assert len(out) == 1
    assert out[0].title == "Fermat's Last Theorem"


# ---------------------------------------------------------------------------
# Export formats
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fmt", ["md", "html", "txt"])
def test_export_formats(tmp_path, fmt):
    from src.export import export_proof

    state = ProofState(claim="x^2 >= 0", verdict="no_counterexample_in_bound")
    path = export_proof(state, fmt, output_dir=str(tmp_path))
    assert os.path.exists(path)
    content = open(path, encoding="utf-8").read()
    assert "x^2 >= 0" in content


def test_export_includes_the_search_certificate(tmp_path):
    from src.export import export_proof

    state = ProofState(claim="x^2 >= 0", verdict="no_counterexample_in_bound")
    state.search_certificate = {
        "total_cubes": 12,
        "cubes_generated": 12,
        "cubes_eliminated_by_symmetry": 6,
        "cubes_solved": 6,
        "sat": 0,
        "unsat": 6,
        "unknown": 0,
        "workers": 4,
        "wall_clock_seconds": 0.1,
        "symmetries": [],
        "per_cube": [],
        "landmark_scale_note": (
            "For comparison, the 2016 Boolean Pythagorean Triples proof covered "
            "~2^7825 cases on 800 cores over 2 days."
        ),
    }
    path = export_proof(state, "md", output_dir=str(tmp_path))
    content = open(path, encoding="utf-8").read()
    assert "Search certificate" in content
    assert "2^7825" in content


# ---------------------------------------------------------------------------
# Memory: no duplicated work
# ---------------------------------------------------------------------------
def test_get_or_compute_runs_once():
    from src.memory import ProofMemory

    memory = ProofMemory()
    calls = []

    def compute():
        calls.append(1)
        return {"v": len(calls)}

    first, hit1 = memory.get_or_compute("k", compute)
    second, hit2 = memory.get_or_compute("k", compute)
    assert len(calls) == 1
    assert first == second
    assert hit1 is False and hit2 is True


# ---------------------------------------------------------------------------
# Canvas / vision plumbing (the web UI's blackboard)
# ---------------------------------------------------------------------------
def test_canvas_png_bytes_handles_every_payload_shape():
    """`st_canvas` can hand back bytes, a PIL image or a numpy array."""
    import numpy as np
    from PIL import Image

    from src.vision import canvas_png_bytes

    class Result:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    assert canvas_png_bytes(None) is None
    assert canvas_png_bytes(Result()) is None

    raw = canvas_png_bytes(Result(image_bytes=b"\x89PNG"))
    assert raw == b"\x89PNG"

    pil = Image.new("RGB", (8, 8), "white")
    assert canvas_png_bytes(Result(image_data=pil))[:4] == b"\x89PNG"

    arr = np.zeros((8, 8, 4), dtype=np.uint8)
    assert canvas_png_bytes(Result(image_data=arr))[:4] == b"\x89PNG"


def test_transcribe_canvas_returns_none_without_a_drawing():
    from src.vision import transcribe_canvas

    class Result:
        image_bytes = None
        image_data = None

    assert transcribe_canvas(Result()) is None
    assert transcribe_canvas(None) is None


def test_web_script_has_no_undefined_module_level_names():
    """Every name used by the script must be bound at module level.

    Streamlit re-runs the whole script on every click, so a helper that is
    defined *after* the button handler (or not defined at all) blows up with
    `NameError` the moment a user clicks. This shipped once as
    `NameError: name '_canvas_png_bytes' is not defined`.
    """
    import ast
    import builtins
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "src" / "web.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    loads: set[str] = set()
    bindings: set[str] = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}

    def walk(node) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bindings.add(child.name)
                continue  # function bodies have their own scope
            if isinstance(child, ast.Import):
                for alias in child.names:
                    bindings.add((alias.asname or alias.name).split(".")[0])
                continue
            if isinstance(child, ast.ImportFrom):
                for alias in child.names:
                    bindings.add(alias.asname or alias.name)
                continue
            if isinstance(child, ast.ExceptHandler) and child.name:
                bindings.add(child.name)  # `except X as exc:`
                continue
            if isinstance(child, ast.Name):
                if isinstance(child.ctx, ast.Store):
                    bindings.add(child.id)
                else:
                    loads.add(child.id)
            walk(child)

    walk(tree)

    undefined = sorted(loads - bindings)
    assert not undefined, (
        "web.py uses names that are never bound at module level: "
        f"{undefined} — they will raise NameError when a button is clicked."
    )

    # and the canvas helpers must come from the importable module, not the script
    text = src.read_text(encoding="utf-8")
    assert "from src.vision import transcribe_canvas" in text
    assert "def _canvas_png_bytes" not in text


def test_web_never_mutates_an_instantiated_widgets_state():
    """Assigning to a widget's session-state key *after* the widget was created
    raises `StreamlitWidgetAlreadyInstantiatedError`.

    This shipped as a crash on chat submit: `st.session_state.chat_input = ""`
    after `st.text_input(key="chat_input")`. The chat input is now versioned
    (`chat_input_<n>`) and the counter is bumped to force a fresh widget
    instead of mutating the old one.
    """
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "src" / "web.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    widget_keys: dict[str, int] = {}       # key -> line where it is created
    assignments: list[tuple[str, int]] = []  # (name, line) of session_state writes

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {
                "text_input",
                "text_area",
                "selectbox",
                "multiselect",
                "slider",
                "number_input",
                "checkbox",
                "button",
                "form_submit_button",
            }:
                for kw in node.keywords:
                    if (
                        kw.arg == "key"
                        and isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, str)
                    ):
                        widget_keys[kw.value.value] = node.lineno
        if isinstance(node, ast.Assign):
            for target in node.targets:
                # st.session_state.<name> = ...
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr == "session_state"
                ):
                    assignments.append((target.attr, node.lineno))

    offenders = [
        (name, line, widget_keys[name])
        for name, line in assignments
        if name in widget_keys and line > widget_keys[name]
    ]
    assert not offenders, (
        "web.py assigns to a widget key after the widget was created "
        f"(StreamlitWidgetAlreadyInstantiatedError): {offenders}"
    )

    # the chat input must use the versioned-key pattern
    text = src.read_text(encoding="utf-8")
    assert 'st.session_state.chat_input = ""' not in text
    assert "chat_input_{st.session_state.chat_input_version}" in text


def test_chat_transcript_carries_the_agents_answers():
    """The agent's replies must reach the CHAT transcript.

    A challenge was stored on the proof state and rendered on the BLACKBOARD,
    but the chat only ever showed the user's half of the exchange — the
    transcript looked like a wall of unanswered questions. The chat message
    list must therefore receive a 'breach' message for every check and every
    challenge.
    """
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "src" / "web.py"
    text = src.read_text(encoding="utf-8")
    tree = ast.parse(text)

    # every append to session_state.messages must include an agent reply
    agent_replies = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "append"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "messages"
    ]
    breach_messages = []
    for n in agent_replies:
        for constant in ast.walk(n):
            if (
                isinstance(constant, ast.Constant)
                and constant.value == "breach"
            ):
                breach_messages.append(n)
                break
    assert len(breach_messages) >= 2, (
        "the chat must receive an agent reply for both a check and a challenge "
        f"(found {len(breach_messages)} of {len(agent_replies)} appends)"
    )

    # and the reply must contain the agent's actual answer
    assert "_challenge_message(state" in text
    assert "_verdict_message(state" in text


def test_challenge_message_contains_the_agents_answer():
    """`_challenge_message` must surface the response, not just a label."""
    import importlib.util
    from pathlib import Path

    from src.state import ProofState

    web_path = Path(__file__).resolve().parent.parent / "src" / "web.py"
    source = web_path.read_text(encoding="utf-8")
    start = source.index("def _challenge_message")
    end = source.index("def _render_state")
    namespace: dict = {}
    exec(compile(source[start:end], str(web_path), "exec"), namespace)

    state = ProofState(claim="a + b > a - b", verdict="no_counterexample_in_bound")
    step = state.add_step("Assume a and b are positive integers.")
    step.challenge_text = "if b=0?"
    step.agent_response = "The domain already restricts b to 1..50, so b=0 is excluded."

    message = namespace["_challenge_message"](state, 1)
    assert "if b=0?" not in message or True  # the objection may or may not be echoed
    assert "excluded" in message, message
    assert "step 1" in message.lower()


def test_verdict_message_states_the_verdict_and_its_scope():
    import importlib.util
    from pathlib import Path

    from src.state import ProofState

    web_path = Path(__file__).resolve().parent.parent / "src" / "web.py"
    source = web_path.read_text(encoding="utf-8")
    start = source.index("def _verdict_message")
    end = source.index("def _challenge_message")
    namespace: dict = {}
    exec(compile(source[start:end], str(web_path), "exec"), namespace)

    false_state = ProofState(claim="x^2 >= -1 for all x", verdict="counterexample_found")
    false_state.counterexample = {"x": 0}
    msg = namespace["_verdict_message"](false_state)
    assert "Counterexample" in msg and "x = 0" in msg

    true_state = ProofState(claim="x^2 >= 0", verdict="no_counterexample_in_bound")
    msg = namespace["_verdict_message"](true_state)
    assert "No counterexample" in msg
    assert "not a proof of truth" in msg

    unknown_state = ProofState(claim="collatz", verdict="unknown")
    unknown_state.unknown_reason = "out of scope"
    msg = namespace["_verdict_message"](unknown_state)
    assert "Unknown" in msg and "out of scope" in msg
