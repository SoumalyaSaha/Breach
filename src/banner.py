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

#: vertical gradient of the letter fill (top -> bottom), like the reference
GRAD_TOP = "#7d1109"
GRAD_BOTTOM = "#ffe6df"

_FALLBACK = {
    RED_FILL: "bright_red",
    RED_BEVEL: "red",
    GREEN_RIM: "bright_green",
    PANEL_BG: "black",
    GRAD_TOP: "red",
    GRAD_BOTTOM: "bright_red",
}


def _mix(colour_a: str, colour_b: str, t: float) -> str:
    """Blend two hex colours."""
    a = tuple(int(colour_a[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(colour_b[i : i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{int(round(a[i] + (b[i] - a[i]) * t)):02x}" for i in range(3))


def _hex(colour: str) -> str:
    """Use the exact colour when the terminal can show it, else fall back."""
    console = _get_console()
    system = getattr(console, "color_system", None)
    system = getattr(system, "name", system)
    if system in ("truecolor", "eight_bit"):
        return colour
    return _FALLBACK.get(colour, colour)


def _banner_art(font: str, scale: int, shear: int) -> list[str]:
    """Render the wordmark: a block font, scaled. The italic shear is applied
    later (in canvas space) so that letters can be recognised before they are
    slanted."""
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
    return art


#: (font, horizontal scale, italic shear) candidates, widest/nicest first.
BANNER_STYLES = (
    ("banner3", 2, 0),  # chunky pixel letters (needs ~130 columns)
    ("banner3", 1, 0),  # compact pixel letters
    ("big", 1, 0),
    ("slant", 1, 0),    # last resort: the thin slanted wordmark
)


def _pick_banner(available_width: int) -> tuple[list[str], int, int]:
    """Pick the biggest wordmark that fits the terminal.

    Returns the (unsheared) art, the italic shear and the horizontal scale.
    """
    forced = os.environ.get("BREACH_BANNER_FONT")
    candidates = ((forced, 2, 0),) if forced else BANNER_STYLES
    for font, scale, shear in candidates:
        lines = _banner_art(font, scale, shear)
        width = max((len(l) for l in lines), default=0)
        if width + 8 + (len(lines) - 1) * shear <= available_width:
            return lines, shear, scale
    font, scale, shear = candidates[-1]
    return _banner_art(font, scale, shear), shear, scale


def banner_lines() -> list[str]:
    """The raw wordmark (letters only, no shadow)."""
    lines, shear, _scale = _pick_banner(_get_console().width)
    height = len(lines)
    return [" " * ((height - 1 - r) * shear) + line for r, line in enumerate(lines)]


def banner_text() -> str:
    """The wordmark as plain text."""
    return "\n".join(banner_lines())


def banner_rich() -> Text:
    """The wordmark: solid red blocks, a green 3D extrusion, and a thin
    '/' style border tracing the perimeter of every letter.

    The border sits one cell away from the blocks, so each letter keeps a
    clean gap around it — the reference artwork's look, but per letter
    instead of one big frame.
    """
    base_lines, shear, scale = _pick_banner(_get_console().width)
    height = len(base_lines)
    base_width = max((len(l) for l in base_lines), default=0)
    base = [[ch != " " for ch in line.ljust(base_width)] for line in base_lines]

    # the italic shear: every row is pushed right as it goes down
    shift = [(height - 1 - r) * shear for r in range(height)]
    width = base_width + shift[0]

    # the sheared art (what we actually draw)
    art = [[False] * width for _ in range(height)]
    for r in range(height):
        for c in range(base_width):
            if base[r][c]:
                art[r][c + shift[r]] = True

    # padding: room for the gap, the border and the extrusion
    pad = 4
    out_h, out_w = height + 2 * pad, width + 2 * pad

    def is_ink(r: int, c: int) -> bool:
        """Canvas-space ink test (the art is drawn at offset `pad`)."""
        rr, cc = r - pad, c - pad
        return 0 <= rr < height and 0 <= cc < width and art[rr][cc]

    def base_pos(r: int, c: int) -> tuple[int, int]:
        """Sheared canvas position of an unsheared art cell."""
        return r, c + shift[r]

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
    rim = _hex(GREEN_RIM)

    # the vertical gradient of the letter fill (dark at the top, light at the
    # bottom) — the reference logo's signature look
    gradient: list[Optional[str]] = []
    for r in range(height):
        t = r / max(1, height - 1)
        colour = _mix(GRAD_TOP, GRAD_BOTTOM, t)
        gradient.append(colour if _hex(colour) == colour else None)

    canvas: list[list[tuple[Optional[str], str]]] = [
        [(None, " ") for _ in range(out_w)] for _ in range(out_h)
    ]

    # --- the letters ---
    for r in range(height):
        style = gradient[r] or fill
        for c in range(base_width):
            if not base[r][c]:
                continue
            sr, sc = base_pos(r, c)
            canvas[sr + pad][sc + pad] = (style, "█")

    # --- the green extrusion: every letter copied one cell down-right ---
    for r in range(height):
        for c in range(base_width):
            if not base[r][c]:
                continue
            sr, sc = base_pos(r, c)
            rr, cc = sr + pad + 1, sc + pad + 1
            if rr < out_h and cc < out_w and canvas[rr][cc][0] is None:
                canvas[rr][cc] = (rim, "█")

    # trim the empty rows above and below the wordmark (keep one on top)
    first = 0
    while first < out_h and all(canvas[first][c][0] is None for c in range(out_w)):
        first += 1
    start = max(0, first - 1)
    last = out_h - 1
    while last > first and all(canvas[last][c][0] is None for c in range(out_w)):
        last -= 1

    text = Text()
    for r in range(start, last + 1):
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
