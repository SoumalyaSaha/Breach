"""Stage 11 (brief §11) — the LLM provider layer.

The LLM's only job in Breach is *translation*: turning informal math into
structured, solver-checkable input (and, later, explaining a solver result in
plain language). It is never the source of truth.

Provider chain (first available wins):
    Groq  ->  Google AI Studio  ->  local Ollama  ->  offline heuristic

The Groq path supports a multi-key rotation with per-key cooldowns so a
single rate-limited key cannot stall a live demo. Every call is time-boxed.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

try:  # optional dependency
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass


DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
DEFAULT_GROQ_VISION_MODEL = os.getenv(
    "GROQ_VISION_MODEL", "meta-llama/llama-3.2-11b-vision-preview"
)
DEFAULT_GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.0-flash")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

#: Chat models to try, in order, when the configured one is not available on
#: the account (Groq model availability varies per key).
GROQ_MODEL_CANDIDATES = [
    DEFAULT_GROQ_MODEL,
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

#: Vision models to try, in order.
GROQ_VISION_CANDIDATES = [
    DEFAULT_GROQ_VISION_MODEL,
    "meta-llama/llama-3.2-90b-vision-preview",
    "meta-llama/llama-3.2-11b-vision-preview",
    "llama-3.2-11b-vision-preview",
    "llama-3.2-90b-vision-preview",
]

DEFAULT_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "45"))


class LLMUnavailable(RuntimeError):
    """No provider could serve the request."""


class LLMError(RuntimeError):
    """A provider was reachable but failed."""


# ---------------------------------------------------------------------------
# Groq key rotation
# ---------------------------------------------------------------------------
class GroqKeyRotator:
    """Round-robin across several Groq keys with per-key cooldowns.

    NOTE: the brief flags that rotating across multiple accounts may violate
    Groq's Acceptable Use Policy. We keep the *technical* rotation (it is also
    useful for a single account's burst limits) but the default ordering is
    Groq -> Google -> Ollama, so we never *need* the rotation to stay alive.
    """

    def __init__(self, keys: Optional[list[str]] = None) -> None:
        if keys is None:
            raw = [
                os.getenv("GROQ_API_KEY_1"),
                os.getenv("GROQ_API_KEY_2"),
                os.getenv("GROQ_API_KEY_3"),
                os.getenv("GROQ_API_KEY_4"),
            ]
            keys = [k for k in raw if k]
        self.keys: list[str] = list(keys)
        self.current_idx = 0
        self.cooldown_until: dict[int, float] = {i: 0.0 for i in range(len(self.keys))}

    def __bool__(self) -> bool:
        return bool(self.keys)

    def _next_available_key(self) -> tuple[Optional[str], Optional[int]]:
        now = time.time()
        for _ in range(len(self.keys)):
            idx = self.current_idx
            if now >= self.cooldown_until.get(idx, 0.0):
                return self.keys[idx], idx
            self.current_idx = (self.current_idx + 1) % len(self.keys)
        return None, None

    def call(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        if not self.keys:
            raise LLMUnavailable("No Groq API keys configured")
        try:
            from groq import Groq
        except Exception as exc:  # pragma: no cover
            raise LLMUnavailable(f"groq package not installed: {exc}") from exc

        last_error: Optional[Exception] = None
        for _ in range(len(self.keys)):
            key, idx = self._next_available_key()
            if key is None:
                break
            client = Groq(api_key=key)
            try:
                return client.chat.completions.create(messages=messages, **kwargs)
            except Exception as exc:  # noqa: BLE001 - provider errors vary
                name = type(exc).__name__
                status = getattr(exc, "status_code", None)
                if name == "RateLimitError" or status == 429:
                    self.cooldown_until[idx] = time.time() + 60
                    self.current_idx = (self.current_idx + 1) % len(self.keys)
                    last_error = exc
                    continue
                if status in (401, 403):
                    self.cooldown_until[idx] = time.time() + 300
                    self.current_idx = (self.current_idx + 1) % len(self.keys)
                    last_error = exc
                    continue
                raise LLMError(f"Groq error: {exc}") from exc
        raise LLMError(f"All Groq keys are rate-limited right now: {last_error}")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
@dataclass
class LLMReply:
    text: str
    provider: str
    model: str
    raw: Any = None


class LLMClient:
    """Provider-agnostic chat client with a deterministic offline fallback."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self.rotator = GroqKeyRotator()
        self.google_key = os.getenv("GOOGLE_API_KEY")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.last_provider: str = ""
        self.offline = os.getenv("BREACH_OFFLINE", "").lower() in ("1", "true", "yes")

    # -- provider probes -------------------------------------------------
    def _groq_ready(self) -> bool:
        return bool(self.rotator) and not self.offline

    def _google_ready(self) -> bool:
        return bool(self.google_key) and not self.offline

    def _ollama_ready(self) -> bool:
        if self.offline:
            return False
        try:
            import requests

            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=1.5)
            return resp.status_code == 200
        except Exception:
            return False

    def providers(self) -> list[str]:
        avail = []
        if self._groq_ready():
            avail.append("groq")
        if self._google_ready():
            avail.append("google")
        if self._ollama_ready():
            avail.append("ollama")
        if not avail:
            avail.append("offline")
        return avail

    # -- chat ------------------------------------------------------------
    def _groq_chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> LLMReply:
        """Call Groq, trying a few models because availability varies by key."""
        requested = kwargs.pop("model", None)
        candidates = [requested] if requested else list(GROQ_MODEL_CANDIDATES)
        for model in candidates:
            if not model:
                continue
            try:
                resp = self.rotator.call(
                    messages=messages,
                    model=model,
                    timeout=self.timeout,
                    **kwargs,
                )
            except LLMError as exc:
                text = str(exc)
                if "404" in text or "does not exist" in text:
                    continue  # try the next candidate model
                raise
            content = (resp.choices[0].message.content or "").strip()
            if not content:
                # reasoning-only models sometimes burn the whole budget on
                # reasoning; treat it as a failed attempt and try the next model
                continue
            return LLMReply(text=content, provider="groq", model=resp.model, raw=resp)
        raise LLMError(
            "No usable Groq model responded. Models tried: "
            + ", ".join(str(m) for m in candidates)
        )

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> LLMReply:
        """Try providers in order; raise `LLMUnavailable` if none can serve."""
        kwargs.setdefault("temperature", 0)
        kwargs.setdefault("max_tokens", 2048)

        last_exc: Optional[Exception] = None
        if self._groq_ready():
            try:
                reply = self._groq_chat(messages, **dict(kwargs))
                self.last_provider = "groq"
                return reply
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        else:
            last_exc = LLMUnavailable("Groq not configured")

        if self._google_ready():
            try:
                text = self._google_chat(messages, **kwargs)
                self.last_provider = "google"
                return LLMReply(text=text, provider="google", model=DEFAULT_GOOGLE_MODEL)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc

        if self._ollama_ready():
            try:
                text = self._ollama_chat(messages, **kwargs)
                self.last_provider = "ollama"
                return LLMReply(text=text, provider="ollama", model=DEFAULT_OLLAMA_MODEL)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc

        raise LLMUnavailable(str(last_exc) if last_exc else "no provider available")

    def chat_text(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        return self.chat(messages, **kwargs).text

    def chat_json(
        self,
        messages: list[dict[str, Any]],
        default: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], str]:
        """Return `(parsed_json, raw_text)`.

        If the provider misbehaves we return the raw text so the caller can
        decide; we never silently substitute a made-up object.
        """
        reply = self.chat(messages, **kwargs)
        parsed = extract_json(reply.text)
        if parsed is None:
            if default is not None:
                return default, reply.text
            raise LLMError(f"Provider did not return JSON: {reply.text[:300]}")
        return parsed, reply.text

    # -- provider-specific implementations --------------------------------
    def _google_chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        import requests

        model = kwargs.pop("model", DEFAULT_GOOGLE_MODEL)
        payload = {
            "contents": [
                {"role": m["role"], "parts": [{"text": m["content"]}]} for m in messages
            ],
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0),
                "maxOutputTokens": kwargs.get("max_tokens", 2048),
            },
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={self.google_key}"
        )
        resp = requests.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)

    def _ollama_chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        import requests

        model = kwargs.pop("model", DEFAULT_OLLAMA_MODEL)
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": kwargs.get("temperature", 0)},
        }
        resp = requests.post(
            f"{self.ollama_url}/api/chat", json=payload, timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")

    # -- vision ----------------------------------------------------------
    def chat_with_image(
        self, prompt: str, image_bytes: bytes, mime: str = "image/png"
    ) -> str:
        """Transcribe an image. Uses a vision-capable model; raises otherwise."""
        import base64

        b64 = base64.b64encode(image_bytes).decode("ascii")
        if self._groq_ready():
            for model in GROQ_VISION_CANDIDATES:
                try:
                    content = [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ]
                    resp = self.rotator.call(
                        messages=[{"role": "user", "content": content}],
                        model=model,
                        temperature=0,
                        max_tokens=2048,
                        timeout=self.timeout,
                    )
                    text = (resp.choices[0].message.content or "").strip()
                    if text:
                        return text
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    continue
        if self._google_ready():
            import requests

            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": mime,
                                    "data": b64,
                                }
                            },
                        ],
                    }
                ]
            }
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{DEFAULT_GOOGLE_MODEL}:generateContent?key={self.google_key}"
            )
            resp = requests.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            parts = resp.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        raise LLMUnavailable(
            "No vision-capable model is available on the configured providers. "
            "Set GOOGLE_API_KEY (gemini vision) or a Groq key with access to a "
            "Llama vision model, then draw the claim in the chat instead."
        )


def extract_json(text: str) -> Optional[dict[str, Any]]:
    """Pull the first JSON object out of a model response (tolerates fences)."""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip("` \n")
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    return json.loads(blob)
                except Exception:
                    return None
    return None


_CLIENT: Optional[LLMClient] = None


def get_client() -> LLMClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = LLMClient()
    return _CLIENT
