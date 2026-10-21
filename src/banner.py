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
    ("banner3", 2, 2),  # chunky italic blocks (needs ~132 columns)
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
    """The wordmark: solid red blocks, a green 3D extrusion, and a thin
    '/' style border tracing the perimeter of every letter.

    The border sits one cell away from the blocks, so each letter keeps a
    clean gap around it — the reference artwork's look, but per letter
    instead of one big frame.
    """
    lines = _pick_banner(_get_console().width)
    height = len(lines)
    width = max((len(l) for l in lines), default=0)
    art = [[ch != " " for ch in line.ljust(width)] for line in lines]

    # padding: room for the gap, the border and the extrusion
    pad = 4
    out_h, out_w = height + 2 * pad, width + 2 * pad

    def is_ink(r: int, c: int) -> bool:
        """Canvas-space ink test (the art is drawn at offset `pad`)."""
        rr, cc = r - pad, c - pad
        return 0 <= rr < height and 0 <= cc < width and art[rr][cc]

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

    canvas: list[list[tuple[Optional[str], str]]] = [
        [(None, " ") for _ in range(out_w)] for _ in range(out_h)
    ]

    # --- the letters ---
    for r in range(height):
        for c in range(width):
            if art[r][c]:
                canvas[r + pad][c + pad] = (fill, "█")

    # --- the green extrusion: every letter copied one cell down-right ---
    for r in range(height):
        for c in range(width):
            if not art[r][c]:
                continue
            rr, cc = r + pad + 1, c + pad + 1
            if rr < out_h and cc < out_w and canvas[rr][cc][0] is None:
                canvas[rr][cc] = (rim, "█")

    # --- a thin '/' style border hugging the perimeter of every letter ---
    def near(r: int, c: int, radius: int) -> bool:
        """Is (r, c) within `radius` cells of any ink cell?"""
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                if is_ink(r + dr, c + dc):
                    return True
        return False

    # --- label the letters (connected components) so each one gets its own
    # --- border, and so the border never rises above its letter ---
    labels: dict[tuple[int, int], int] = {}
    components: dict[int, list[tuple[int, int]]] = {}
    label = 0
    for r in range(height):
        for c in range(width):
            if not art[r][c] or (r, c) in labels:
                continue
            label += 1
            stack = [(r, c)]
            members: list[tuple[int, int]] = []
            labels[(r, c)] = label
            while stack:
                cr, cc = stack.pop()
                members.append((cr, cc))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = cr + dr, cc + dc
                    if (
                        0 <= nr < height
                        and 0 <= nc < width
                        and art[nr][nc]
                        and (nr, nc) not in labels
                    ):
                        labels[(nr, nc)] = label
                        stack.append((nr, nc))
            components[label] = members
    comp_top = {lab: min(r for r, _ in cells) for lab, cells in components.items()}

    for r in range(out_h):
        for c in range(out_w):
            if canvas[r][c][0] is not None:
                continue
            if near(r, c, 1):
                continue  # keep a one-cell gap around the blocks
            if not near(r, c, 2):
                continue  # only the immediate perimeter
            if not outside[r][c]:
                continue  # inside an enclosed counter -> leave it dark
            above = is_ink(r - 2, c)
            below = is_ink(r + 2, c)
            left = is_ink(r, c - 2)
            right = is_ink(r, c + 2)
            if below and not above:
                continue  # no top edge: the border only runs down the sides
            # never rise above the letter this border belongs to
            ar, ac = r - pad, c - pad
            owners = {
                labels[(ar + dr, ac + dc)]
                for dr in (-2, -1, 0, 1, 2)
                for dc in (-2, -1, 0, 1, 2)
                if (ar + dr, ac + dc) in labels
            }
            if owners and all(ar < comp_top[lab] for lab in owners):
                continue
            char = "_" if (above or below) and not (left or right) else "/"
            canvas[r][c] = (rim, char)

    # --- a dashed line exactly above the heads of the letters ---
    dashes: dict[int, list[tuple[int, int]]] = {}
    for lab, cells in components.items():
        heads: dict[int, int] = {}
        for r, c in cells:
            if c not in heads or r < heads[c]:
                heads[c] = r
        for c, head in heads.items():
            rr, cc = head - 2 + pad, c + pad
            if not (0 <= rr < out_h and 0 <= cc < out_w):
                continue
            if canvas[rr][cc][0] is not None:
                continue
            # the dash must sit in open space, right above the letter's head
            clash = False
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if labels.get((rr + dr - pad, cc + dc - pad)):
                        clash = True
            if clash:
                continue
            # ...and above everything else in that column
            if any(art[ar][c] for ar in range(0, head)):
                continue
            # ...and clear of any other letter's strokes
            for other, cells in components.items():
                if other == lab:
                    continue
                for orow, ocol in cells:
                    if abs(orow - (head - 2)) <= 2 and abs(ocol - c) <= 2:
                        clash = True
                        break
                if clash:
                    break
            if clash:
                continue
            dashes.setdefault(lab, []).append((rr, cc))

    # one line per letter: paint them, then keep only the highest of each
    for lab, cells in dashes.items():
        top = min(r for r, _ in cells)
        for rr, cc in cells:
            if rr == top:
                canvas[rr][cc] = (rim, "-")
            else:
                canvas[rr][cc] = (None, " ")

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
