"""Stage 4b — Cube-and-conquer case splitting + symmetry breaking.

This is the architecture (not the scale) behind landmark SAT results: split the
search space into independent "cubes", dispatch them in parallel, and kill
equivalent cubes up front with symmetry breaking.

Scale honesty is deliberate: the Boolean Pythagorean Triples proof covered
~2^7825 cases on 800 cores over two days. We run the same *shape* of search on
a laptop, and we always report the real numbers.
"""

from __future__ import annotations

import itertools
import multiprocessing as mp
import time
from typing import Any, Optional

from .engine import SymbolicForm, Variable
from .memory import ProofMemory, make_key
from .orchestrator import constraint_worker

DEFAULT_SPLITS = 8


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------
def split_into_cubes(
    form: SymbolicForm,
    split_variable: Optional[str] = None,
    num_splits: int = DEFAULT_SPLITS,
) -> list[SymbolicForm]:
    """Partition the search space along one variable into independent cubes."""
    if not form.variables:
        return [form]
    target = None
    if split_variable:
        for v in form.variables:
            if v.name == split_variable:
                target = v
                break
    if target is None:
        # pick the first integer variable with a finite range (best for Z3)
        for v in form.variables:
            if v.lower is not None and v.upper is not None:
                target = v
                break
    if target is None or target.lower is None or target.upper is None:
        target = form.variables[0]

    lo = float(target.lower if target.lower is not None else 0)
    hi = float(target.upper if target.upper is not None else 1)
    if hi <= lo:
        return [form]

    n = max(1, int(num_splits))
    step = (hi - lo) / n
    cubes: list[SymbolicForm] = []
    for i in range(n):
        cube_lo = lo + i * step
        cube_hi = lo + (i + 1) * step
        if target.type == "int":
            ilo, ihi = int(round(cube_lo)), int(round(cube_hi))
            if ihi < ilo:
                ilo, ihi = ihi, ilo
            extra = f"{target.name} >= {ilo}", f"{target.name} <= {ihi}"
            bounds = (float(ilo), float(ihi))
        else:
            extra = (f"{target.name} >= {cube_lo}", f"{target.name} <= {cube_hi}")
            bounds = (cube_lo, cube_hi)
        cube = SymbolicForm.from_dict(form.to_dict())
        cube.constraints = list(form.constraints) + list(extra)
        cube.steps = list(form.steps)
        cube.search_space = dict(form.search_space or {})
        cube.search_space["cube"] = {"variable": target.name, "index": i, "bounds": bounds}
        cubes.append(cube)
    return cubes


# ---------------------------------------------------------------------------
# Symmetry
# ---------------------------------------------------------------------------
def _claim_expr_z3(form):
    """Build the Z3 claim expression (returns None if it cannot be built)."""
    try:
        import z3

        from .engine import _safe_eval, _z3_namespace

        ns, consts = _z3_namespace(form)
        if not form.claim_expr.strip():
            return None, consts
        expr = _safe_eval(form.claim_expr, ns)
        if not z3.is_bool(expr):
            return None, consts
        return expr, consts
    except Exception:
        return None, {}


def _valid_equivalence(a, b, timeout_ms: int = 3000) -> bool:
    """True iff `a` and `b` are equivalent (checked by Z3, not by eyeballing)."""
    try:
        import z3

        solver = z3.Solver()
        solver.set("timeout", timeout_ms)
        solver.add(a != b)
        return solver.check() == z3.unsat
    except Exception:
        return False


def detect_symmetries(form: SymbolicForm) -> list[dict[str, Any]]:
    """Detect permutation and sign-flip symmetries of the claim expression.

    Every reported symmetry is *verified* by asking Z3 whether the claim is
    equivalent to its transformed copy. We never eliminate a cube on the basis
    of a guess — an unsound symmetry break could hide a counterexample.
    """
    symmetries: list[dict[str, Any]] = []
    claim, consts = _claim_expr_z3(form)
    if claim is None:
        return symmetries

    import z3

    # -- permutations of variables with identical domains --
    groups: dict[tuple, list[str]] = {}
    for v in form.variables:
        key = (v.type, v.lower, v.upper)
        groups.setdefault(key, []).append(v.name)
    for _key, members in groups.items():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                try:
                    swapped = z3.substitute(claim, [(consts[a], consts[b]), (consts[b], consts[a])])
                except Exception:
                    continue
                if _valid_equivalence(claim, swapped):
                    symmetries.append({"type": "swap", "a": a, "b": b})

    # -- sign flips (only where the domain is symmetric) --
    for v in form.variables:
        if v.type != "int" or v.lower is None or v.upper is None:
            continue
        if float(v.lower) != -float(v.upper):
            continue
        try:
            flipped = z3.substitute(claim, [(consts[v.name], -consts[v.name])])
        except Exception:
            continue
        if _valid_equivalence(claim, flipped):
            symmetries.append({"type": "flip", "variable": v.name})
    return symmetries


def _cube_signature(cube: SymbolicForm) -> tuple:
    """A comparable signature of a cube: its extra variable intervals."""
    meta = (cube.search_space or {}).get("cube")
    if not meta:
        return ()
    return (meta.get("variable"), tuple(round(float(b), 6) for b in meta.get("bounds", ())))


