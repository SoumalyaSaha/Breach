"""Stage 6 — Symbol shortcuts.

A small, *visible* translation table. Multi-character function names (`log`,
`ln`, `sin`, `cos`, `lim`) are deliberately excluded: replacing them would
silently corrupt the maths.
"""

from __future__ import annotations

SYMBOL_MAP = {
    "pi": "π",
    "theta": "θ",
    "sqrt": "√",
    "infinity": "∞",
    "integral": "∫",
    "sum": "Σ",
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "lambda": "λ",
    "mu": "μ",
    "sigma": "σ",
    "phi": "φ",
    "omega": "ω",
    "<=": "≤",
    ">=": "≥",
    "!=": "≠",
    "->": "→",
    "forall": "∀",
    "exists": "∃",
    "in": "∈",
    "subset": "⊂",
    "superset": "⊃",
    "union": "∪",
    "intersect": "∩",
    "emptyset": "∅",
    "times": "×",
    "divide": "÷",
    "plusmn": "±",
    "neq": "≠",
    "equiv": "≡",
    "approx": "≈",
    "prop": "⊨",
    "qed": "∎",
}

#: Words that must NEVER be auto-substituted (multi-character function names).
PROTECTED = {"log", "ln", "sin", "cos", "tan", "lim", "exp", "sec", "csc", "cot", "mod", "gcd", "lcm"}

#: Longest-first so `subset` wins over `sub`.
_ORDERED_KEYS = sorted(SYMBOL_MAP.keys(), key=len, reverse=True)


def find_completion(text: str, cursor: int | None = None) -> tuple[str, str] | None:
    """Return `(word, replacement)` for the token ending at the cursor.

    Used for the live autocomplete preview. Returns None when the token is
    protected or unknown.
    """
    if cursor is None:
        cursor = len(text)
    left = text[:cursor]
    i = len(left)
    while i > 0 and (left[i - 1].isalnum() or left[i - 1] in "<>!=-&|√πθαβγλμσφω∞∫Σ"):
        i -= 1
    token = left[i:]
    if not token:
        return None
    low = token.lower()
    if low in PROTECTED:
        return None
    for key in _ORDERED_KEYS:
        if low == key:
            return token, SYMBOL_MAP[key]
    # operator-style tokens need a word boundary
    if low.startswith("<") or low.startswith(">") or low.startswith("!") or low.startswith("-"):
        for key in ("<=", ">=", "!=", "->"):
            if low.startswith(key):
                return token, SYMBOL_MAP[key]
    return None


def apply_shortcut(text: str, cursor: int | None = None) -> tuple[str, int] | None:
    """Apply the shortcut for the token ending at the cursor.

    Returns `(new_text, new_cursor)` or None if there is nothing to replace.
    """
    if cursor is None:
        cursor = len(text)
    hit = find_completion(text, cursor)
    if not hit:
        return None
    token, replacement = hit
    start = cursor - len(token)
    new_text = text[:start] + replacement + text[cursor:]
    return new_text, start + len(replacement)


def preview(text: str, cursor: int | None = None) -> str | None:
    """Human-readable preview of what Tab/space would insert."""
    hit = find_completion(text, cursor)
    if not hit:
        return None
    token, replacement = hit
    return f"{token} → {replacement}"
