"""Stage 10 — Shared visual theme for the CLI and the web UI.

Reference: the SKY CLI (ASCII banner in a bordered box, coloured status lines,
bold user prompt, "thinking..." spinner). The accent here is red/orange —
this is an adversarial tool, not a friendly one.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional

# Windows consoles often default to cp1252, which cannot encode the status
# icons we use. Force UTF-8 (and never crash on an unencodable character).
for _stream in (sys.stdout, sys.stderr):
    try:  # pragma: no cover - platform dependent
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# -- palette ---------------------------------------------------------------
ACCENT = "bright_red"
ACCENT_SOFT = "orange1"
LETTER = "light_green"  # the BREACH wordmark itself
WARN = "yellow"
OK = "green"
DIM = "dim"
MUTED = "grey62"

VERDICT_STYLE = {
    "counterexample_found": ("⚠️", "bold bright_red", "counterexample found"),
    "no_counterexample_in_bound": ("✅", "bold green", "no counterexample found in bound"),
    "unknown": ("❓", "bold yellow", "unknown"),
}

STATUS_ICON = {
    "unchallenged": "•",
    "challenged": "?",
    "resolved": "✓",
    "implicated": "⚠",
}

console = Console()
err_console = Console(stderr=True)


def _letter_style() -> str:
    """Style for the BREACH wordmark: a light green that survives every terminal.

    Rich's 16-colour downgrade maps light greens onto cyan, so we only use the
    exact hex colour when the terminal can actually show it; otherwise we fall
    back to the 16-colour bright green.
    """
    system = getattr(console, "color_system", None)
    system = getattr(system, "name", system)
    if system in ("truecolor", "eight_bit"):
        return f"bold #{LETTER_HEX}"
    # 16-colour terminals: bright green is the closest light green.
    return "bold bright_green"


LETTER_HEX = "90EE90"  # CSS lightgreen
SHADOW_HEX = "555555"  # dark grey drop shadow
PANEL_HEX = "262626"  # dark charcoal background


def make_console(**kwargs: Any) -> Console:
    kwargs.setdefault("style", None)
    return Console(**kwargs)


def _banner_art(font: str, scale: int) -> list[str]:
    """Render the wordmark with a font, scaled horizontally."""
    try:
        import pyfiglet

        art = pyfiglet.figlet_format("BREACH", font=font).splitlines()
    except Exception:
        art = []
    if not art:
        art = [
            " ____ ____  ____  _____ ______ ______  _____",
            "| __ )  _ \\|  _ \\| ____|  ____|  ____|| ____|",
            "|  _ \\ | | | | | |  _| |__   |__   | |__ |  _|",
            "| |_) || |_| | | | |____|  __|  __|  |  _| |___",
            "|____/ \\___/|_| |_|_____|_|   |_|    |_| |_",
        ]
    scaled = ["".join(ch * scale for ch in line).rstrip() for line in art]
    while scaled and not scaled[-1]:
        scaled.pop()
    return scaled


#: (font, horizontal scale) candidates, widest/nicest first.
BANNER_STYLES = (
    ("slant", 1),      # the slanted, italic wordmark
    ("smslant", 1),
    ("banner3", 1),
    ("big", 2),
)


def _pick_banner(available_width: int) -> tuple[str, list[str]]:
    """Pick the biggest wordmark that fits the terminal."""
    forced = os.environ.get("BREACH_BANNER_FONT")
    candidates = ((forced, 2),) if forced else BANNER_STYLES
    for font, scale in candidates:
        lines = _banner_art(font, scale)
        width = max((len(l) for l in lines), default=0)
        if width + 6 <= available_width:
            return font, lines
    # nothing fits comfortably — use the smallest and let rich clip
    return (forced or "banner3"), _banner_art(forced or "banner3", 1)


def banner_text() -> str:
    """The BREACH wordmark as raw text (solid block letters)."""
    _font, lines = _pick_banner(console.width)
    return "\n".join(lines)


def banner_lines() -> list[str]:
    """The wordmark rendered as solid blocks (pyfiglet 'banner3')."""
    _font, lines = _pick_banner(console.width)
    return lines


def _fill_style() -> str:
    """Light green for the inside of the letters (survives 16-colour terminals)."""
    system = getattr(console, "color_system", None)
    system = getattr(system, "name", system)
    if system in ("truecolor", "eight_bit"):
        return f"bold #{LETTER_HEX}"
    return "bold bright_green"


def _panel_style() -> str:
    """Dark charcoal panel background."""
    system = getattr(console, "color_system", None)
    system = getattr(system, "name", system)
    if system in ("truecolor", "eight_bit"):
        return f"on #{PANEL_HEX}"
    return "on black"


def print_banner(con: Optional[Console] = None) -> None:
    """The retro italic BREACH wordmark (see `src/banner.py`)."""
    from .banner import print_banner as _print_banner

    _print_banner(con or console)


def status_spinner(text: str = "BREACH is thinking..."):
    """`console.status` wrapper used around *every* solver/LLM call."""
    return console.status(f"[{DIM}]{text}[/{DIM}]", spinner="dots")


def verdict_panel(state: Any) -> Panel:
    """Render a `ProofState` verdict as a rich panel."""
    icon, style, label = VERDICT_STYLE.get(
        getattr(state, "verdict", "unknown"), ("❓", "bold yellow", "unknown")
    )
    body = Text()
    body.append(f"{icon}  ", style=style)
    body.append(label.upper(), style=style)
    body.append("\n\n")
    body.append("Claim: ", style=DIM)
    body.append(getattr(state, "claim", ""), style="bold")

    if getattr(state, "verdict", "") == "counterexample_found" and state.counterexample:
        body.append("\nCounterexample:\n", style=DIM)
        for k, v in state.counterexample.items():
            body.append(f"  {k} = ", style=ACCENT_SOFT)
            body.append(f"{v}\n", style="bold")

    if getattr(state, "verdict", "") == "no_counterexample_in_bound":
        body.append("\n", style=DIM)
        body.append(
            "No assignment in the searched bound violates the claim.\n",
            style=OK,
        )
        body.append(
            "This is not a proof of truth — it is the absence of a counterexample "
            "inside the bound that was searched.",
            style=DIM,
        )

    if getattr(state, "verdict", "") == "unknown":
        info = getattr(state, "unknown_info", None)
        if info:
            body.append("\n\nWhy we stopped:\n", style=DIM)
            body.append(f"  {info.detail}\n", style=WARN)
            body.append(
                f"  classification: {info.kind} (confidence {info.confidence:.0%})\n",
                style=DIM,
            )
            if info.remedy:
                body.append(f"  what would help: {info.remedy}\n", style=DIM)

    if getattr(state, "scope_note", ""):
        body.append("\n\nScope: ", style=DIM)
        body.append(state.scope_note, style=DIM)

    if getattr(state, "diagnosis", ""):
        body.append("\n\nAutopsy: ", style=ACCENT_SOFT)
        body.append(state.diagnosis, style="bold")

    return Panel(body, border_style=ACCENT, expand=False)


def steps_table(state: Any) -> Table:
    """The blackboard: one row per proof step."""
    table = Table(
        show_header=True,
        header_style=f"bold {ACCENT}",
        box=None,
        pad_edge=False,
    )
    table.add_column("#", style=DIM, width=3)
    table.add_column("Step", overflow="fold")
    table.add_column("Status", width=12)
    for step in getattr(state, "steps", []) or []:
        if step.implicated:
            status = f"[{ACCENT}]⚠ implicated[/]"
        else:
            status = f"[{MUTED}]{STATUS_ICON.get(step.status, '•')} {step.status}[/]"
        table.add_row(str(step.id), step.text, status)
        if step.challenge_text:
            table.add_row("", f"[{WARN}]challenge: {step.challenge_text}[/]", "")
        if step.agent_response:
            table.add_row("", f"[{MUTED}]→ {step.agent_response}[/]", "")
        if step.missing_assumption:
            table.add_row(
                "",
                f"[{ACCENT}]missing assumption: {step.missing_assumption}[/]",
                "",
            )
    return table


def certificate_panel(cert: dict[str, Any]) -> Panel:
    body = Text()
    body.append(f"Cases generated: {cert.get('total_cubes', 0)}\n")
    body.append(f"Cases searched: {cert.get('cubes_solved', 0)}\n")
    body.append(f"Eliminated by symmetry: {cert.get('cubes_eliminated_by_symmetry', 0)}\n")
    body.append(f"Workers: {cert.get('workers', 1)}\n")
    body.append(f"Wall clock: {cert.get('wall_clock_seconds', 0)}s\n")
    body.append(
        f"SAT: {cert.get('sat', 0)}  UNSAT: {cert.get('unsat', 0)}  unknown: {cert.get('unknown', 0)}\n",
        style=OK,
    )
    if cert.get("landmark_scale_note"):
        body.append("\n" + cert["landmark_scale_note"], style=DIM)
    return Panel(body, title="Search Certificate", border_style=ACCENT_SOFT, expand=False)