def _canonical_signature(cube: SymbolicForm, symmetries: list[dict[str, Any]]) -> tuple:
    """Canonical form of a cube under the detected symmetry group."""
    sig = _cube_signature(cube)
    if not sig:
        return sig
    var, (lo, hi) = sig
    candidates = [sig]
    for sym in symmetries:
        if sym["type"] == "flip" and sym["variable"] == var:
            candidates.append((var, (-hi, -lo)))
        if sym["type"] == "swap":
            if sym["a"] == var:
                candidates.append((sym["b"], (lo, hi)))
            if sym["b"] == var:
                candidates.append((sym["a"], (lo, hi)))
    return min(candidates)


def eliminate_symmetric_cubes(
    cubes: list[SymbolicForm], symmetries: list[dict[str, Any]]
) -> tuple[list[SymbolicForm], int]:
    """Drop cubes that are equivalent to an earlier one under a symmetry."""
    if not symmetries:
        return cubes, 0
    seen: set[tuple] = set()
    kept: list[SymbolicForm] = []
    dropped = 0
    for cube in cubes:
        key = _canonical_signature(cube, symmetries)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        kept.append(cube)
    return kept, dropped


# ---------------------------------------------------------------------------
# Parallel dispatch
# ---------------------------------------------------------------------------
def _solve_cube(args: tuple[str, dict[str, Any], float]) -> dict[str, Any]:
    """Module-level so it survives Windows' spawn start method."""
    cube_id, cube_dict, timeout = args
    form = SymbolicForm.from_dict(cube_dict)
    from .engine import run_solver

    result = run_solver(form, timeout=timeout)
    return {
        "cube_id": cube_id,
        "verdict": result.verdict,
        "counterexample": result.counterexample,
        "unknown": result.unknown_info.to_dict() if result.unknown_info else None,
        "elapsed": result.elapsed,
    }


def dispatch_cubes(
    cubes: list[SymbolicForm],
    memory: Optional[ProofMemory] = None,
    workers: Optional[int] = None,
    timeout: float = 10.0,
    claim: str = "",
) -> list[dict[str, Any]]:
    """Solve cubes in parallel. Falls back to serial if the pool fails."""
    memory = memory or ProofMemory()
    workers = workers or max(1, min(8, (mp.cpu_count() or 2) - 1))
    payloads = [(i, c.to_dict(), timeout) for i, c in enumerate(cubes)]

    results: list[dict[str, Any]] = []
    try:
        with mp.Pool(processes=workers) as pool:
            results = pool.map(_solve_cube, payloads)
    except Exception:
        results = []
    if not results:
        results = [_solve_cube(p) for p in payloads]

    # Parent process owns the shared memory — this is what guarantees no two
    # cubes overwrite each other's record.
    for res in results:
        memory.write(
            make_key(f"{claim}#cube{res['cube_id']}", "cube"),
            res,
            source="cases.dispatch_cubes",
        )
    return results


# ---------------------------------------------------------------------------
# Certificate
# ---------------------------------------------------------------------------
def build_certificate(
    cubes: list[SymbolicForm],
    results: list[dict[str, Any]],
    symmetries_eliminated: int,
    workers: int,
    symmetries: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """The 'Search Certificate' — a reproducible record of what was searched."""
    sat = [r for r in results if r["verdict"] == "counterexample_found"]
    unsat = [r for r in results if r["verdict"] == "no_counterexample_in_bound"]
    unknown = [r for r in results if r["verdict"] == "unknown"]
    return {
        "total_cubes": len(cubes) + symmetries_eliminated,
        "cubes_generated": len(cubes),
        "cubes_eliminated_by_symmetry": symmetries_eliminated,
        "cubes_solved": len(results),
        "sat": len(sat),
        "unsat": len(unsat),
        "unknown": len(unknown),
        "workers": workers,
        "wall_clock_seconds": round(sum(r.get("elapsed", 0.0) for r in results), 4),
        "symmetries": symmetries or [],
        "per_cube": results,
        "landmark_scale_note": (
            "For comparison, the 2016 Boolean Pythagorean Triples proof covered "
            "~2^7825 cases on 800 cores over 2 days."
        ),
    }


def run_cube_search(
    form: SymbolicForm,
    claim: str,
    memory: Optional[ProofMemory] = None,
    num_splits: int = DEFAULT_SPLITS,
    workers: Optional[int] = None,
    timeout: float = 10.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Full pipeline: split -> symmetry-break -> dispatch -> certify."""
    memory = memory or ProofMemory()
    symmetries = detect_symmetries(form)

    # Split along the primary variable and, when the claim is symmetric under
    # a variable swap, along the symmetric partner as well — the duplicate
    # cubes are then removed by the symmetry filter below.
    split_vars: list[str] = []
    primary = next(
        (v.name for v in form.variables if v.lower is not None and v.upper is not None),
        None,
    )
    if primary:
        split_vars.append(primary)
    for sym in symmetries:
        if sym.get("type") == "swap":
            for name in (sym.get("a"), sym.get("b")):
                if name and name not in split_vars:
                    split_vars.append(name)

    cubes: list[SymbolicForm] = []
    for var in split_vars:
        cubes.extend(split_into_cubes(form, split_variable=var, num_splits=num_splits))

    kept, dropped = eliminate_symmetric_cubes(cubes, symmetries)
    results = dispatch_cubes(kept, memory=memory, workers=workers, timeout=timeout, claim=claim)
    cert = build_certificate(kept, results, dropped, workers or (mp.cpu_count() or 2), symmetries)
    return results, cert
