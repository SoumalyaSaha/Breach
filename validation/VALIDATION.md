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
| BVC-001 | `amc12_2000_p11` | algebraic identity | `no_counterexample_in_bound` | ✅ Pass (3/3 runs) |
| BVC-002 | `mathd_numbertheory_618` | number theory (gcd) | `no_counterexample_in_bound` | ⚠️ Initially flaky → ✅ Fixed |
| BVC-003 | `mathd_algebra_487` | algebraic system | `no_counterexample_in_bound` | ✅ Pass (3/3 runs) |
| BVC-004 | Pólya conjecture (1919) | historical context only | n/a | Not executed — citation only |
| BVC-005 | control inequality | counterexample control | `counterexample_found` | ✅ Pass (3/3 runs) |

**4 of 5 entries are executable test cases; 1 is included for historical
context only and is explicitly never run or claimed as a Breach result.**
Of the 4 executable cases, all 4 now pass reliably. 3 passed cleanly on
first validation; 1 (BVC-002) was found to be non-deterministic on first
testing, root-caused, fixed, and re-verified.

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
  these 4 specific cases are now verified stable
- It is not a replacement for structured testing with working
  mathematicians, which would be the natural next step beyond this
  corpus for broader validation

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
```

Run each a few times — stable, repeated results across multiple runs is
itself part of what this corpus checks for, not just a single pass/fail.
