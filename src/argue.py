"""Stage 5 + Stage 5b — the blackboard argument loop.

Stage 5   `challenge_step`  — the user contests a specific step; the agent must
                             answer *that* objection, not restart.
Stage 5b  `diagnose_failure` — given a counterexample, work out which step's
                             implicit assumption it breaks (proof autopsy).
Stage 5b  `offer_patch`     — offer to add the missing assumption as a
                             constraint and re-check, honestly reporting the
                             patched outcome.

Nothing here is allowed to fabricate: if the model cannot point at a specific
step, the claim is marked as failing at the premise level instead.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .engine import SymbolicForm, check_with_form, run_solver
from .llm_client import LLMClient, LLMError, LLMUnavailable, get_client
from .memory import ProofMemory
from .state import ProofState

# ---------------------------------------------------------------------------
# Stage 5 — challenging a step
# ---------------------------------------------------------------------------
CHALLENGE_PROMPT = """You are defending a mathematical argument while the
user tries to break it. You are given the claim, the full list of steps, the
step being challenged, and the user's objection.

CLAIM: {claim}
SYMBOLIC FORM:
{symbolic}

ALL STEPS:
{steps}

STEP BEING CHALENGED (step {step_id}):
{step_text}

USER'S OBJECTION:
{challenge}

