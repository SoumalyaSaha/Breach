"""Stage 13 — Tests for the deterministic core.

These exercise the solver path directly (no network, no LLM): the whole point
of Breach is that the checking is done by real solvers, so that is what we
test. The LLM-dependent layers (translation, challenge, autopsy) are tested
with a stub client.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine import SymbolicForm, Variable, check_with_form, run_solver  # noqa: E402
from src.examples import EXAMPLES, get_example  # noqa: E402
from src.memory import ProofMemory  # noqa: E402
from src.state import ProofState  # noqa: E402


# ---------------------------------------------------------------------------
# 1. a TRUE claim -> no counterexample in the bound
# ---------------------------------------------------------------------------
def test_true_claim_yields_no_counterexample():
    form = SymbolicForm(
        backend="z3",
        variables=[Variable("n", "int", -50, 50)],
        constraints=["n >= -50", "n <= 50"],
        claim_expr="n * n >= 0",
    )
    result = run_solver(form, timeout=10)
    assert result.verdict == "no_counterexample_in_bound"
    assert result.counterexample is None


# ---------------------------------------------------------------------------
# 2. a FALSE claim -> a real counterexample with exact witness values
# ---------------------------------------------------------------------------
def test_false_claim_yields_counterexample():
    form = SymbolicForm(
        backend="z3",
        variables=[
            Variable("x", "int", 1, 20),
            Variable("y", "int", 1, 20),
            Variable("z", "int", 1, 20),
        ],
        constraints=["x >= 1", "y >= 1", "z >= 1"],
        claim_expr="Not(x * x + y * y == z * z)",
    )
    result = run_solver(form, timeout=10)
    assert result.verdict == "counterexample_found"
    ce = result.counterexample or {}
    assert set(ce) == {"x", "y", "z"}
    assert ce["x"] ** 2 + ce["y"] ** 2 == ce["z"] ** 2


# ---------------------------------------------------------------------------
# 3. an UNKNOWN claim -> honest unknown, with a reason and a confidence
# ---------------------------------------------------------------------------
def test_undecidable_claim_returns_scored_unknown():
    form = SymbolicForm(
        backend="sympy",
        variables=[Variable("n", "int", 1, 1000)],
        constraints=["n >= 1"],
        claim_expr="",
        scope_note=(
            "Out of scope for mechanical verification: this is an open conjecture about "
            "unbounded iteration, not a bounded or decidable statement."
        ),
    )
    result = run_solver(form, timeout=10)
    assert result.verdict == "unknown"
    assert result.unknown_info is not None
    assert result.unknown_info.kind in ("undecidable", "translation_ambiguity")
    assert 0.0 <= result.unknown_info.confidence <= 1.0
    assert result.unknown_info.detail


# ---------------------------------------------------------------------------
# 4. the gallery examples all behave as advertised
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", sorted(EXAMPLES.keys()))
def test_gallery_examples_match_expected_verdict(key):
    ex = get_example(key)
    assert ex is not None
    state = check_with_form(ex.form, ex.claim, timeout=30)
    assert state.verdict == ex.expected, f"{key}: {state.verdict} != {ex.expected}"


def test_euler_example_finds_the_historical_witness():
    ex = get_example("euler")
    state = check_with_form(ex.form, ex.claim, timeout=30)
    assert state.verdict == "counterexample_found"
    ce = state.counterexample or {}
    lhs = sum(ce[k] ** 5 for k in ("a", "b", "c", "d"))
    assert lhs == ce["n"] ** 5


# ---------------------------------------------------------------------------
# 5. memory discipline: no duplicated or overwritten work
# ---------------------------------------------------------------------------
def test_memory_write_never_overwrites():
    memory = ProofMemory()
    assert memory.write("k", {"v": 1}, source="a") is True
    assert memory.write("k", {"v": 2}, source="b") is False
    assert memory.read("k") == {"v": 1}


def test_cached_check_is_reused():
    memory = ProofMemory()
    ex = get_example("pythagorean")
    first = check_with_form(ex.form, ex.claim, memory=memory)
    second = check_with_form(ex.form, ex.claim, memory=memory)
    assert first.verdict == second.verdict == "counterexample_found"


# ---------------------------------------------------------------------------
# 6. state round-trip (CLI <-> web session file)
# ---------------------------------------------------------------------------
def test_state_serialisation_round_trip(tmp_path):
    state = ProofState(claim="x^2 >= 0", verdict="no_counterexample_in_bound")
    state.add_step("Assume x is an integer.")
    path = tmp_path / "session.json"
    state.save(str(path))
    loaded = ProofState.load(str(path))
    assert loaded.claim == state.claim
    assert loaded.verdict == state.verdict
    assert loaded.steps[0].text == "Assume x is an integer."


# ---------------------------------------------------------------------------
# 7. symbols: shortcuts work, function names are protected
# ---------------------------------------------------------------------------
def test_symbol_shortcuts():
    from src.symbols import apply_shortcut, find_completion

    assert find_completion("the angle pi") == ("pi", "π")
    assert find_completion("use sin") is None  # protected function name
    assert find_completion("x log") is None
    text, cursor = apply_shortcut("the angle pi")
    assert text == "the angle π"


# ---------------------------------------------------------------------------
# 8. export produces a real file
# ---------------------------------------------------------------------------
def test_export_writes_markdown(tmp_path):
    from src.export import export_proof

    state = ProofState(claim="x^2 >= 0", verdict="no_counterexample_in_bound")
    path = export_proof(state, "md", output_dir=str(tmp_path))
    assert os.path.exists(path)
    content = open(path, encoding="utf-8").read()
    assert "x^2 >= 0" in content
    assert "NO COUNTEREXAMPLE FOUND" in content
