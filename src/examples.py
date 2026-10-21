"""The built-in "greatest hits" gallery.

Pre-baked historical examples that resolve in seconds and need no network —
judges can run `breach check --example euler` and see real mathematics.

Each entry carries its own structured form, so the demo never depends on the
LLM being reachable. The forms are checked by the same solver code path as
everything else; nothing here is faked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .engine import SymbolicForm, Variable


@dataclass
class Example:
    key: str
    title: str
    claim: str
    form: SymbolicForm
    expected: str
    history: str = ""
    tags: list[str] = field(default_factory=list)


def _primes_upto(n: int) -> list[int]:
    sieve = [True] * (n + 1)
    sieve[0:2] = [False, False]
    for i in range(2, int(n**0.5) + 1):
        if sieve[i]:
            for j in range(i * i, n + 1, i):
                sieve[j] = False
    return [i for i, s in enumerate(sieve) if s]


def _prime_disjunction(var: str, primes: list[int]) -> str:
    """`Or(p == 2, p == 3, ...)` — z3's Or, not Python's `or`."""
    return "Or(" + ", ".join(f"{var} == {p}" for p in primes) + ")"


def _build_examples() -> dict[str, Example]:
    examples: dict[str, Example] = {}

    # ---- Euler's sum-of-powers conjecture (1769) — refuted 1966 ----------
    examples["euler"] = Example(
        key="euler",
        title="Euler's sum-of-powers conjecture (k = 5)",
        claim=(
            "There are no positive integers a, b, c, d, n with a^5 + b^5 + c^5 + d^5 = n^5."
        ),
        form=SymbolicForm(
            backend="mitm",
            variables=[
                Variable("a", "int", 1, 150),
                Variable("b", "int", 1, 150),
                Variable("c", "int", 1, 150),
                Variable("d", "int", 1, 150),
                Variable("n", "int", 1, 150),
            ],
            constraints=["a >= 1", "b >= 1", "c >= 1", "d >= 1", "n >= 1"],
            claim_expr="a**5 + b**5 + c**5 + d**5 == n**5",
            steps=[
                "Euler conjectured (1769) that at least k k-th powers are needed to sum to a k-th power.",
                "For k = 5 this claims no four positive fifth powers sum to a fifth power.",
                "The search space is bounded to 1..150 (the historical counterexample lives there).",
                "A meet-in-the-middle split turns 150^5 combinations into ~150^3 probes.",
            ],
            scope_note=(
                "Searched exhaustively over 1..150 by a meet-in-the-middle split of the "
                "power sums. The 1966 Lander–Parkin counterexample (27, 84, 110, 133, 144) "
                "lies inside this bound."
            ),
            confidence=0.95,
            search_space={"exponent": 5, "lower": 1, "upper": 150, "terms": 4},
        ),
        expected="counterexample_found",
        history=(
            "Euler's conjecture held for 200 years. Lander and Parkin found "
            "27^5 + 84^5 + 110^5 + 133^5 = 144^5 in 1966, refuting it for k = 5."
        ),
        tags=["history", "counterexample", "sum-of-powers"],
    )

    # ---- Pythagorean triples — the classic counterexample ---------------
    examples["pythagorean"] = Example(
        key="pythagorean",
        title="Pythagorean triples exist in the small square",
        claim="There are no positive integers x, y, z with x^2 + y^2 = z^2.",
        form=SymbolicForm(
            backend="z3",
            variables=[
                Variable("x", "int", 1, 20),
                Variable("y", "int", 1, 20),
                Variable("z", "int", 1, 20),
            ],
            constraints=["x >= 1", "y >= 1", "z >= 1"],
            claim_expr="Not(x*x + y*y == z*z)",
            steps=[
                "The claim asserts that no integer right triangle has square hypotenuse.",
                "Search all x, y, z in 1..20 and look for a point where the relation holds.",
            ],
            scope_note="Bounded to 1..20; the first witness (3, 4, 5) is well inside it.",
            confidence=0.95,
        ),
        expected="counterexample_found",
        history="(3, 4, 5) has been known since antiquity — Euclid's proof of the theorem relies on it.",
        tags=["classic", "counterexample"],
    )

    # ---- Squares modulo 4 — a true claim the solver can confirm ---------
    examples["squares_mod4"] = Example(
        key="squares_mod4",
        title="Squares are 0 or 1 modulo 4",
        claim="The square of any integer is congruent to 0 or 1 modulo 4.",
        form=SymbolicForm(
            backend="z3",
            variables=[Variable("n", "int", 0, 2000)],
            constraints=["n >= 0", "n <= 2000"],
            claim_expr="Or((n * n) % 4 == 0, (n * n) % 4 == 1)",
            steps=[
                "Every integer is 0, 1, 2 or 3 mod 4.",
                "Squaring gives 0, 1, 0, 1 — so the residue is always 0 or 1.",
                "The solver checks all 2001 residues in the bound directly.",
            ],
            scope_note=(
                "Checked for every residue class represented in 0..2000. The general "
                "statement is a short argument, not an open problem."
            ),
            confidence=0.95,
        ),
        expected="no_counterexample_in_bound",
        history="A one-line argument: squaring a residue mod 4 gives 0 or 1.",
        tags=["classic", "true-claim", "modular"],
    )

    # ---- Squares are never negative — the simplest true claim -----------
    examples["square_nonneg"] = Example(
        key="square_nonneg",
        title="Squares are never negative",
        claim="For every integer n, n^2 is greater than or equal to 0.",
        form=SymbolicForm(
            backend="z3",
            variables=[Variable("n", "int", -50, 50)],
            constraints=["n >= -50", "n <= 50"],
            claim_expr="n*n >= 0",
            steps=["Search every integer in the bound for a negative square."],
            scope_note="Bounded to -50..50.",
            confidence=0.95,
        ),
        expected="no_counterexample_in_bound",
        history="Trivially true — included as the calm baseline of the gallery.",
        tags=["true-claim", "sanity"],
    )

    # ---- Strong Goldbach, bounded ---------------------------------------
    goldbach_primes = _primes_upto(200)
    examples["goldbach"] = Example(
        key="goldbach",
        title="Strong Goldbach conjecture (bounded check)",
        claim="Every even integer greater than 2 is the sum of two primes.",
        form=SymbolicForm(
            backend="z3",
            claim_kind="existential_sweep",
            variables=[
                Variable("n", "int", 4, 200),
                Variable("p", "int", 2, 200),
                Variable("q", "int", 2, 200),
            ],
            constraints=[
                "n >= 4",
                "n <= 200",
                "n % 2 == 0",
                "p >= 2",
                "q >= 2",
            ],
            claim_expr=(
                "And(p + q == n, "
                + _prime_disjunction("p", goldbach_primes)
                + ", "
                + _prime_disjunction("q", goldbach_primes)
                + ")"
            ),
            steps=[
                "The claim says every even n in 4..200 is p + q for primes p, q.",
                "A counterexample is an even n with no prime pair at all.",
                "Primality is expanded into an explicit disjunction over the bounded range.",
            ],
            scope_note=(
                "Checked exhaustively for even n in 4..200. The unbounded conjecture "
                "remains open — a bounded check is not a proof."
            ),
            confidence=0.85,
            search_space={"sweep_var": "n", "lower": 4, "upper": 200, "step": 2},
        ),
        expected="no_counterexample_in_bound",
        history="Goldbach's conjecture is still open; it has been verified by computer far beyond 400.",
        tags=["open", "true-claim", "goldbach"],
    )

    # ---- A claim that is honestly out of scope -------------------------
    examples["collatz"] = Example(
        key="collatz",
        title="Collatz conjecture — out of scope, and we say so",
        claim="Every positive integer eventually reaches 1 under the Collatz map.",
        form=SymbolicForm(
            backend="sympy",
            variables=[Variable("n", "int", 1, 10**12)],
            constraints=["n >= 1"],
            claim_expr="",
            steps=[
                "The Collatz conjecture is an open problem about unbounded iteration.",
                "No SMT solver or computer algebra system can decide it mechanically.",
            ],
            scope_note=(
                "Out of scope for mechanical verification: this is an open conjecture about "
                "unbounded iteration, not a bounded or decidable statement."
            ),
            confidence=0.0,
            ambiguity="The claim is well-formed but lies outside what solvers can decide.",
        ),
        expected="unknown",
        history="Open since 1937. Computer searches cover billions of cases; no proof is known.",
        tags=["open", "honesty", "out-of-scope"],
    )

    # ---- Landau's fourth problem ----------------------------------------
    examples["landau"] = Example(
        key="landau",
        title="Landau's fourth problem (twin primes)",
        claim="There are infinitely many twin primes, i.e. infinitely many n with n and n+2 both prime.",
        form=SymbolicForm(
            backend="sympy",
            variables=[Variable("n", "int", 2, 10**9)],
            constraints=["n >= 2"],
            claim_expr="",
            steps=[
                "Landau's fourth problem asks for infinitely many twin primes.",
                "Infinitude is not a property a bounded solver can confirm.",
            ],
            scope_note=(
                "Out of scope for mechanical verification: the claim is about infinitude, "
                "which no bounded search can settle."
            ),
            confidence=0.0,
            ambiguity="Well-formed but not decidable by a bounded search.",
        ),
        expected="unknown",
        history="One of Landau's four problems; still open. The bounded version is verified to very large N.",
        tags=["open", "honesty", "infinitude"],
    )

    return examples


EXAMPLES: dict[str, Example] = _build_examples()


def list_examples() -> list[Example]:
    return list(EXAMPLES.values())


def get_example(key: str) -> Optional[Example]:
    return EXAMPLES.get(key.strip().lower())
