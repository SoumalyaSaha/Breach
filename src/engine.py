"""Stage 3 — The core engine.

Three jobs:

1. `translate_claim`  — turn informal math into a structured, solver-checkable
   form. The LLM is used *only* here (and for explanation), never as the
   source of truth.
2. `run_solver`      — hand that structure to a deterministic solver (Z3 /
   SymPy / a bounded arithmetic search) and report one of three verdicts:
   counterexample found / no counterexample in bound / unknown.
3. `breach_check`    — orchestrate translate -> memory -> solve -> ProofState.

Honesty rules encoded here:
* a counterexample is only ever reported when a solver produced a model;
* "no counterexample found" is always scoped to the searched bound;
* "unknown" is *scored* — we say why the solver stopped and how confident we
  are (timeout / undecidable / translation ambiguity / ...).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .llm_client import LLMClient, LLMError, LLMUnavailable, get_client
from .memory import ProofMemory, make_key
from .state import ProofState, ProofStep, UnknownInfo

SOLVER_TIMEOUT_SECONDS = 10.0
SAFE_EXPR = re.compile(r"^[A-Za-z0-9_+\-*/%^()<>=!&|.,\s'\[\]]+$")


# ---------------------------------------------------------------------------
# Structured symbolic form
# ---------------------------------------------------------------------------
@dataclass
class Variable:
    name: str
    type: str = "int"  # "int" | "real"
    lower: Optional[float] = None
    upper: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SymbolicForm:
    backend: str = "z3"  # "z3" | "sympy" | "mitm" (bounded sum-of-powers search)
    claim_kind: str = "universal"  # "universal" | "existential" | "existential_sweep"
    variables: list[Variable] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    claim_expr: str = ""
    steps: list[str] = field(default_factory=list)
    scope_note: str = ""
    confidence: float = 0.6
    ambiguity: str = ""
    search_space: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["variables"] = [v.to_dict() for v in self.variables]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SymbolicForm":
        data = dict(data or {})
        variables = [Variable(**v) for v in data.pop("variables", []) or []]
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(variables=variables, **filtered)

    def pretty(self) -> str:
        lines = [f"backend: {self.backend}", f"claim: {self.claim_expr}"]
        if self.variables:
            vs = ", ".join(
                f"{v.name}:{v.type}"
                + (f"[{v.lower},{v.upper}]" if v.lower is not None else "")
                for v in self.variables
            )
            lines.append(f"variables: {vs}")
        if self.constraints:
            lines.append("constraints: " + " ∧ ".join(self.constraints))
        if self.steps:
            lines.append("steps:")
            lines.extend(f"  {i+1}. {s}" for i, s in enumerate(self.steps))
        return "\n".join(lines)


@dataclass
class SolverResult:
    verdict: str  # counterexample_found | no_counterexample_in_bound | unknown
    counterexample: Optional[dict[str, Any]] = None
    unknown_info: Optional[UnknownInfo] = None
    raw: str = ""
    elapsed: float = 0.0
    backend: str = ""


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------
TRANSLATE_PROMPT = """You translate informal mathematical claims into a STRUCTURED form
that a computer solver (Z3 SMT solver, or SymPy algebra) can check mechanically.

You must output ONLY a JSON object, no prose, no markdown fence:

{
  "backend": "z3" | "sympy",
  "claim_kind": "universal" | "existential",
  "variables": [{"name": "x", "type": "int" | "real", "lower": 0, "upper": 10}],
  "constraints": ["x >= 0", "x <= 10"],
  "claim_expr": "x * x >= 0",
  "steps": ["short English description of each step of the argument"],
  "scope_note": "what part of the claim is actually machine-checkable here",
  "confidence": 0.0-1.0,
  "ambiguity": "if the claim is ambiguous or under-specified, say exactly how; else empty"
}

RULES (these matter, follow them exactly):
1. `constraints` are the ASSUMPTIONS plus the SEARCH DOMAIN. Every free variable
   that is searched over MUST have a finite, explicit bound (integers) or a finite
   interval (reals). A claim with no explicit bound should get a small default
   bound (integers: -50..50 unless the claim suggests otherwise; reals: -10..10).
2. `claim_expr` is a BOOLEAN predicate over the DECLARED variables that must be
   TRUE for the claim to hold at that point. A COUNTEREXAMPLE is an assignment
   of the declared variables satisfying all `constraints` where `claim_expr` is
   FALSE.
   - "for all integers n, n^2 >= 0"  ->  claim_expr: "n * n >= 0"
   - "there are no positive solutions to x^2 + y^2 = z^2 with x,y,z <= 50"
     ->  claim_expr: "Not(x * x + y * y == z * z)"   (x, y, z are declared)
   - "n^2 + n + 41 is prime for every n in 1..40"
     ->  declare n and d, then claim_expr: "Not(And(d >= 2, d <= 41, Mod(n*n + n + 41, d) == 0))"
3. DO NOT use ForAll / Exists / quantified formulas. The search already ranges
   over every declared variable; a quantifier would hide the witness from the
   report. If the claim is an existence claim ("there exists ...") set
   "claim_kind": "existential" and write the witness condition directly.
4. Use `**` for powers, `Mod(a, b)` for remainder. Use `And`, `Or`, `Not`,
   `Implies` for logic. Never use Python's `or`/`and` inside an expression —
   use `Or(...)` / `And(...)`.
5. NO unbounded quantifiers: every variable that is searched over MUST be
   declared with a finite bound.
