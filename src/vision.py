"""Stage 7 — Vision transcription (canvas drawing -> LaTeX / plain text).

The transcription is ALWAYS shown back to the user for confirmation before it
is submitted. Handwriting recognition is imperfect, and a silent error here
would poison the entire trust story of the tool.
"""

from __future__ import annotations

import base64
from typing import Optional

from .llm_client import LLMClient, LLMError, LLMUnavailable, get_client

VISION_PROMPT = """Transcribe the mathematical content of this image into
precise LaTeX.

Rules:
- Output ONLY the transcription. No commentary, no markdown fence.
- Preserve the structure: symbols, exponents, fractions, quantifiers, arrows.
- If any part is genuinely illegible, write UNCLEAR in place of that part.
  Do NOT guess — a wrong guess is worse than an admission.
- If the image contains no mathematics at all, output exactly: NOT_MATH"""


def transcribe_drawing(
    image_bytes: bytes,
    client: Optional[LLMClient] = None,
    mime: str = "image/png",
) -> str:
    """Transcribe a drawing into LaTeX/text. Raises only on hard failure."""
    client = client or get_client()
    try:
        return client.chat_with_image(VISION_PROMPT, image_bytes, mime=mime).strip()
    except (LLMUnavailable, LLMError) as exc:
        raise RuntimeError(
            "Vision transcription is unavailable (no vision-capable provider configured): "
            f"{exc}"
        ) from exc


def transcribe_data_url(data_url: str, client: Optional[LLMClient] = None) -> str:
    """Transcribe from a `data:image/png;base64,...` URL."""
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    return transcribe_drawing(base64.b64decode(data_url), client=client)


def transcribe_file(path: str, client: Optional[LLMClient] = None) -> str:
    with open(path, "rb") as fh:
        data = fh.read()
    mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    return transcribe_drawing(data, client=client, mime=mime)
