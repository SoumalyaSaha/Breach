"""Breach — an adversarial math-checking agent.

Core rule: the LLM only *translates* language into structured, checkable input.
All verification is done by deterministic solvers (Z3 / SymPy). "Trust the
solver, not the LLM's reasoning."
"""

__version__ = "0.1.0"