6. Primality cannot be expressed directly. Expand it into an explicit
   disjunction over the bounded range, e.g. "Or(x == 101, x == 103)", or use the
   divisor pattern shown in rule 2.
7. SUMMATIONS and closed forms: if the claim involves "the sum of ...",
   use backend "sympy" and write it as Sum(k * k, (k, 1, n)) — the solver
   evaluates sums symbolically. Never restate one side as the other; both
   sides must be the actual expressions from the claim.
8. DIVISION: if the expression contains '/', declare the variables involved
   with type "real" — integer division truncates and manufactures fake
   counterexamples (e.g. 10/9 + 9/10 truncating to 1 + 0).
8. If the claim is a famous open problem that no solver can check (Navier-Stokes,
   Collatz, the Riemann hypothesis, P vs NP, ...), DO NOT invent a translation.
   Instead return: backend "sympy", variables [], constraints [], claim_expr "",
   confidence 0.0, and put the reason in `scope_note` and `ambiguity`.
9. `steps` should be the human-readable decomposition of the argument, in order.
10. Output JSON only."""

SCOPE_PROMPT = """You are a careful mathematician assessing whether a claim is
MACHINE-CHECKABLE with a bounded SMT solver or computer algebra.

Claim: {claim}
Structured form: {form}

Answer with ONLY a JSON object:
{{"checkable": true|false,
  "kind": "timeout" | "undecidable" | "translation_ambiguity" | "unsupported_backend",
  "confidence": 0.0-1.0,
  "detail": "one plain sentence a non-expert can understand",
  "remedy": "what would need to change for the solver to resolve this"}}

Guidance:
- "timeout": the solver ran out of time; more time or tighter bounds might fix it.
- "undecidable": the claim is outside what solvers can decide (real-valued
  analysis, unbounded quantifiers, famous open problems). No amount of time helps.
- "translation_ambiguity": the statement itself is vague/ambiguous, or the
  formalisation is uncertain — the machine cannot check what was not pinned down.
