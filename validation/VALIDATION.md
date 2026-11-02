# miniF2F-curated validation corpus

A small, curated benchmark used to validate Breach's claim-verification
pipeline against real, externally-sourced mathematical statements — not
only against problems we wrote ourselves. This corpus is **curated from
miniF2F** (the standard cross-system academic benchmark for automated/formal
mathematical reasoning — [arXiv:2109.00110](https://arxiv.org/abs/2109.00110)),
selecting entries that fall inside Breach's actual scope: bounded,
mechanically decidable claims checkable by Z3/SymPy.

## Summary

| ID | Name | Category | Expected | Status |
|---|---|---|---|---|
| BVC-001 | `amc12_2000_p11` | algebraic identity | `no_counterexample_in_bound` | ✅ Pass (5/5 runs, 100% accuracy) |
| BVC-002 | `mathd_numbertheory_618` | number theory (gcd) | `no_counterexample_in_bound` | ⚠️ Initially flaky → ✅ Fixed (5/5 runs, 100% accuracy) |
| BVC-003 | `mathd_algebra_487` | algebraic system | `no_counterexample_in_bound` | ✅ Pass (5/5 runs, 100% accuracy) |
| BVC-004 | Pólya conjecture (1919) | historical context only | n/a | Not executed — citation only |
| BVC-005 | control inequality | counterexample control | `counterexample_found` | ✅ Pass (5/5 runs, 100% accuracy) |
| BVC-006 | `mathd_algebra_141` | algebraic identity | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-007 | `mathd_algebra_160` | linear system | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-008 | `mathd_algebra_412` | linear system | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-009 | `mathd_algebra_44` | linear system | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-010 | `mathd_algebra_126` | linear equation | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-011 | `mathd_algebra_398` | algebraic identity | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-012 | `mathd_algebra_107` | algebraic identity | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-013 | `mathd_algebra_455` | linear equation | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-014 | `mathd_algebra_440` | linear equation | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-015 | `control_false_prime` | number theory (prime) | `counterexample_found` | Pass (3/3 runs, 100% accuracy) |
| BVC-016 | `control_false_divisibility` | number theory (divisibility) | `counterexample_found` | Pass (3/3 runs, 100% accuracy) |
| BVC-017 | `control_false_inequality2` | inequality | `counterexample_found` | Pass (3/3 runs, 100% accuracy) |
| BVC-018 | `algebra_sqineq_unitcircatbpamblt1` | inequality | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-019 | `algebra_sqineq_36azm9asqle36zsq` | inequality | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-020 | `mathd_algebra_388` | linear system | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-021 | `mathd_algebra_176` | algebraic identity | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-022 | `mathd_algebra_327` | inequality | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-023 | `mathd_algebra_24` | linear equation | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |

**Measured accuracy: 74/74 correct = 100%** — 5 runs of each of the 4 original executable cases plus 3 runs of each of the 18 expanded cases (see [Accuracy](#accuracy) below for the per-case breakdown and the caveats).

**22 of 23 entries are executable test cases; 1 is included for historical
context only and is explicitly never run or claimed as a Breach result.**
Of the 4 original executable cases, all 4 now pass reliably. 3 passed cleanly on
first validation; 1 (BVC-002) was found to be non-deterministic on first
testing, root-caused, fixed, and re-verified. The 18 expanded cases
(BVC-006 through BVC-023) each passed 3/3 runs on first validation.

## What BVC-002 taught us

Repeated runs of the same command sometimes returned the correct verdict
and sometimes returned an honest `unknown` (classified as
`translation_ambiguity` or `timeout`). The cause: Breach's LLM-driven
translation step occasionally produced a solver encoding that failed to
parse, or chose search bounds wide enough to make the nonlinear
divisibility search time out — and there was no retry or validation step
before reporting the result.

This was **not a false-positive bug** — Breach never returned an
incorrect "true" result, only an honest "I couldn't resolve this, and
here's exactly why." That is the intended behavior of the system's
honesty architecture working correctly under a genuinely hard input. The
fix (validate the generated encoding and retry translation on parse
failure) removed the non-determinism; it did not change Breach's logic
for when to report `unknown` versus a definite verdict.

## What this corpus does *not* claim

- It does not claim Breach can solve open mathematical problems (see
  BVC-004, included only as historical/narrative context — Breach has
  not found that counterexample and the entry is marked accordingly)
- It does not claim deterministic translation in general — only that
  these 23 specific cases are now verified stable
- It is not a replacement for structured testing with working
  mathematicians, which would be the natural next step beyond this
  corpus for broader validation

---

## Accuracy

Measured on this corpus by running every executable case through
`breach check` and comparing each verdict against the expected one —
the 4 original cases 5 times each (20 runs), the 18 expanded cases
3 times each (54 runs).

**Overall: 74/74 correct = 100%.**
Per case: BVC-001–BVC-003 and BVC-005 100% over 5 runs each;
BVC-006–BVC-023 100% over 3 runs each.
Mean wall-clock per check ≈ 13.2s on the original cases (slowest 44.4s);
≈ 7.4s on the expanded cases (slowest 20.4s).

| ID | case | expected verdict | correct | accuracy | observed |
|---|---|---|---|---|---|
| BVC-001 | `amc12_2000_p11` | `no_counterexample_in_bound` | 5/5 | 100% | `no_counterexample_in_bound` × 5 |
| BVC-002 | `mathd_numbertheory_618` | `no_counterexample_in_bound` | 5/5 | 100% | `no_counterexample_in_bound` × 5 |
| BVC-003 | `mathd_algebra_487` | `no_counterexample_in_bound` | 5/5 | 100% | `no_counterexample_in_bound` × 5 |
| BVC-005 | `control_false_inequality` | `counterexample_found` | 5/5 | 100% | `counterexample_found` × 5 |
| BVC-006 | `mathd_algebra_141` | algebraic identity | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-007 | `mathd_algebra_160` | linear system | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-008 | `mathd_algebra_412` | linear system | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-009 | `mathd_algebra_44` | linear system | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-010 | `mathd_algebra_126` | linear equation | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-011 | `mathd_algebra_398` | algebraic identity | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-012 | `mathd_algebra_107` | algebraic identity | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-013 | `mathd_algebra_455` | linear equation | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-014 | `mathd_algebra_440` | linear equation | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-015 | `control_false_prime` | number theory (prime) | `counterexample_found` | Pass (3/3 runs, 100% accuracy) |
| BVC-016 | `control_false_divisibility` | number theory (divisibility) | `counterexample_found` | Pass (3/3 runs, 100% accuracy) |
| BVC-017 | `control_false_inequality2` | inequality | `counterexample_found` | Pass (3/3 runs, 100% accuracy) |
| BVC-018 | `algebra_sqineq_unitcircatbpamblt1` | inequality | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-019 | `algebra_sqineq_36azm9asqle36zsq` | inequality | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-020 | `mathd_algebra_388` | linear system | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-021 | `mathd_algebra_176` | algebraic identity | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-022 | `mathd_algebra_327` | inequality | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |
| BVC-023 | `mathd_algebra_24` | linear equation | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |

Reading these numbers honestly:

- **100% on 22 cases is a small sample, not a benchmark
  result.** It says Breach does not embarrass itself on real, externally-sourced
  mathematics; it does not say Breach is 100% correct in general.
- **A correct verdict is a correct *verdict*, not a proof.** `no_counterexample_in_bound`
  means no counterexample was found inside the searched bound. The corpus
  records the ground truth separately, which is why each case states how that
  truth was established (SymPy simplification, direct substitution, the
  historical record) rather than trusting Breach's own word.
- **The case that counts most is the one that fails honestly.** Across
  74 runs, Breach never produced a *confident wrong* result:
  whenever it could not resolve a claim it said `unknown` and gave the reason.
  A tool that fails loudly is worth more than one that fails quietly.
- **Reproduce it yourself** — the raw per-run measurements are in
  [`accuracy.json`](./accuracy.json), and every command is listed below.

## Reproducing these results

```bash
# BVC-001
breach check "for nonzero reals a and b, if a*b = a - b, then a/b + b/a - a*b = 2"

# BVC-002
breach check "for positive integer n, let p(n) = n^2 - n + 41; if gcd(p(n), p(n+1)) > 1 then n >= 41"

# BVC-003
breach check "if a^2 = b, a + b = 1, c^2 = d, c + d = 1, and a != c, then sqrt((a-c)^2 + (b-d)^2) = sqrt(10)"

# BVC-005
breach check "for all positive integers a and b, a^2 + b^2 >= 2*a*b + 1"

# BVC-006
breach check "for real numbers a and b, if a*b = 180 and a + b = 27, then a^2 + b^2 = 369"

# BVC-007
breach check "for real numbers n and x, if n + x = 97 and n + 5*x = 265, then n + 2*x = 139"

# BVC-008
breach check "for real numbers x and y, if x + y = 25 and x - y = 11, then x = 18"

# BVC-009
breach check "for real numbers s and t, if s = 9 - 2*t and t = 3*s + 1, then s = 1 and t = 4"

# BVC-010
breach check "for real numbers x and y, if 2*3 = x - 9 and 2*(-5) = y + 1, then x = 15 and y = -11"

# BVC-011
breach check "for real numbers a, b, c, if 9*b = 20*c and 7*a = 4*b, then 63*a = 80*c"

# BVC-012
breach check "for real numbers x and y, if x^2 + 8*x + y^2 - 6*y = 0, then (x + 4)^2 + (y - 3)^2 = 25"

# BVC-013
breach check "if 2*(2*(2*(2*x))) = 48, then x = 3"

# BVC-014
breach check "if 3/2/3 = x/10, then x = 5"

# BVC-015
breach check "for all integers n between 1 and 40, n^2 + n + 41 is prime"

# BVC-016
breach check "for all integers n, n^2 - n is never divisible by 6"

# BVC-017
breach check "for all positive integers a and b, a^2 + b^2 >= 2*a*b + 2"

# BVC-018
breach check "for all real numbers a and b, if a^2 + b^2 = 1, then a*b + (a - b) <= 1"

# BVC-019
breach check "for all real numbers z and a, 36*(a*z) - 9*a^2 <= 36*z^2"

# BVC-020
breach check "for real numbers x, y, z, if 3*x + 4*y - 12*z = 10 and -2*x - 3*y + 9*z = -4, then x = 14"

# BVC-021
breach check "for all real numbers a, (a + 1)^2 * a = a^3 + 2*a^2 + a"

# BVC-022
breach check "for all real numbers x, (1/5)*abs(9 + 2*x) < 1 implies -7 < x and x < -2"

# BVC-023
breach check "for real numbers x, if x/50 = 40, then x = 2000"
```

Run each a few times — stable, repeated results across multiple runs is
itself part of what this corpus checks for, not just a single pass/fail.
