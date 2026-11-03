# miniF2F source (upstream benchmark, vendored)

The `.lean` files in `lean/src/` are **not Breach code**. They are the Lean 4
source of the miniF2F benchmark, vendored here verbatim for provenance of the
validation corpus in [`validation/`](../validation/):

- `lean/src/valid.lean` — the miniF2F *valid* split (244 theorems)
- `lean/src/test.lean` — the miniF2F *test* split (244 theorems)
- `lean/src/minif2f_import.lean` — shared imports

**Source:** [openai/miniF2F](https://github.com/openai/miniF2F) (upstream).
**Citation:** Zheng, Han, Polu. "miniF2F: a cross-system benchmark for formal
Olympiad-level mathematics." arXiv:2109.00110.
**License:** Apache License 2.0 — see [`lean/LICENSE`](lean/LICENSE); the
upstream license text is carried along as required.

Breach does not compile, depend on, or execute these files. Breach verifies
claims with Z3 and SymPy (see `src/solver.py`); the miniF2F sources are
included only so a reader can trace each corpus entry (e.g. `mathd_algebra_141`)
back to its original theorem statement.
