"""Stage 9 — Citations.

Finds 1–3 theorems/papers related to the claim's mathematical area.

Hard rule: if we cannot find a good match we return an EMPTY list. A
fabricated citation is much worse than no citation — it would undermine the
one thing this tool is selling.
"""

from __future__ import annotations

from typing import Any, Optional

from .llm_client import LLMClient, LLMError, LLMUnavailable, get_client
from .state import Citation

CITATION_PROMPT = """Find relevant published mathematics for the claim below.

Claim: {claim}
Domain: {domain}

Return ONLY a JSON object:
{{"citations": [{{"title": "...", "authors_or_source": "...", "relevance_note": "..."}}]}}

Rules:
- At most 3 entries. Only well-known, real theorems or papers.
- "title" must be a real, recognisable theorem or paper title.
- "authors_or_source" is e.g. "Euler, 1769" or "Lander & Parkin, 1966".
- "relevance_note" is one short sentence on why it matters for THIS claim.
- If nothing genuinely relevant exists, return an empty list. An empty list is
  a valid and often correct answer — never invent a citation."""


def find_citations(
    claim_text: str,
    claim_domain: str = "general mathematics",
    client: Optional[LLMClient] = None,
) -> list[Citation]:
    """Return related work, or an empty list if nothing solid is available."""
    client = client or get_client()
    try:
        payload, _ = client.chat_json(
            [
                {"role": "system", "content": CITATION_PROMPT},
                {
                    "role": "user",
                    "content": f"Claim: {claim_text}\nDomain: {claim_domain}",
                },
            ]
        )
    except (LLMUnavailable, LLMError, ValueError, TypeError):
        return []

    raw = payload.get("citations")
    if not isinstance(raw, list):
        return []
    out: list[Citation] = []
    for item in raw[:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        out.append(
            Citation(
                title=title,
                authors_or_source=str(item.get("authors_or_source", "")).strip(),
                relevance_note=str(item.get("relevance_note", "")).strip(),
            )
        )
    return out


def attach_citations(state, client: Optional[LLMClient] = None) -> None:
    """Attach citations to a proof state, in place. Never fabricates."""
    if state.citations:
        return
    citations = find_citations(state.claim, client=client)
    if citations:
        state.citations = citations
