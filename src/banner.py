"""The BREACH wordmark — a retro, italic block logo.

Visual recipe (matching the reference logo):
  * solid, sheared (italic) block letters filled in red
  * a darker red bevel on the letter edges
  * a green rim around the letters, thickening into a green drop shadow at the
    bottom-right — the 3D "raised" effect
  * a near-black background

Everything is drawn on a character grid: the letters are rasterised, the empty
cells are flood-filled from the border so that the counters of the letters stay
dark, and the remaining empty cells become the green rim / shadow.
"""

from __future__ import annotations

import os
from collections import deque
from typing import Optional

from rich.panel import Panel
from rich.text import Text


def _get_console():
    """The shared rich console (imported lazily to avoid a circular import)."""
    from .ui_theme import console

    return console


# -- palette ---------------------------------------------------------------
RED_FILL = "#e8413a"  # the letters
RED_BEVEL = "#c1352b"  # slightly darker red down the right-hand edge
GREEN_RIM = "#2f9e44"  # rim + drop shadow
PANEL_BG = "#0d1117"  # near-black background

_FALLBACK = {
    RED_FILL: "bright_red",
    RED_BEVEL: "red",
    GREEN_RIM: "bright_green",
    PANEL_BG: "black",
}


def _hex(colour: str) -> str:
    """Use the exact colour when the terminal can show it, else fall back."""
    console = _get_console()
    system = getattr(console, "color_system", None)
    system = getattr(system, "name", system)
    if system in ("truecolor", "eight_bit"):
        return colour
    return _FALLBACK.get(colour, colour)


def _banner_art(font: str, scale: int, shear: int) -> list[str]:
    """Render the wordmark: a block font, scaled, then sheared into an italic."""
    try:
        import pyfiglet

        art = pyfiglet.figlet_format("BREACH", font=font).splitlines()
    except Exception:
        art = []
    if not art:
        art = [
            "########  ########  ########    ###     ######  ##     ##",
            "##     ## ##     ## ##         ## ##   ##    ## ##     ##",
            "##     ## ##     ## ##        ##   ##  ##       ##     ##",
            "########  ########  ######   ##     ## ##       #########",
            "##     ## ##   ##   ##       ######### ##       ##     ##",
            "##     ## ##    ##  ##       ##     ## ##    ## ##     ##",
            "########  ##     ## ######## ##     ##  ######  ##     ##",
        ]
    while art and not art[-1].strip():
        art.pop()
    if scale > 1:
        art = ["".join(ch * scale for ch in line) for line in art]
    if shear:
        height = len(art)
        art = [" " * ((height - 1 - r) * shear) + line for r, line in enumerate(art)]
    return art


#: (font, horizontal scale, italic shear) candidates, widest/nicest first.
BANNER_STYLES = (
    ("banner3", 2, 2),  # chunky italic blocks
    ("banner3", 1, 1),  # compact italic blocks
    ("big", 1, 1),
    ("slant", 1, 0),    # last resort: the thin slanted wordmark
)


def _pick_banner(available_width: int) -> list[str]:
    """Pick the biggest wordmark that fits the terminal."""
    forced = os.environ.get("BREACH_BANNER_FONT")
    candidates = ((forced, 2, 2),) if forced else BANNER_STYLES
    for font, scale, shear in candidates:
        lines = _banner_art(font, scale, shear)
        width = max((len(l) for l in lines), default=0)
        if width + 8 <= available_width:
            return lines
    font, scale, shear = candidates[-1]
    return _banner_art(font, scale, shear)


def banner_lines() -> list[str]:
    """The raw wordmark (letters only, no shadow)."""
    return _pick_banner(_get_console().width)


def banner_text() -> str:
    """The wordmark as plain text."""
    return "\n".join(banner_lines())


def banner_rich() -> Text:
    """The wordmark with rim, bevel and drop shadow."""
    lines = _pick_banner(_get_console().width)
    height = len(lines)
    width = max((len(l) for l in lines), default=0)
    ink = [[ch != " " for ch in line.ljust(width)] for line in lines]

    out_h, out_w = height + 2, width + 2

    def is_ink(r: int, c: int) -> bool:
        return 0 <= r < height and 0 <= c < width and ink[r][c]

    # flood fill the empty cells from the border: whatever stays unreachable is
    # a counter (a hole inside the letters) and must stay dark.
    outside = [[False] * out_w for _ in range(out_h)]
    queue: deque[tuple[int, int]] = deque()
    for r in range(out_h):
        queue.append((r, 0))
        queue.append((r, out_w - 1))
    for c in range(out_w):
        queue.append((0, c))
        queue.append((out_h - 1, c))
    while queue:
        r, c = queue.popleft()
        if outside[r][c] or is_ink(r, c):
            continue
        outside[r][c] = True
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < out_h and 0 <= cc < out_w and not outside[rr][cc]:
                queue.append((rr, cc))

    fill = _hex(RED_FILL)
    bevel = _hex(RED_BEVEL)
    rim = _hex(GREEN_RIM)

    canvas: list[list[tuple[Optional[str], str]]] = [
        [(None, " ") for _ in range(out_w)] for _ in range(out_h)
    ]
    for r in range(out_h):
        for c in range(out_w):
            if is_ink(r, c):
                # letters: solid red, with a darker red down the right-hand
                # edge so the blocks read as raised
                shade = not is_ink(r, c + 1)
                canvas[r][c] = (bevel if shade else fill, "#")
                continue
            if not outside[r][c]:
                continue  # counter of a letter -> stays dark
            touches_letter = any(
                is_ink(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)
            )
            shadow = is_ink(r - 1, c - 1)  # the copy offset down-right
            if touches_letter or shadow:
                canvas[r][c] = (rim, "#")

    text = Text()
    for r in range(out_h):
        run_style: Optional[str] = None
        run_start = 0
        for c in range(out_w + 1):
            style = canvas[r][c][0] if c < out_w else None
            if style != run_style:
                if run_start < c:
                    text.append(
                        "".join(canvas[r][cc][1] for cc in range(run_start, c)),
                        style=run_style,
                    )
                run_style = style
                run_start = c
        text.append("\n")
    return text


def _panel_style() -> str:
    """Near-black panel background."""
    if _hex(PANEL_BG) == PANEL_BG:
        return f"on {PANEL_BG}"
    return f"on {_hex(PANEL_BG)}"


def print_banner(con=None) -> None:
    from .ui_theme import ACCENT

    con = con or _get_console()
    con.print(
        Panel(
            banner_rich(),
            title=f"[bold {ACCENT}]BREACH[/bold {ACCENT}] — adversarial math checking",
            subtitle="[dim]try to break the proof, not confirm it[/dim]",
            border_style=ACCENT,
            style=_panel_style(),
            expand=False,
        )
    )
