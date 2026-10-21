"""Stage 1 — Core data model shared by the CLI and the Web UI.

Everything the tool knows about a claim lives in a single `ProofState` object.
The CLI and Streamlit app are thin renderers over this same structure, which is
what lets `/web` hand a live session over to the browser without losing state.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Optional

Verdict = Literal["counterexample_found", "no_counterexample_in_bound", "unknown"]

#: How the solver (or the translator) failed to reach a verdict.
UnknownKind = Literal[
    "timeout",  # more time might have resolved it
    "undecidable",  # no amount of time helps — outside the solver's fragment
    "translation_ambiguity",  # the claim was ambiguous / formalisation unsure
    "unsupported_backend",  # the requested backend cannot express the claim
    "solver_error",  # an unexpected failure — reported, never hidden
]

STATUS_ICONS = {
    "unchallenged": "•",
    "challenged": "?",
    "resolved": "✓",
}


@dataclass
class ProofStep:
    """One line of the argument being attacked."""

    id: int
    text: str
    status: Literal["unchallenged", "challenged", "resolved"] = "unchallenged"
    challenge_text: Optional[str] = None
    agent_response: Optional[str] = None
    created_by: str = "constraint_worker"
    # Stage 5b — proof autopsy
    implicated: bool = False
    missing_assumption: Optional[str] = None
    missing_assumption_expr: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProofStep":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class UnknownInfo:
    """A *scored* unknown, not a flat shrug.

    `kind` says why the solver stopped, `confidence` says how sure we are about
    that classification, and `remedy` says what (if anything) would help.
    """

    kind: UnknownKind = "undecidable"
    confidence: float = 0.5
    remedy: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UnknownInfo":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


@dataclass
class Citation:
    title: str
    authors_or_source: str = ""
    relevance_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Citation":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


@dataclass
class ProofState:
    """The whole story of one claim under attack."""

    claim: str
    symbolic_form: str = ""
    symbolic_form_struct: Optional[dict[str, Any]] = None
    steps: list[ProofStep] = field(default_factory=list)
    verdict: Verdict = "unknown"
    counterexample: Optional[dict[str, Any]] = None
    unknown_reason: Optional[str] = None
    unknown_info: Optional[UnknownInfo] = None
    citations: list[Citation] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    # bookkeeping
    backend: str = ""
    cache_hit: bool = False
    search_certificate: Optional[dict[str, Any]] = None
    premises_faulty: bool = False
    diagnosis: Optional[str] = None
    implicated_step_id: Optional[int] = None
    scope_note: str = ""
    extra_constraints: list[str] = field(default_factory=list)

    # -- helpers ---------------------------------------------------------
    def add_step(self, text: str, created_by: str = "constraint_worker") -> ProofStep:
        step = ProofStep(id=len(self.steps) + 1, text=text, created_by=created_by)
        self.steps.append(step)
        return step

    def get_step(self, step_id: int) -> Optional[ProofStep]:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None

    @property
    def key(self) -> str:
        """Stable cache key for this claim + task type."""
        raw = f"{self.claim.strip().lower()}|{self.backend or 'auto'}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def serialize_to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [s.to_dict() for s in self.steps]
        data["citations"] = [c.to_dict() for c in self.citations]
        data["unknown_info"] = self.unknown_info.to_dict() if self.unknown_info else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProofState":
        data = dict(data or {})
        steps = [ProofStep.from_dict(s) for s in data.pop("steps", []) or []]
        citations = [Citation.from_dict(c) for c in data.pop("citations", []) or []]
        unknown = data.pop("unknown_info", None)
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        state = cls(steps=steps, citations=citations, **filtered)
        state.unknown_info = UnknownInfo.from_dict(unknown) if unknown else None
        return state

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.serialize_to_dict(), fh, indent=2, ensure_ascii=False)
        return path

    @classmethod
    def load(cls, path: str) -> "ProofState":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def summary_line(self) -> str:
        if self.verdict == "counterexample_found":
            return "counterexample found"
        if self.verdict == "no_counterexample_in_bound":
            return "no counterexample found in bound"
        return "unknown"
