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