Answer with ONLY a JSON object:
{{"response": "your answer to THIS objection, specifically (2-4 sentences)",
  "concedes": true|false,
  "new_constraint": "if the objection exposes a missing assumption, give it as a
     solver-ready constraint expression over the declared variables (or empty string)",
  "new_step": "if the objection surfaces a genuinely new sub-claim that should be
     checked, state it in one sentence (or empty string)"}}

Rules:
- Answer the objection that was made. Do not restate the whole proof.
- If the objection is valid, concede honestly (concedes=true) and give the
  missing assumption as `new_constraint` (e.g. "b != 0", "x >= 1").
- Never invent a proof you were not given."""


def challenge_step(
    proof_state: ProofState,
    step_id: int,
    challenge_text: str,
    client: Optional[LLMClient] = None,
    memory: Optional[ProofMemory] = None,
) -> ProofState:
    """Respond to a specific objection about a specific step."""
    client = client or get_client()
    memory = memory or ProofMemory()
    step = proof_state.get_step(step_id)
    if step is None:
        step = proof_state.add_step(f"(step {step_id} does not exist)")
        step.status = "challenged"
        step.challenge_text = challenge_text
        step.agent_response = "That step does not exist in the current proof state."
        return proof_state

    step.status = "challenged"
    step.challenge_text = challenge_text

    steps_block = "\n".join(
        f"  {s.id}. {s.text}" + (f"   [status: {s.status}]" if s.status != "unchallenged" else "")
        for s in proof_state.steps
    )
    prompt = CHALLENGE_PROMPT.format(
        claim=proof_state.claim,
        symbolic=proof_state.symbolic_form,
        steps=steps_block,
        step_id=step_id,
        step_text=step.text,
        challenge=challenge_text,
    )
    try:
        payload, _ = client.chat_json(
            [{"role": "system", "content": prompt}],
        )
        response = str(payload.get("response", "")).strip()
        concedes = bool(payload.get("concedes", False))
        new_constraint = str(payload.get("new_constraint", "") or "").strip()
        new_step = str(payload.get("new_step", "") or "").strip()
    except (LLMUnavailable, LLMError, ValueError, TypeError) as exc:
        step.agent_response = (
            f"The agent could not be reached ({exc}). Your objection is recorded and "
            "the step is marked as challenged."
        )
        return proof_state

    if not response:
        response = "The agent returned an empty answer to the objection."
    step.agent_response = response

    if new_step:
        proof_state.add_step(new_step, created_by="challenge_worker")

    if concedes and new_constraint and proof_state.symbolic_form_struct:
        # the objection broke the proof — re-check with the new constraint
        patched = _patch_state(proof_state, new_constraint, client=client, memory=memory)
        if patched is not None:
            proof_state.verdict = patched.verdict
            proof_state.counterexample = patched.counterexample
            proof_state.unknown_reason = patched.unknown_reason
            proof_state.unknown_info = patched.unknown_info
            proof_state.extra_constraints = patched.extra_constraints
            proof_state.counterexample = patched.counterexample

    step.status = "resolved"
    return proof_state


def _patch_state(
    proof_state: ProofState,
    constraint: str,
    client: Optional[LLMClient] = None,
    memory: Optional[ProofMemory] = None,
) -> Optional[ProofState]:
    """Re-run the solver with an extra constraint."""
    struct = proof_state.symbolic_form_struct
    if not struct:
        return None
    form = SymbolicForm.from_dict(struct)
    result = run_solver(
        form,
        timeout=10.0,
        extra_constraints=list(proof_state.extra_constraints) + [constraint],
    )
    patched = ProofState.from_dict(proof_state.serialize_to_dict())
    patched.extra_constraints = list(proof_state.extra_constraints) + [constraint]
    if result.verdict == "counterexample_found":
        patched.verdict = "counterexample_found"
        patched.counterexample = result.counterexample or {}
    elif result.verdict == "no_counterexample_in_bound":
        patched.verdict = "no_counterexample_in_bound"
        patched.counterexample = None
    else:
        patched.verdict = "unknown"
        patched.unknown_info = result.unknown_info
        patched.unknown_reason = result.unknown_info.detail if result.unknown_info else None
    return patched


# ---------------------------------------------------------------------------
# Stage 5b — proof autopsy
# ---------------------------------------------------------------------------
DIAGNOSE_PROMPT = """You are performing a PROOF AUTOPSY. A solver has found a
counterexample to a claim. Your job: identify which step's IMPLICIT ASSUMPTION
the counterexample violates, and state that assumption explicitly.

CLAIM: {claim}
SYMBOLIC FORM:
{symbolic}

STEPS OF THE ARGUMENT:
{steps}

COUNTEREXAMPLE FOUND:
{counterexample}

Answer with ONLY a JSON object:
{{"implicated_step": <step id or null>,
  "missing_assumption": "the implicit assumption in plain words, e.g. 'the divisor is nonzero'",
  "missing_assumption_expr": "that assumption as a solver-ready constraint, e.g. 'b != 0'",
  "confidence": 0.0-1.0,
  "explanation": "one or two sentences: why this counterexample breaks this step",
  "premise_level_failure": true|false}}

Rules:
- Only name a step if you are confident the counterexample really violates an
  assumption made there. If the counterexample contradicts the claim itself
  (the premises were never justified), set "implicated_step" to null and
  "premise_level_failure" to true.
- Never guess. A low-confidence guess is worse than an honest "premise level"."""


def diagnose_failure(
    proof_state: ProofState,
    counterexample: Optional[dict[str, Any]] = None,
    client: Optional[LLMClient] = None,
) -> ProofState:
    """Annotate the proof state with which step the counterexample breaks."""
    client = client or get_client()
    ce = counterexample if counterexample is not None else (proof_state.counterexample or {})
    steps_block = "\n".join(f"  {s.id}. {s.text}" for s in proof_state.steps)
    prompt = DIAGNOSE_PROMPT.format(
        claim=proof_state.claim,
        symbolic=proof_state.symbolic_form,
        steps=steps_block,
        counterexample=json.dumps(ce, indent=2, ensure_ascii=False),
    )
    try:
        payload, _ = client.chat_json([{"role": "system", "content": prompt}])
    except (LLMUnavailable, LLMError, ValueError, TypeError) as exc:
        proof_state.diagnosis = (
            f"The autopsy could not be performed (agent unreachable: {exc}). "
            "The counterexample above is still exact — only the attribution is missing."
        )
        proof_state.premises_faulty = True
        return proof_state

    implicated_id = payload.get("implicated_step")
    confidence = float(payload.get("confidence", 0.0) or 0.0)
    premise_level = bool(payload.get("premise_level_failure", False))
    missing = str(payload.get("missing_assumption", "") or "").strip()
    missing_expr = str(payload.get("missing_assumption_expr", "") or "").strip()
    explanation = str(payload.get("explanation", "") or "").strip()

    if implicated_id is not None and not premise_level and confidence >= 0.4:
        try:
            step = proof_state.get_step(int(implicated_id))
        except (TypeError, ValueError):
            step = None
        if step is not None:
            step.implicated = True
            step.missing_assumption = missing or None
            step.missing_assumption_expr = missing_expr or None  # type: ignore[attr-defined]
            proof_state.diagnosis = explanation or (
                f"Step {step.id} breaks: it assumes {missing} but never states it."
            )
            proof_state.implicated_step_id = step.id  # type: ignore[attr-defined]
            return proof_state

    # No confident single-step attribution -> honest premise-level failure.
    proof_state.premises_faulty = True
    proof_state.diagnosis = explanation or (
        "The counterexample does not point at one specific step: the claim fails at the "
        "premise level. The premises themselves were never justified."
    )
    return proof_state


def offer_patch(proof_state: ProofState, step_id: Optional[int] = None) -> str:
    """The prompt we show the user to accept/reject the patch."""
    if step_id is None:
        step_id = getattr(proof_state, "implicated_step_id", None)
    step = proof_state.get_step(step_id) if step_id is not None else None
    if step is None or not step.missing_assumption:
        return ""
    return f"Add constraint '{step.missing_assumption}' and re-check? [y/n]"


def apply_patch(
    proof_state: ProofState,
    step_id: Optional[int] = None,
    client: Optional[LLMClient] = None,
    memory: Optional[ProofMemory] = None,
) -> tuple[Optional[ProofState], str]:
    """Apply the diagnosed patch and report the outcome in plain language."""
    if step_id is None:
        step_id = getattr(proof_state, "implicated_step_id", None)
    step = proof_state.get_step(step_id) if step_id is not None else None
    if step is None or not step.missing_assumption:
        return None, "There is no diagnosed assumption to add."
    expr = getattr(step, "missing_assumption_expr", "") or ""
    constraint = expr.strip()
    if not constraint:
        constraint = step.missing_assumption
    patched = _patch_state(proof_state, constraint, client=client, memory=memory)
    if patched is None:
        return None, "The original symbolic form is not available, so the patch cannot be applied."
    if patched.verdict == "no_counterexample_in_bound":
        return patched, (
            f"With the constraint '{constraint}' added, no counterexample was found "
            "in the searched bound."
        )
    if patched.verdict == "counterexample_found":
        return patched, (
            f"Still breaks — the claim needs more than '{constraint}'. "
            f"Next counterexample: {patched.counterexample}"
        )
    return patched, (
        f"With the constraint '{constraint}' added the solver could not decide the claim "
        f"({patched.unknown_reason or 'unknown'})."
    )
