"""Bounded sum-of-powers search (meet-in-the-middle).

This is the honest, laptop-scale version of the technique that cracked the
Boolean Pythagorean Triples problem: split the search space into halves, hash
one half, probe it with the other half, and report a *witness* when the two
halves meet.

Used by the built-in example gallery (Euler's sum-of-powers conjecture), where
Z3's nonlinear integer arithmetic would be too slow to be demo-safe.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .state import UnknownInfo


def _pow(base: int, exp: int) -> int:
    return base ** exp


def solve_sum_of_powers(form, timeout: float = 30.0) -> "Any":
    """Solve `a^e + b^e + ... = n^e` over a bounded integer domain.

    `form.search_space` is expected to hold:
        {"exponent": 5, "lower": 1, "upper": 150, "terms": 4}
    """
    from .engine import SolverResult

    space = form.search_space or {}
    exponent = int(space.get("exponent", 5))
    lower = int(space.get("lower", 1))
    upper = int(space.get("upper", 150))
    terms = int(space.get("terms", 4))

    started = time.time()
    if terms != 4:
        return SolverResult(
            verdict="unknown",
            unknown_info=UnknownInfo(
                kind="unsupported_backend",
                confidence=0.9,
                detail=f"The meet-in-the-middle backend only handles exactly 4 summands (got {terms}).",
                remedy="Fall back to the generic Z3 backend.",
            ),
            backend="mitm",
        )

    if time.time() - started > timeout:
        return SolverResult(
            verdict="unknown",
            unknown_info=UnknownInfo(
                kind="timeout",
                confidence=0.9,
                detail="The bounded search ran out of time.",
                remedy="Narrow the bound and try again.",
            ),
            backend="mitm",
        )

    values = list(range(lower, upper + 1))
    powers = {v: _pow(v, exponent) for v in values}

    # half A: a^e + b^e   -> hash map
    half_a: dict[int, tuple[int, int]] = {}
    for a in values:
        pa = powers[a]
        for b in values:
            half_a.setdefault(pa + powers[b], (a, b))

    # half B: c^e + d^e   -> we probe instead of storing
    checked = 0
    for c in values:
        pc = powers[c]
        for d in values:
            checked += 1
            if time.time() - started > timeout:
                return SolverResult(
                    verdict="unknown",
                    unknown_info=UnknownInfo(
                        kind="timeout",
                        confidence=0.95,
                        detail=f"The bounded search was cut off after {checked:,} pairs.",
                        remedy="Reduce the upper bound.",
                    ),
                    backend="mitm",
                )
            partial = pc + powers[d]
            for n in values:
                target = powers[n] - partial
                hit = half_a.get(target)
                if hit is not None:
                    return SolverResult(
                        verdict="counterexample_found",
                        counterexample={
                            "a": hit[0],
                            "b": hit[1],
                            "c": c,
                            "d": d,
                            "n": n,
                            "exponent": exponent,
                            "equation": (
                                f"{hit[0]}^{exponent} + {hit[1]}^{exponent} + "
                                f"{c}^{exponent} + {d}^{exponent} = {n}^{exponent}"
                            ),
                        },
                        raw=f"witness found after {checked:,} half-pairs",
                        elapsed=time.time() - started,
                        backend="mitm",
                    )

    return SolverResult(
        verdict="no_counterexample_in_bound",
        raw=f"exhausted {checked:,} half-pairs, no witness",
        elapsed=time.time() - started,
        backend="mitm",
    )
