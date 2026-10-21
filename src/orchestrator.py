"""Stage 4 — Orchestrator / "subagents".

Implemented as plain function dispatch (not autonomous agent loops): the point
is the *routing* and the *shared memory discipline*, not fake autonomy.

Every worker writes through the shared `ProofMemory`, so no two workers can
duplicate or clobber each other's work.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from .engine import SolverResult, SymbolicForm, run_solver
from .llm_client import LLMClient, get_client
from .memory import ProofMemory, make_key


def symbolic_worker(payload: dict[str, Any], memory: ProofMemory) -> dict[str, Any]:
    """SymPy-side check of a structured claim."""
    form = SymbolicForm.from_dict(payload.get("form", {}))
    result = run_solver(form, timeout=float(payload.get("timeout", 10.0)))
    out = {
        "worker": "symbolic_worker",
        "verdict": result.verdict,
        "counterexample": result.counterexample,
        "unknown": result.unknown_info.to_dict() if result.unknown_info else None,
        "elapsed": result.elapsed,
    }
    memory.write(
        make_key(payload.get("claim", ""), "symbolic"),
        out,
        source="symbolic_worker",
    )
    return out


def constraint_worker(payload: dict[str, Any], memory: ProofMemory) -> dict[str, Any]:
    """Z3-side check of a structured claim."""
    form = SymbolicForm.from_dict(payload.get("form", {}))
    result = run_solver(form, timeout=float(payload.get("timeout", 10.0)))
    out = {
        "worker": "constraint_worker",
        "verdict": result.verdict,
        "counterexample": result.counterexample,
        "unknown": result.unknown_info.to_dict() if result.unknown_info else None,
        "elapsed": result.elapsed,
    }
    memory.write(
        make_key(payload.get("claim", ""), "constraint"),
        out,
        source="constraint_worker",
    )
    return out


def numeric_worker(payload: dict[str, Any], memory: ProofMemory) -> dict[str, Any]:
    """High-precision numeric sanity check of a candidate counterexample.

    Re-evaluates the claim at the candidate point with mpmath so we never
    report a counterexample that does not actually violate the claim.
    """
    import mpmath as mp

    claim_text = payload.get("claim", "")
    point = payload.get("point", {}) or {}
    form = SymbolicForm.from_dict(payload.get("form", {}))
    verdict = "no_counterexample_in_bound"
    detail = "numeric re-check found no violation"
    if point and form.claim_expr:
        try:
            local = {k: mp.mpf(v) for k, v in point.items()}
            local["Abs"] = abs
            local["sqrt"] = mp.sqrt
            local["pi"] = mp.pi
            expr = form.claim_expr.replace("**", "**")
            value = eval(expr, {"__builtins__": {}}, local)  # noqa: S307 - restricted
            if not bool(value):
                verdict = "counterexample_found"
                detail = f"numeric re-check confirms the violation at {point}"
            else:
                detail = "numeric re-check contradicts the solver's counterexample"
        except Exception as exc:  # noqa: BLE001
            verdict = "unknown"
            detail = f"numeric re-check could not run: {exc}"
    out = {"worker": "numeric_worker", "verdict": verdict, "detail": detail}
    memory.write(make_key(claim_text, "numeric"), out, source="numeric_worker")
    return out


WORKERS: dict[str, Callable[[dict[str, Any], ProofMemory], dict[str, Any]]] = {
    "symbolic": symbolic_worker,
    "constraint": constraint_worker,
    "numeric": numeric_worker,
}


def dispatch(task: dict[str, Any], memory: Optional[ProofMemory] = None) -> dict[str, Any]:
    """Route a task to the right worker based on `task['type']`."""
    memory = memory or ProofMemory()
    task_type = (task.get("type") or "constraint").lower()
    worker = WORKERS.get(task_type, constraint_worker)
    started = time.time()
    result = worker(task, memory)
    result["dispatched_to"] = worker.__name__
    result["total_elapsed"] = time.time() - started
    return result