- "unsupported_backend": the claim needs arithmetic the chosen backend cannot express."""


def _safe_eval(expr: str, namespace: dict[str, Any]) -> Any:
    """Evaluate a restricted expression from the model against `namespace`."""
    expr = expr.strip()
    if not expr:
        raise ValueError("empty expression")
    if not SAFE_EXPR.match(expr):
        raise ValueError(f"expression contains disallowed characters: {expr!r}")
    if "__" in expr:
        raise ValueError("dunder names are not allowed")
    return eval(expr, {"__builtins__": {}}, namespace)  # noqa: S307 - restricted


#: How many times we let the LLM re-translate a claim when the encoding it
#: produced cannot be used (unparseable) or the solver cannot cope with it.
MAX_TRANSLATION_ATTEMPTS = 3


def translate_claim(
    claim_text: str,
    client: Optional[LLMClient] = None,
    memory: Optional[ProofMemory] = None,
    feedback: str = "",
    use_cache: bool = True,
) -> SymbolicForm:
    """Translate an informal claim into a structured, checkable form.

    The generated encoding is *validated* (it must actually parse in the
    backend that will run it). If it does not, the model is asked again with
    the error, up to `MAX_TRANSLATION_ATTEMPTS` times.
    """
    key = make_key(claim_text, "translate")
    if memory is not None and use_cache:
        cached = memory.read(key)
        if cached is not None:
            return SymbolicForm.from_dict(cached)

    client = client or get_client()
    form: Optional[SymbolicForm] = None
    last_error = ""
    try:
        for attempt in range(MAX_TRANSLATION_ATTEMPTS):
            user_msg = f"Claim: {claim_text}"
            if feedback:
                user_msg += (
                    "\n\nYour previous attempt did not work: "
                    f"{feedback}\n"
                    "Produce a corrected encoding. Keep the search bounds small enough "
                    "that the solver can finish, and use only the variable names you "
                    "declare."
                )
            payload, _ = client.chat_json(
                [
                    {"role": "system", "content": TRANSLATE_PROMPT},
                    {"role": "user", "content": user_msg},
                ]
            )
            candidate = SymbolicForm.from_dict(payload)
            if candidate.claim_expr:
                candidate = _validate_form(candidate)
            form = candidate
            problem = _encoding_problem(candidate)
            if problem is None:
                break
            last_error = problem
            feedback = problem
        if form is None:
            raise LLMError("no translation produced")
    except (LLMUnavailable, LLMError, ValueError, KeyError, TypeError) as exc:
        form = offline_translate(claim_text) or SymbolicForm(
            backend="sympy",
            variables=[],
            constraints=[],
            claim_expr="",
            confidence=0.0,
            ambiguity=(
                f"The claim could not be formalised automatically ({exc})."
                + (f" Last encoding problem: {last_error}" if last_error else "")
            ),
            scope_note="No machine-checkable formalisation was produced.",
        )

    if memory is not None and use_cache:
        memory.write(key, form.to_dict(), source="engine.translate_claim")
    return form


def _encoding_problem(form: SymbolicForm) -> Optional[str]:
    """Return why the encoding is unusable, or None when it is fine.

    An empty claim expression is *not* a problem: that is how a claim outside
    Breach's scope is represented (and it is reported honestly, not retried).
    """
    if not form.claim_expr.strip():
        return None
    try:
        if form.backend == "sympy":
            import sympy

            syms = {
                v.name: sympy.Symbol(v.name, integer=(v.type == "int"))
                for v in form.variables
            }
            _sympify_claim(form.claim_expr, syms)
            for c in form.constraints:
                _sympify_claim(c, syms)
        else:
            ns, _consts = _z3_namespace(form)
            _safe_eval(form.claim_expr, ns)
            for c in form.constraints:
                _safe_eval(c, ns)
    except Exception as exc:  # noqa: BLE001 - any parse problem is a retry
        return f"the encoding could not be parsed by the solver: {exc}"
    return None


def _validate_form(form: SymbolicForm) -> SymbolicForm:
    """Sanity-check the model output before we trust it with a solver."""
    names = [v.name for v in form.variables]
    if len(set(names)) != len(names):
        form.variables = []
    for v in form.variables:
        if v.type not in ("int", "real"):
            v.type = "int"
    form.constraints = [c for c in form.constraints if isinstance(c, str) and c.strip()]
    if form.claim_kind not in ("universal", "existential", "existential_sweep"):
        form.claim_kind = "universal"
    if form.confidence is None:
        form.confidence = 0.5
    form.confidence = max(0.0, min(1.0, float(form.confidence)))
    if not form.claim_expr.strip():
        form.ambiguity = form.ambiguity or "The claim did not yield a checkable expression."
        form.confidence = min(form.confidence, 0.2)
    else:
        tautology = _is_tautology(form.claim_expr)
        if tautology:
            form.ambiguity = (
                "The formalisation reduced the claim to a tautology (both sides are the "
                "same expression), so the solver would be checking nothing."
            )
            form.confidence = min(form.confidence, 0.25)
    return form


def _is_tautology(claim_expr: str) -> bool:
    """True if `a == a` — the translation checks nothing at all."""
    lhs, rhs = _split_top_level(claim_expr, "==")
    if lhs is None or rhs is None:
        return False
    norm = lambda s: re.sub(r"\s+", "", s)  # noqa: E731
    return norm(lhs) == norm(rhs) and lhs.strip() != ""


# ---------------------------------------------------------------------------
# Offline heuristic translator (no LLM available)
# ---------------------------------------------------------------------------
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def offline_translate(claim_text: str) -> Optional[SymbolicForm]:
    """Very small rule-based translator used when no LLM provider is available.

    It handles the common shapes: "for all integers n, <predicate>", "there is
    no integer ... such that <predicate>", and simple equations with bounded
    variables. Anything else returns None so we report an honest unknown.
    """
    text = claim_text.strip().lower()
    if not text:
        return None

    # "for all/every integer(s) <v> , <expr>"  (also "for all <v> in integers")
    m = re.search(
        r"for\s+(?:all|every)\s+(?:integers?|naturals?|reals?)\s+([a-z])\b\s*[:,]?\s*(.+)",
        text,
    )
    if m:
        var, body = m.group(1), m.group(2)
        pred = _relational_to_predicate(body)
        if pred:
            lower, upper = (0, 50) if "natural" in text else (-50, 50)
            return SymbolicForm(
                backend="z3",
                variables=[Variable(var, "int", lower, upper)],
                constraints=[f"{var} >= {lower}", f"{var} <= {upper}"],
                claim_expr=pred,
                steps=[f"For every {var} in [{lower}, {upper}], {body.strip()}"],
                scope_note=(
                    f"Checked exhaustively for integer {var} in [{lower}, {upper}]. "
                    "This is a bounded check, not a proof for all integers."
                ),
                confidence=0.45,
            )

    # "there is/are no integer(s) <v> ... <expr>"
    m = re.search(r"there\s+(?:is|are)\s+no\s+(?:integers?|positive integers?)\s+([a-z])\b\s*(.+)", text)
    if m:
        var, body = m.group(1), m.group(2)
        pred = _relational_to_predicate(body)
        if pred:
            return SymbolicForm(
                backend="z3",
                variables=[Variable(var, "int", 1, 50)],
                constraints=[f"{var} >= 1", f"{var} <= 50"],
                claim_expr=f"Not({pred})",
                steps=[f"No integer {var} in [1,50] satisfies: {body.strip()}"],
                scope_note="Bounded to 1..50 — a witness outside this range would not be found.",
                confidence=0.4,
            )
    return None


def _relational_to_predicate(body: str) -> Optional[str]:
    """Turn 'x^2 >= 0' / 'x^2 + y^2 = z^2' into a boolean Z3 expression."""
    body = body.strip().rstrip(".").strip()
    body = body.replace("^", "**")
    # normalise words
    body = re.sub(r"\bis\b", "==", body)
    body = re.sub(r"\bequals\b", "==", body)
    body = re.sub(r"\bnot equal(?:s)?\b", "!=", body)
    body = re.sub(r"\bless than or equal\b", "<=", body)
    body = re.sub(r"\bgreater than or equal\b", ">=", body)
    body = re.sub(r"\bless than\b", "<", body)
    body = re.sub(r"\bgreater than\b", ">", body)
    if not re.search(r"(==|!=|<=|>=|<|>)", body):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_+\-*/%^()=<>!.\s,]+", body):
        return None
    return body


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------
def _z3_namespace(form: SymbolicForm):
    import z3

    ns: dict[str, Any] = {}
    for name in (
        "And", "Or", "Not", "Xor", "Implies", "Exists", "ForAll", "If",
        "RealVal", "IntVal", "Abs", "Bool", "BoolVal",
    ):
        fn = getattr(z3, name, None)
        if fn is not None:
            ns[name] = fn
    # Some z3 builds do not expose Mod/Div as functions; `%` works on ArithRef.
    ns.setdefault("Mod", lambda a, b: a % b)
    ns.setdefault("Div", lambda a, b: a / b)
    consts = {}
    for v in form.variables:
        c = z3.Int(v.name) if v.type == "int" else z3.Real(v.name)
        consts[v.name] = c
        ns[v.name] = c
    return ns, consts


def _extract_model(model, consts) -> dict[str, Any]:
    import z3

    out: dict[str, Any] = {}
    for name, c in consts.items():
        try:
            value = model.eval(c, model_completion=True)
            if z3.is_int_value(value):
                out[name] = value.as_long()
            elif z3.is_rational_value(value):
                out[name] = float(value.numerator_as_long()) / float(value.denominator_as_long())
            else:
                out[name] = str(value)
        except Exception:  # pragma: no cover
            continue
    # Any extra constant in the model is a solver-side witness (e.g. the
    # skolem of an existential quantifier) — report it instead of hiding it.
    try:
        for decl in model.decls():
            name = decl.name()
            if name in out:
                continue
            value = model.eval(decl())
            if z3.is_int_value(value):
                out[f"witness_{name}"] = value.as_long()
            elif z3.is_rational_value(value):
                out[f"witness_{name}"] = (
                    float(value.numerator_as_long()) / float(value.denominator_as_long())
                )
    except Exception:  # pragma: no cover
        pass
    return out


def run_solver(
    form: SymbolicForm,
    timeout: float = SOLVER_TIMEOUT_SECONDS,
    extra_constraints: Optional[list[str]] = None,
) -> SolverResult:
    """Run the appropriate deterministic backend. Never raises."""
    started = time.time()
    backend = (form.backend or "z3").lower()
    extra = extra_constraints or []
    try:
        if backend == "mitm":
            from .powers import solve_sum_of_powers

            return solve_sum_of_powers(form, timeout=timeout)
        if backend == "sympy":
            return _run_sympy(form, timeout=timeout)
        return _run_z3(form, timeout=timeout, extra=extra)
    except Exception as exc:  # noqa: BLE001 - never crash the app
        return SolverResult(
            verdict="unknown",
            unknown_info=UnknownInfo(
                kind="solver_error",
                confidence=0.95,
                detail=f"The solver raised an error: {exc}",
                remedy="Adjust the formalisation and try again.",
            ),
            raw=str(exc),
            elapsed=time.time() - started,
            backend=backend,
        )


def _run_z3(form: SymbolicForm, timeout: float = SOLVER_TIMEOUT_SECONDS, extra: Optional[list[str]] = None) -> SolverResult:
    import z3

    started = time.time()
    ns, consts = _z3_namespace(form)
    constraints = list(form.constraints) + list(extra or [])

    if not form.claim_expr.strip():
        out_of_scope = "out of scope" in (form.scope_note or "").lower()
        return SolverResult(
            verdict="unknown",
            unknown_info=UnknownInfo(
                kind="undecidable" if out_of_scope else "translation_ambiguity",
                confidence=0.85 if out_of_scope else 0.6,
                detail=(
                    form.scope_note
                    or "No checkable expression could be extracted from the claim."
                )
                + (
                    " No amount of solver time helps here — the statement is outside "
                    "the class of problems mechanical verification can decide."
                    if out_of_scope
                    else ""
                ),
                remedy=(
                    "This claim is not mechanically verifiable. It needs a human argument "
                    "or a different, bounded formulation."
                    if out_of_scope
                    else "Rephrase the claim, or draw it on the blackboard so it can be transcribed."
                ),
            ),
            elapsed=time.time() - started,
            backend="z3",
        )

    try:
        claim = _safe_eval(form.claim_expr, ns)
    except Exception as exc:
        return SolverResult(
            verdict="unknown",
            unknown_info=UnknownInfo(
                kind="unsupported_backend",
                confidence=0.8,
                detail=f"The formalised claim could not be read by the solver ({exc}).",
                remedy="Simplify the statement or re-translate it.",
            ),
            raw=str(exc),
            elapsed=time.time() - started,
            backend="z3",
        )

    if not z3.is_bool(claim):
        return SolverResult(
            verdict="unknown",
            unknown_info=UnknownInfo(
                kind="unsupported_backend",
                confidence=0.85,
                detail="The claim did not formalise into a boolean proposition.",
                remedy="State the claim as a proposition that is either true or false.",
            ),
            elapsed=time.time() - started,
            backend="z3",
        )

    solver = z3.Solver()
    solver.set("timeout", int(timeout * 1000))
    for c in constraints:
        try:
            solver.add(_safe_eval(c, ns))
        except Exception as exc:
            return SolverResult(
                verdict="unknown",
                unknown_info=UnknownInfo(
                    kind="translation_ambiguity",
                    confidence=0.7,
                    detail=f"One constraint could not be parsed: {c!r} ({exc}).",
                    remedy="Rephrase the assumption in plain arithmetic.",
                ),
                elapsed=time.time() - started,
                backend="z3",
            )

    try:
        if form.claim_kind == "existential":
            solver.add(claim)
        elif form.claim_kind == "existential_sweep":
            return _sweep_existential(form, ns, consts, timeout=timeout)
        else:
            solver.add(z3.Not(claim))
        result = solver.check()
    except z3.Z3Exception as exc:
        return SolverResult(
            verdict="unknown",
            unknown_info=UnknownInfo(
                kind="unsupported_backend",
                confidence=0.8,
                detail=f"The solver rejected the formalisation ({exc}).",
                remedy="Try a more explicit formulation.",
            ),
            raw=str(exc),
            elapsed=time.time() - started,
            backend="z3",
        )

    elapsed = time.time() - started
    if form.claim_kind == "existential":
        # The claim says "there exists a witness". SAT means the claim holds.
        if result == z3.sat:
            return SolverResult(
                verdict="no_counterexample_in_bound",
                counterexample=None,
                raw="witness found — the existential claim holds in the searched bound",
                elapsed=elapsed,
                backend="z3",
            )
        if result == z3.unsat:
            return SolverResult(
                verdict="counterexample_found",
                counterexample={
                    "note": "no witness exists in the searched bound, so the existential claim is false here"
                },
                raw="unsat",
                elapsed=elapsed,
                backend="z3",
            )
    elif result == z3.sat:
        model = solver.model()
        return SolverResult(
            verdict="counterexample_found",
            counterexample=_extract_model(model, consts),
            raw=str(model),
            elapsed=elapsed,
            backend="z3",
        )
    elif result == z3.unsat:
        return SolverResult(
            verdict="no_counterexample_in_bound",
            raw="unsat",
            elapsed=elapsed,
            backend="z3",
        )
    reason = solver.reason_unknown() if hasattr(solver, "reason_unknown") else ""
    kind = "timeout" if "timeout" in (reason or "").lower() else "undecidable"
    return SolverResult(
        verdict="unknown",
        unknown_info=UnknownInfo(
            kind=kind,  # type: ignore[arg-type]
            confidence=0.9 if kind == "timeout" else 0.7,
            detail=(
                "The solver ran out of time before it could decide the question."
                if kind == "timeout"
                else f"The solver could not decide this fragment ({reason or 'incomplete quantifier elimination'})."
            ),
            remedy=(
                "Give it a larger timeout or a tighter search bound."
                if kind == "timeout"
                else "No extra time helps — the statement lies outside what this solver decides."
            ),
        ),
        raw=reason,
        elapsed=elapsed,
        backend="z3",
    )


def _sweep_existential(form, ns, consts, timeout: float = 10.0) -> "SolverResult":
    """Check a family of existential claims, one value of the sweep variable at
    a time ("for every n in range, does a witness exist?").

    A counterexample is a value of the sweep variable with no witness.
    """
    import z3

    started = time.time()
    space = form.search_space or {}
    sweep_var = space.get("sweep_var")
    lower = int(space.get("lower", 0))
    upper = int(space.get("upper", 0))
    step = int(space.get("step", 1))
    if not sweep_var or sweep_var not in ns:
        return SolverResult(
            verdict="unknown",
            unknown_info=UnknownInfo(
                kind="unsupported_backend",
                confidence=0.8,
                detail="The sweep variable is not declared, so the family cannot be checked.",
                remedy="Declare the swept variable in the formalisation.",
            ),
            elapsed=time.time() - started,
            backend="z3",
        )
    try:
        claim = _safe_eval(form.claim_expr, ns)
    except Exception as exc:
        return SolverResult(
            verdict="unknown",
            unknown_info=UnknownInfo(
                kind="unsupported_backend",
                confidence=0.8,
                detail=f"The swept claim could not be read by the solver ({exc}).",
                remedy="Simplify the statement.",
            ),
            elapsed=time.time() - started,
            backend="z3",
        )

    checked = 0
    for value in range(lower, upper + 1, step):
        if time.time() - started > timeout:
            return SolverResult(
                verdict="unknown",
                unknown_info=UnknownInfo(
                    kind="timeout",
                    confidence=0.9,
                    detail=f"The sweep was cut off after {checked} values.",
                    remedy="Reduce the swept range or raise the timeout.",
                ),
                elapsed=time.time() - started,
                backend="z3",
            )
        solver = z3.Solver()
        solver.set("timeout", int(max(1.0, timeout) * 1000))
        try:
            for c in form.constraints:
                solver.add(_safe_eval(c, ns))
            solver.add(ns[sweep_var] == value)
            solver.add(claim)
        except Exception as exc:  # noqa: BLE001
            return SolverResult(
                verdict="unknown",
                unknown_info=UnknownInfo(
                    kind="translation_ambiguity",
                    confidence=0.7,
                    detail=f"The swept claim could not be assembled ({exc}).",
                    remedy="Rephrase the claim in plain arithmetic.",
                ),
                elapsed=time.time() - started,
                backend="z3",
            )
        checked += 1
        result = solver.check()
        if result == z3.unsat:
            return SolverResult(
                verdict="counterexample_found",
                counterexample={
                    sweep_var: value,
                    "note": f"no witness exists for {sweep_var} = {value} inside the searched bound",
                },
                raw=f"unsat at {sweep_var}={value}",
                elapsed=time.time() - started,
                backend="z3",
            )
        if result == z3.unknown:
            reason = solver.reason_unknown()
            return SolverResult(
                verdict="unknown",
                unknown_info=UnknownInfo(
                    kind="timeout" if "timeout" in (reason or "").lower() else "undecidable",
                    confidence=0.8,
                    detail=f"The solver stopped at {sweep_var} = {value} ({reason}).",
                    remedy="Narrow the range and try again.",
                ),
                elapsed=time.time() - started,
                backend="z3",
            )
    return SolverResult(
        verdict="no_counterexample_in_bound",
        raw=f"checked {checked} values, every one had a witness",
        elapsed=time.time() - started,
        backend="z3",
    )


def _run_sympy(form: SymbolicForm, timeout: float = SOLVER_TIMEOUT_SECONDS) -> SolverResult:
    import sympy

    started = time.time()
    if not form.claim_expr.strip():
        out_of_scope = "out of scope" in (form.scope_note or "").lower()
        return SolverResult(
            verdict="unknown",
            unknown_info=UnknownInfo(
                kind="undecidable" if out_of_scope else "translation_ambiguity",
                confidence=0.85 if out_of_scope else 0.6,
                detail=(
                    (form.scope_note or "No symbolic expression could be extracted from the claim.")
                    + (
                        " No amount of solver time helps here — the statement is outside "
                        "the class of problems mechanical verification can decide."
                        if out_of_scope
                        else ""
                    )
                ),
                remedy=(
                    "This claim is not mechanically verifiable. It needs a human argument "
                    "or a different, bounded formulation."
                    if out_of_scope
                    else "Rephrase the claim more precisely."
                ),
            ),
            elapsed=time.time() - started,
            backend="sympy",
        )
    try:
        syms = {
            v.name: sympy.Symbol(v.name, integer=(v.type == "int"))
            for v in form.variables
        }
        expr = _sympify_claim(form.claim_expr, syms)
    except Exception as exc:  # noqa: BLE001
        return SolverResult(
            verdict="unknown",
            unknown_info=UnknownInfo(
                kind="unsupported_backend",
                confidence=0.75,
                detail=f"SymPy could not parse the statement ({exc}).",
                remedy="Rewrite the claim using standard algebraic notation.",
            ),
            raw=str(exc),
            elapsed=time.time() - started,
            backend="sympy",
        )

    decision = _sympy_decide(expr)
    if decision is True:
        return SolverResult(
            verdict="no_counterexample_in_bound",
            raw="symbolically true",
            elapsed=time.time() - started,
            backend="sympy",
        )

    # Not decided symbolically — look for a concrete violating point inside
    # the declared bound (this is what turns "unknown" into a real witness).
    witness, scanned, scan_note = _bounded_scan(form, expr, timeout=max(timeout, 5.0))
    if witness is not None:
        return SolverResult(
            verdict="counterexample_found",
            counterexample=witness,
            raw=f"numeric scan over {scanned} points",
            elapsed=time.time() - started,
            backend="sympy",
        )

    if decision is False:
        return SolverResult(
            verdict="unknown",
            unknown_info=UnknownInfo(
                kind="undecidable",
                confidence=0.7,
                detail=(
                    "SymPy showed the statement is not an identity, but no concrete "
                    f"violating point was found inside the bound ({scan_note})."
                ),
                remedy="Widen the bound, or give the claim as a proposition a solver can decide.",
            ),
            elapsed=time.time() - started,
            backend="sympy",
        )

    return SolverResult(
        verdict="unknown",
        unknown_info=UnknownInfo(
            kind="undecidable",
            confidence=0.65,
            detail=(
                "SymPy simplified the statement but could not decide whether it holds"
                + (f" ({scan_note})" if scan_note else "")
                + "."
            ),
            remedy="This needs a human argument or a bounded numerical search.",
        ),
        elapsed=time.time() - started,
        backend="sympy",
    )


def _split_top_level(text: str, op: str) -> tuple[Optional[str], Optional[str]]:
    """Split `text` on the first `op` that is not inside brackets."""
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and text.startswith(op, i):
            return text[:i], text[i + len(op) :]
        i += 1
    return None, None


def _rewrite_comparisons(text: str) -> str:
    """Turn `a == b` into `Eq(a, b)` (and friends) so SymPy sees a proposition.

    SymPy's `__eq__` returns a plain bool, so a naive parse would silently
    evaluate the comparison instead of building it.
    """
    for op, fn in (("==", "Eq"), ("!=", "Ne"), ("<=", "Le"), (">=", "Ge")):
        lhs, rhs = _split_top_level(text, op)
        if lhs is not None and rhs is not None:
            return f"{fn}({lhs}, {rhs})"
    for op, fn in (("<", "Lt"), (">", "Gt")):
        lhs, rhs = _split_top_level(text, op)
        if lhs is not None and rhs is not None:
            return f"{fn}({lhs}, {rhs})"
    return text


def _sympify_claim(text: str, syms: dict[str, Any]):
    """Parse a claim into a SymPy expression, keeping comparisons as propositions."""
    import sympy
    from sympy.parsing.sympy_parser import parse_expr, standard_transformations

    local: dict[str, Any] = dict(syms)
    for name in (
        "Sum", "Product", "Integral", "Eq", "Ne", "Lt", "Le", "Gt", "Ge",
        "sqrt", "pi", "E", "I", "oo", "Rational", "factorial", "binomial",
        "exp", "log", "sin", "cos", "tan", "abs", "Abs", "Matrix", "Symbol",
        "Function", "Lambda", "And", "Or", "Not", "simplify", "expand",
    ):
        local[name] = getattr(sympy, name, None)

    rewritten = _rewrite_comparisons(text)
    return parse_expr(
        rewritten,
        local_dict=local,
        transformations=standard_transformations,
        evaluate=True,
    )


def _sympy_decide(expr):
    """Try to decide a SymPy expression symbolically.

    Returns True / False / None (undecided). Sums and integrals are evaluated
    with `doit()` first so closed forms are reachable.
    """
    import sympy

    try:
        if expr is sympy.true:
            return True
        if expr is sympy.false:
            return False
        if isinstance(expr, sympy.logic.boolalg.BooleanAtom):
            return bool(expr)
    except Exception:
        return None

    candidates = [expr]
    if isinstance(expr, sympy.Equality):
        candidates.append(expr.lhs - expr.rhs)
    elif isinstance(expr, (sympy.Lt, sympy.Le, sympy.Gt, sympy.Ge)):
        candidates.append(expr.lhs - expr.rhs)

    for candidate in candidates:
        try:
            reduced = candidate.doit() if hasattr(candidate, "doit") else candidate
        except Exception:
            reduced = candidate
        for attempt in (reduced, sympy.expand(reduced)):
            try:
                s = sympy.simplify(attempt)
            except Exception:
                continue
            try:
                if s is sympy.true or s == 0:
                    return True
                if s is sympy.false:
                    return False
                if isinstance(s, sympy.Equality) and s.lhs == s.rhs:
                    return True
            except Exception:
                continue
    return None


def _bounded_scan(form, expr, timeout: float = 10.0, cap: int = 20000):
    """Exhaustively look for a point inside the bound where the claim fails.

    Returns `(witness | None, points_scanned, note)`.
    """
    import itertools

    import sympy

    bounded = [
        v
        for v in form.variables
        if v.type == "int" and v.lower is not None and v.upper is not None
    ]
    if not bounded:
        return None, 0, "the claim has no bounded integer variables to scan"

    ranges = [range(int(v.lower), int(v.upper) + 1) for v in bounded]
    total = 1
    for r in ranges:
        total *= len(r)
    if total > cap:
        return None, 0, f"the bound is too large to scan exhaustively ({total:,} points)"

    syms = {v.name: sympy.Symbol(v.name, integer=True) for v in bounded}
    try:
        target = expr.subs({syms[v.name]: syms[v.name] for v in bounded})
    except Exception:
        target = expr

    started = time.time()
    scanned = 0
    try:
        for point in itertools.product(*ranges):
            scanned += 1
            if scanned % 500 == 0 and time.time() - started > timeout:
                return None, scanned, f"scan stopped after {scanned:,} points (timeout)"
            subs = {syms[v.name]: syms[v.name].subs(syms[v.name], val)
                    for v, val in zip(bounded, point)}
            try:
                value = target.subs(subs)
                value = sympy.simplify(value)
                truth = bool(value)
            except Exception:
                continue
            if not truth:
                witness = {v.name: val for v, val in zip(bounded, point)}
                return witness, scanned, f"violation found after {scanned:,} points"
    except Exception as exc:  # noqa: BLE001
        return None, scanned, f"scan failed: {exc}"
    return None, scanned, f"no violation in {scanned:,} scanned points"


# ---------------------------------------------------------------------------
# Honest, scored unknowns
# ---------------------------------------------------------------------------
def classify_unknown(
    claim_text: str,
    form: SymbolicForm,
    result: SolverResult,
    client: Optional[LLMClient] = None,
) -> UnknownInfo:
    """Ask the LLM *why* we are stuck; fall back to heuristics if unavailable."""
    heuristic = result.unknown_info or UnknownInfo(
        kind="undecidable",
        confidence=0.5,
        detail="The solver stopped without deciding the claim.",
        remedy="Try tightening the bounds.",
    )
    if result.unknown_info and result.unknown_info.kind in ("solver_error",):
        return result.unknown_info
    if form.confidence < 0.45 or form.ambiguity:
        # translation problem dominates — say so
        info = UnknownInfo(
            kind="translation_ambiguity",
            confidence=max(0.5, 1.0 - form.confidence),
            detail=(
                f"The statement is ambiguous, so the solver was checking a guess. "
                f"{form.ambiguity}".strip()
            ),
            remedy="Pin the statement down (draw it, or state it with explicit bounds).",
        )
        return info
    try:
        client = client or get_client()
        payload, _ = client.chat_json(
            [
                {"role": "system", "content": SCOPE_PROMPT},
                {
                    "role": "user",
                    "content": f"Claim: {claim_text}\nStructured form:\n{form.pretty()}\n"
                    f"Solver said: {heuristic.detail} ({result.raw})",
                },
            ]
        )
        kind = payload.get("kind", heuristic.kind)
        if kind not in ("timeout", "undecidable", "translation_ambiguity", "unsupported_backend"):
            kind = heuristic.kind
        conf = float(payload.get("confidence", heuristic.confidence))
        conf = max(0.0, min(1.0, conf))
        return UnknownInfo(
            kind=kind,  # type: ignore[arg-type]
            confidence=conf,
            detail=str(payload.get("detail", heuristic.detail)),
            remedy=str(payload.get("remedy", heuristic.remedy)),
        )
    except (LLMUnavailable, LLMError, ValueError, TypeError):
        return heuristic


# ---------------------------------------------------------------------------
# Top-level check
# ---------------------------------------------------------------------------
def _apply_result(
    state: ProofState,
    form: SymbolicForm,
    result: SolverResult,
    claim_text: str,
    client: Optional[LLMClient] = None,
) -> ProofState:
    """Turn a solver result into the state fields (with the honesty guards)."""
    if result.verdict == "counterexample_found":
        state.verdict = "counterexample_found"
        state.counterexample = result.counterexample or {}
    elif result.verdict == "no_counterexample_in_bound":
        if _is_tautology(form.claim_expr):
            state.verdict = "unknown"
            state.unknown_info = UnknownInfo(
                kind="translation_ambiguity",
                confidence=0.9,
                detail=(
                    "The claim was formalised into a tautology, so the solver was checking "
                    "nothing at all. We are not going to report 'no counterexample' for a "
                    "check that did not happen."
                ),
                remedy="Rephrase the claim so both sides of the relation are explicit.",
            )
            state.unknown_reason = state.unknown_info.detail
        else:
            state.verdict = "no_counterexample_in_bound"
    else:
        state.verdict = "unknown"
        state.unknown_info = classify_unknown(claim_text, form, result, client=client)
        state.unknown_reason = state.unknown_info.detail
    return state


def breach_check(
    claim_text: str,
    memory: Optional[ProofMemory] = None,
    client: Optional[LLMClient] = None,
    timeout: float = SOLVER_TIMEOUT_SECONDS,
    extra_constraints: Optional[list[str]] = None,
) -> ProofState:
    """Translate -> solve -> build a `ProofState`. Never raises."""
    memory = memory or ProofMemory()
    client = client or get_client()

    key = make_key(claim_text, "check")
    cached = memory.read(key)
    if cached is not None:
        state = ProofState.from_dict(cached)
        state.cache_hit = True
        return state

    form = translate_claim(claim_text, client=client, memory=memory)
    result = run_solver(form, timeout=timeout, extra_constraints=extra_constraints)

    # The encoding parsed but the solver could not cope with it (typically a
    # too-wide search space on a nonlinear divisibility check). Ask for a
    # tighter encoding and try again before reporting an unknown.
    attempts = 0
    while (
        result.verdict == "unknown"
        and attempts < MAX_TRANSLATION_ATTEMPTS - 1
        and result.unknown_info is not None
        and result.unknown_info.kind in ("timeout", "translation_ambiguity")
    ):
        attempts += 1
        retry_form = translate_claim(
            claim_text,
            client=client,
            memory=memory,
            feedback=(
                f"that encoding returned '{result.unknown_info.kind}' "
                f"({result.unknown_info.detail})."
            ),
            use_cache=False,
        )
        if not retry_form.claim_expr.strip():
            break
        retry_result = run_solver(
            retry_form, timeout=timeout, extra_constraints=extra_constraints
        )
        if retry_result.verdict == "unknown" and retry_result.unknown_info is None:
            break
        form, result = retry_form, retry_result

    state = ProofState(
        claim=claim_text,
        symbolic_form=form.pretty(),
        symbolic_form_struct=form.to_dict(),
        backend=form.backend,
        scope_note=form.scope_note,
        extra_constraints=list(extra_constraints or []),
    )
    for s in form.steps:
        state.add_step(s, created_by=f"{form.backend}_worker")
    if not state.steps:
        state.add_step(f"Claim under test: {claim_text}", created_by="engine")

    if result.verdict == "counterexample_found":
        state.verdict = "counterexample_found"
        state.counterexample = result.counterexample or {}
    elif result.verdict == "no_counterexample_in_bound":
        state.verdict = "no_counterexample_in_bound"
    else:
        state.verdict = "unknown"
        state.unknown_info = classify_unknown(claim_text, form, result, client=client)
        state.unknown_reason = state.unknown_info.detail

    if state.verdict == "no_counterexample_in_bound" and _is_tautology(form.claim_expr):
        state.verdict = "unknown"
        state.unknown_info = UnknownInfo(
            kind="translation_ambiguity",
            confidence=0.9,
            detail=(
                "The claim was formalised into a tautology, so the solver was checking "
                "nothing at all. We are not going to report 'no counterexample' for a "
                "check that did not happen."
            ),
            remedy="Rephrase the claim so both sides of the relation are explicit.",
        )
        state.unknown_reason = state.unknown_info.detail

    memory.write(key, state.serialize_to_dict(), source="engine.breach_check")
    return state

def check_with_form(
    form: SymbolicForm,
    claim_text: str,
    memory: Optional[ProofMemory] = None,
    timeout: float = SOLVER_TIMEOUT_SECONDS,
    extra_constraints: Optional[list[str]] = None,
) -> ProofState:
    """Same as `breach_check` but with a pre-built symbolic form (used by the
    built-in example gallery so demos never depend on the network)."""
    memory = memory or ProofMemory()
    result = run_solver(form, timeout=timeout, extra_constraints=extra_constraints)
    state = ProofState(
        claim=claim_text,
        symbolic_form=form.pretty(),
        symbolic_form_struct=form.to_dict(),
        backend=form.backend,
        scope_note=form.scope_note,
        extra_constraints=list(extra_constraints or []),
    )
    for s in form.steps:
        state.add_step(s, created_by=f"{form.backend}_worker")
    if not state.steps:
        state.add_step(f"Claim under test: {claim_text}", created_by="engine")
    if result.verdict == "counterexample_found":
        state.verdict = "counterexample_found"
        state.counterexample = result.counterexample or {}
    elif result.verdict == "no_counterexample_in_bound":
        state.verdict = "no_counterexample_in_bound"
    else:
        state.verdict = "unknown"
        state.unknown_info = result.unknown_info or UnknownInfo(
            kind="undecidable",
            confidence=0.5,
            detail="The solver stopped without deciding the claim.",
            remedy="Try tightening the bounds.",
        )
        state.unknown_reason = state.unknown_info.detail
    if result.verdict == "no_counterexample_in_bound" and _is_tautology(form.claim_expr):
        state.verdict = "unknown"
        state.unknown_info = UnknownInfo(
            kind="translation_ambiguity",
            confidence=0.9,
            detail=(
                "The claim was formalised into a tautology, so the solver was checking "
                "nothing at all. We are not going to report 'no counterexample' for a "
                "check that did not happen."
            ),
            remedy="Rephrase the claim so both sides of the relation are explicit.",
        )
        state.unknown_reason = state.unknown_info.detail
    memory.write(make_key(claim_text, "check"), state.serialize_to_dict(), source="engine.check_with_form")
    return state
