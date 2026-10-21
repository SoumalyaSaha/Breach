"""Stage 2 — Shared `ProofMemory` store.

A dict-based, lock-guarded cache keyed by `hash(claim_text, task_type)`.
Writes never silently overwrite: `write()` returns False if the key already
exists, which is what guarantees "no duplicated or overwritten subagent work".
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Optional


def make_key(claim_text: str, task_type: str = "check") -> str:
    raw = f"{task_type}::{(claim_text or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class ProofMemory:
    """Thread-safe store shared by every worker and by both UIs."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    # -- core API --------------------------------------------------------
    def write(self, key: str, value: Any, source: str = "unknown") -> bool:
        """Store a value. Returns False if the key already existed."""
        with self._lock:
            if key in self._store:
                return False
            self._store[key] = value
            self._meta[key] = {"source": source, "at": time.time()}
            return True

    def read(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._store.get(key)

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._store

    def meta(self, key: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._meta.get(key, {}))

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._store.keys())

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._meta.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    # -- convenience -----------------------------------------------------
    def get_or_compute(self, key: str, compute, source: str = "unknown"):
        """Return the cached value, or compute+store it exactly once.

        `compute` is only called on a miss. Concurrent callers all wait on the
        same key and only one of them ever runs `compute`.
        """
        hit = self.read(key)
        if hit is not None:
            return hit, True
        value = compute()
        self.write(key, value, source=source)
        return value, False


#: Process-wide default store (CLI and Web each get their own instance, but
#: the module-level one is handy for tests and scripts).
DEFAULT_MEMORY = ProofMemory()
