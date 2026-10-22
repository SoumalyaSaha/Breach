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


def canvas_png_bytes(canvas) -> Optional[bytes]:
    """PNG bytes of a `st_canvas` result.

    With `return_image_data=True` the component hands back raw PNG bytes
    (`image_bytes`); older builds return a numpy RGBA array (`image_data`) or
    a PIL image. Handle all three so the transcription never depends on one
    version of the component.

    Lives here (not in the Streamlit script) so it is importable and testable,
    and so the UI can never call it before it exists.
    """
    if canvas is None:
        return None

    raw = getattr(canvas, "image_bytes", None)
    if raw:
        return bytes(raw)

    data = getattr(canvas, "image_data", None)
    if data is None:
        return None
    if hasattr(data, "save"):  # a PIL image
        from io import BytesIO

        buf = BytesIO()
        data.save(buf, format="PNG")
        return buf.getvalue()
    try:  # a numpy RGBA array
        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.fromarray(data).save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def transcribe_canvas(canvas, client: Optional[LLMClient] = None) -> Optional[str]:
    """Transcribe a canvas drawing into LaTeX (None if nothing is drawn)."""
    png = canvas_png_bytes(canvas)
    if not png:
        return None
    return transcribe_drawing(png, client=client)
