# Changelog

All notable changes to Breach.

## Unreleased — validation corpus, translation robustness

### Added
- **`validation/VALIDATION.md` + `validation/validation_corpus.json`** — a small
  curated corpus (5 entries, 4 executable) for validating Breach against
  externally-sourced mathematical statements (miniF2F) rather than only
  self-authored problems. BVC-004 (the Pólya conjecture) is included as
  historical context only and is never run or claimed as a Breach result.
- **Translation validation with automatic retry** (`engine.py`) — a generated
  encoding is now *checked* before it reaches the solver: the claim expression
  and every constraint must actually parse in the backend that will run them.
  If they do not, the model is asked again with the error, up to
  `MAX_TRANSLATION_ATTEMPTS` (3) times.
- **Retry on solver timeout** — if the encoding parses but the solver cannot
  cope with it (typically a too-wide search space on a nonlinear divisibility
  check), Breach asks for a tighter encoding and tries again before reporting
  an unknown.

### Fixed
- **BVC-002 (`mathd_numbertheory_618`) was non-deterministic.** Repeated runs
  of the same command sometimes returned `no_counterexample_in_bound` and
  sometimes an honest `unknown` (classified `translation_ambiguity` when the
  generated encoding did not parse, or `timeout` when the search bounds were
  too wide for the nonlinear divisibility search). There was no validation or
  retry step before reporting the result.

  This was **not a false-positive bug** — Breach never returned an incorrect
  "true" result, only an honest "I could not resolve this, and here is
  exactly why". The fix removes the non-determinism; it does not change when
  Breach reports `unknown` versus a definite verdict.

### Not changed
- The honesty architecture is untouched: an unresolved claim is still reported
  as an unresolved claim, with its reason and a confidence score.
- No solver logic was changed to make the corpus pass. The four runnable cases
  were already returning correct verdicts; what changed is that a broken
  encoding is now rejected and re-generated instead of being reported.
