"""Stage 11 — The Breach CLI (Typer + rich).

Commands
    breach check "<claim>"        check a claim (or --example euler)
    breach chat                   interactive blackboard session
    breach challenge <id> "<obj>"  contest a specific proof step
    breach export <fmt>           export the current session (md/html/txt)
    breach examples               list the built-in greatest-hits gallery
    breach web                    launch the web interface

The CLI is a *thin wrapper*: it never implements solver logic itself, it only
calls into engine / orchestrator / cases / argue.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import webbrowser
from typing import Optional

import typer
from rich.panel import Panel
from rich.prompt import Prompt as RichPrompt
from rich.table import Table

from . import ui_theme as theme
from .paths import OUTPUT_DIR, PROJECT_ROOT, SESSION_FILE as DEFAULT_SESSION_FILE
from .argue import apply_patch, challenge_step, diagnose_failure, offer_patch
from .citations import attach_citations
from .engine import breach_check, check_with_form
from .examples import EXAMPLES, get_example, list_examples
from .export import export_proof
from .llm_client import get_client
from .memory import ProofMemory
from .state import ProofState
from .symbols import apply_shortcut, find_completion

SESSION_FILE = os.environ.get("BREACH_SESSION_FILE", DEFAULT_SESSION_FILE)
WEB_PORT = int(os.environ.get("BREACH_WEB_PORT", "8501"))

app = typer.Typer(
    name="breach",
    help="Breach — try to break the proof, not confirm it.",
    no_args_is_help=True,
    add_completion=False,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _session_path() -> str:
    return os.path.abspath(SESSION_FILE)


def _save_session(state: ProofState) -> str:
    path = _session_path()
    state.save(path)
    return path


def _load_session() -> Optional[ProofState]:
    path = _session_path()
    if not os.path.exists(path):
        return None
    try:
        return ProofState.load(path)
    except Exception:
        return None


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _web_running() -> bool:
    return _port_open(WEB_PORT)


def _launch_web(state: Optional[ProofState] = None) -> None:
    """Launch (or refocus) the Streamlit UI, keeping the CLI usable."""
    if state is not None:
        _save_session(state)
    if _web_running():
        theme.console.print(
            f"🌐 Web interface already running at http://localhost:{WEB_PORT}"
        )
        webbrowser.open(f"http://localhost:{WEB_PORT}")
        return

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "web.py"),
        "--server.port",
        str(WEB_PORT),
        "--server.headless",
        "true",
        "--",
        "--session",
        _session_path(),
    ]
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=os.getcwd(),
    )
    theme.console.print(
        f"🌐 Launching web interface at http://localhost:{WEB_PORT} — "
        "your current session has been loaded."
    )
    # give streamlit a moment, then open the browser (never block the REPL)
    for _ in range(40):
        if _port_open(WEB_PORT):
            break
        time.sleep(0.25)
    webbrowser.open(f"http://localhost:{WEB_PORT}")
    theme.console.print(
        "[dim]The terminal session stays live — the two views share the same "
        "proof state file.[/dim]"
    )


def _print_state(state: ProofState) -> None:
    theme.console.print(theme.verdict_panel(state))
    if state.steps:
        theme.console.print(theme.steps_table(state))
    if state.search_certificate:
        theme.console.print(theme.certificate_panel(state.search_certificate))
    if state.citations:
        table = Table(title="Related work", show_header=False, box=None)
        for c in state.citations:
            table.add_row(f"[bold]{c.title}[/bold]", f"{c.authors_or_source} — {c.relevance_note}")
        theme.console.print(table)


def _export_and_report(state: ProofState, formats: list[str]) -> list[str]:
    """Export the session and make the file easy to get hold of.

    - every requested format is written to `outputs/`
    - the .html file is opened in the default browser (so it can be saved
      straight from the browser, or printed to PDF)
    - the path of the HTML report is copied to the clipboard, ready to paste
      into Explorer, a download bar or a chat window
    """
    from .clipboard import copy_to_clipboard

    paths: list[str] = []
    for fmt in formats:
        try:
            paths.append(export_proof(state, fmt))
        except ValueError as exc:
            theme.err_console.print(str(exc))
        except Exception as exc:  # noqa: BLE001
            theme.err_console.print(f"export failed: {exc}")

    if not paths:
        return []

    folder = os.path.dirname(paths[0])
    theme.console.print(f"📁 [bold]{len(paths)} file(s) written to {folder}[/bold]")
    for path in paths:
        theme.console.print(f"   • [bold]{os.path.basename(path)}[/bold]")

    html = next((p for p in paths if p.lower().endswith(".html")), None)
    if html:
        try:
            webbrowser.open(html)
            theme.console.print(
                "[dim]Opened the HTML report in your browser — Ctrl+S to save it, "
                "or Ctrl+P to print it to PDF.[/dim]"
            )
        except Exception:
            pass

    # the clipboard gets the most useful file: the HTML report if there is one
    primary = html or paths[0]
    if copy_to_clipboard(primary):
        theme.console.print(f"📋 Copied to clipboard: [dim]{primary}[/dim]")
    else:
        theme.console.print("[dim]Tip: copy the path above into Explorer to open it.[/dim]")
    return paths


def _expand_symbols(text: str) -> str:
    """Apply a symbol shortcut at the end of the input, announcing it."""
    if find_completion(text):
        applied = apply_shortcut(text)
        if applied:
            new_text, _ = applied
            theme.console.print(f"[dim]→ symbol shortcut applied: {new_text}[/dim]")
            return new_text
    return text


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def _run_example(
    key: str,
    memory: Optional[ProofMemory] = None,
    timeout: float = 10.0,
    as_json: bool = False,
):
    """Run one of the built-in gallery examples. Returns the ProofState."""
    ex = get_example(key)
    if ex is None:
        theme.err_console.print(f"[{theme.ACCENT}]Unknown example:[/] {key}")
        theme.console.print("Available: " + ", ".join(sorted(EXAMPLES.keys())))
        return None
    if not as_json:
        theme.console.print(
            Panel(
                f"[bold]{ex.title}[/bold]\n\n{ex.claim}\n\n[dim]{ex.history}[/dim]",
                border_style=theme.ACCENT_SOFT,
                expand=False,
            )
        )
    with theme.status_spinner("searching for a counterexample..."):
        state = check_with_form(ex.form, ex.claim, memory=memory or ProofMemory(),
                                timeout=max(timeout, 30))
    if as_json:
        print(json.dumps(state.serialize_to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_state(state)
    if state.verdict == "counterexample_found":
        with theme.status_spinner("performing the autopsy..."):
            state = diagnose_failure(state, client=get_client())
        theme.console.print(
            f"[{theme.ACCENT}]Autopsy:[/] {state.diagnosis or 'no specific step implicated.'}"
        )
    _save_session(state)
    return state


def _handle_shell_style_input(
    text: str,
    state: Optional[ProofState],
    memory: ProofMemory,
) -> bool:
    """Run shell-style commands typed into the REPL.

    Without this, `breach check --example euler` typed into the chat is
    interpreted as a *claim* to attack and comes back UNKNOWN.
    """
    raw = text.strip()
    if not raw:
        return False

    cmd = raw
    if cmd.lower().startswith("breach "):
        cmd = cmd[len("breach ") :].strip()
    lowered = cmd.lower()

    if lowered in ("help", "--help", "-h", "?"):
        theme.console.print(
            "[dim]Inside the chat:[/] type a claim to attack it, or use "
            "/web /challenge /export /examples /clear /quit.\n"
            "You can also type shell-style commands here: "
            "[bold]check \"<claim>\"[/], [bold]check --example euler[/], "
            "[bold]examples[/], [bold]export html[/], [bold]web[/].[/dim]"
        )
        return True

    if lowered in ("examples", "example", "list-examples", "gallery"):
        _print_examples()
        return True

    if lowered in ("web", "--web"):
        _launch_web(state)
        return True

    if lowered.startswith("export"):
        parts = cmd.split()
        fmt = parts[1] if len(parts) > 1 else ""
        if state is None:
            theme.console.print("[dim]Nothing to export yet.[/dim]")
        else:
            _export_and_report(state, [fmt] if fmt else ["md", "html", "txt"])
        return True

    if lowered.startswith("check"):
        rest = cmd[len("check") :].strip()
        if "--example" in rest or rest.startswith("-e "):
            tail = rest.split("--example", 1)[-1] if "--example" in rest else rest[3:]
            key = tail.strip().strip('"').strip("'").split()[0] if tail.strip() else ""
            if key:
                _run_example(key, memory=memory)
            else:
                theme.console.print("[dim]Usage: check --example <key>[/dim]")
            return True
        claim = rest.strip()
        if claim.startswith('"') and claim.endswith('"') and len(claim) > 1:
            claim = claim[1:-1]
        elif claim.startswith("'") and claim.endswith("'") and len(claim) > 1:
            claim = claim[1:-1]
        if claim:
            with theme.status_spinner("BREACH is thinking..."):
                new_state = breach_check(claim, memory=memory, client=get_client())
            _print_state(new_state)
            _save_session(new_state)
        else:
            theme.console.print("[dim]Usage: check \"<claim>\"[/dim]")
        return True

    # a bare gallery key, e.g. "euler"
    if raw.lower() in EXAMPLES:
        theme.console.print(
            f"[dim]Running the gallery example {raw.lower()!r} "
            "(type /examples to list them).[/dim]"
        )
        _run_example(raw.lower(), memory=memory)
        return True

    return False


@app.command()
def check(
    claim: Optional[str] = typer.Argument(None, help="The claim to attack."),
    example: Optional[str] = typer.Option(
        None, "--example", "-e", help="Run a built-in gallery example instead."
    ),
    timeout: float = typer.Option(10.0, "--timeout", help="Solver timeout in seconds."),
    citations: bool = typer.Option(False, "--citations", help="Also look up related work."),
    as_json: bool = typer.Option(False, "--json", help="Print the raw state as JSON."),
) -> None:
    """Try to break a claim."""
    memory = ProofMemory()
    client = get_client()

    if example:
        ex = get_example(example)
        if ex is None:
            theme.err_console.print(f"[{theme.ACCENT}]Unknown example:[/] {example}")
            theme.console.print(
                "Available: " + ", ".join(sorted(EXAMPLES.keys())),
            )
            raise typer.Exit(code=1)
        if not as_json:
            theme.console.print(
                Panel(
                    f"[bold]{ex.title}[/bold]\n\n{ex.claim}\n\n[dim]{ex.history}[/dim]",
                    border_style=theme.ACCENT_SOFT,
                    expand=False,
                )
            )
        with theme.status_spinner("searching for a counterexample..."):
            state = check_with_form(ex.form, ex.claim, memory=memory, timeout=max(timeout, 30))
    elif claim:
        with theme.status_spinner("translating and searching..."):
            state = breach_check(claim, memory=memory, client=client, timeout=timeout)
    else:
        theme.err_console.print("Give a claim, or use --example (see `breach examples`).")
        raise typer.Exit(code=1)

    if citations:
        with theme.status_spinner("looking up related work..."):
            attach_citations(state, client=client)

    if as_json:
        print(json.dumps(state.serialize_to_dict(), indent=2, ensure_ascii=False))
        return

    _print_state(state)

    if state.verdict == "counterexample_found":
        with theme.status_spinner("performing the autopsy..."):
            state = diagnose_failure(state, client=client)
        theme.console.print(
            f"[{theme.ACCENT}]Autopsy:[/] {state.diagnosis or 'no specific step implicated.'}"
        )
        prompt = offer_patch(state)
        if prompt:
            theme.console.print(f"[{theme.ACCENT}]{prompt}[/]")
            if typer.confirm("Apply the patch and re-check?", default=False):
                patched, message = apply_patch(state, client=client, memory=memory)
                theme.console.print(message)
                if patched is not None:
                    state = patched
                    _print_state(state)

    _save_session(state)


@app.command()
def chat() -> None:
    """Interactive session with a persistent proof state."""
    theme.print_banner()
    memory = ProofMemory()
    client = get_client()
    state: Optional[ProofState] = None
    theme.console.print(
        "[dim]Type a claim to attack it. Commands: /web /export /challenge /examples "
        "/clear /quit[/dim]"
    )

    while True:
        try:
            user_input = RichPrompt.ask(
                "[bold]You[/]:", console=theme.console, default="", show_default=False
            )
        except (EOFError, KeyboardInterrupt):
            theme.console.print("\n[dim]bye.[/dim]")
            break
        user_input = (user_input or "").strip()
        if not user_input:
            continue

        if user_input.startswith("/"):
            cmd, _, rest = user_input.partition(" ")
            cmd = cmd.lower()
            rest = rest.strip()
            if cmd in ("/quit", "/exit"):
                break
            if cmd == "/web":
                _launch_web(state)
                continue
            if cmd == "/export":
                fmt = (rest or "").split()[0] if rest else ""
                if state is None:
                    theme.console.print("[dim]Nothing to export yet.[/dim]")
                    continue
                if fmt:
                    _export_and_report(state, [fmt])
                else:
                    # no format given: write all three — the HTML report is
                    # the one you can open (and save) straight away
                    _export_and_report(state, ["md", "html", "txt"])
                continue
            if cmd == "/examples":
                _print_examples()
                continue
            if cmd == "/clear":
                state = None
                theme.console.print("[dim]Board cleared.[/dim]")
                continue
            if cmd == "/challenge":
                if state is None:
                    theme.console.print("[dim]No proof state yet — state a claim first.[/dim]")
                    continue
                parts = rest.split(" ", 1)
                if len(parts) < 2 or not parts[0].isdigit():
                    theme.console.print("[dim]Usage: /challenge <step_id> <objection>[/dim]")
                    continue
                step_id = int(parts[0])
                objection = parts[1]
                with theme.status_spinner("answering the objection..."):
                    state = challenge_step(state, step_id, objection, client=client, memory=memory)
                _print_state(state)
                _save_session(state)
                if state.verdict == "counterexample_found":
                    state = diagnose_failure(state, client=client)
                    prompt = offer_patch(state)
                    if prompt:
                        theme.console.print(f"[{theme.ACCENT}]{prompt}[/]")
                continue
            if cmd == "/help":
                theme.console.print(
                    "[dim]/web  /export md|html|txt  /challenge <id> <objection>  "
                    "/examples  /clear  /quit[/dim]"
                )
                continue
            theme.console.print(f"[dim]Unknown command {cmd}. Try /help[/dim]")
            continue

        user_input = _expand_symbols(user_input)

        with theme.status_spinner("BREACH is thinking..."):
            state = breach_check(user_input, memory=memory, client=client)
        _print_state(state)

        if state.verdict == "counterexample_found":
            with theme.status_spinner("performing the autopsy..."):
                state = diagnose_failure(state, client=client)
            theme.console.print(
                f"[{theme.ACCENT}]Autopsy:[/] {state.diagnosis or 'no specific step implicated.'}"
            )
            prompt = offer_patch(state)
            if prompt:
                theme.console.print(f"[{theme.ACCENT}]{prompt}[/]")
                if typer.confirm("Apply the patch?", default=False):
                    patched, message = apply_patch(state, client=client, memory=memory)
                    theme.console.print(message)
                    if patched is not None:
                        state = patched
                        _print_state(state)
        _save_session(state)


@app.command()
def challenge(
    step_id: int = typer.Argument(..., help="Step number to challenge."),
    objection: str = typer.Argument(..., help="Your objection to that step."),
) -> None:
    """Contest a specific step of the current session."""
    state = _load_session()
    if state is None:
        theme.err_console.print(
            "No saved session found. Run `breach check \"...\"` first, or use `breach chat`."
        )
        raise typer.Exit(code=1)
    client = get_client()
    with theme.status_spinner("answering the objection..."):
        state = challenge_step(state, step_id, objection, client=client)
    _print_state(state)
    _save_session(state)


@app.command()
def export(
    format: str = typer.Argument(
        "", help="md | html | txt — leave empty for all three."
    ),
) -> None:
    """Export the current session to a file (and open the HTML report)."""
    state = _load_session()
    if state is None:
        theme.err_console.print("No saved session found. Run `breach check \"...\"` first.")
        raise typer.Exit(code=1)
    formats = [format] if format else ["md", "html", "txt"]
    paths = _export_and_report(state, formats)
    if not paths:
        raise typer.Exit(code=1)


@app.command()
def search(
    claim: Optional[str] = typer.Argument(None, help="The claim to attack."),
    example: Optional[str] = typer.Option(
        None, "--example", "-e", help="Run a built-in gallery example instead."
    ),
    splits: int = typer.Option(8, "--splits", help="How many cubes to split the space into."),
    workers: int = typer.Option(4, "--workers", help="Parallel workers to dispatch cubes to."),
    timeout: float = typer.Option(10.0, "--timeout", help="Per-cube solver timeout in seconds."),
) -> None:
    """Cube-and-conquer search: split the space, break symmetries, run in parallel."""
    from .cases import run_cube_search
    from .engine import translate_claim

    memory = ProofMemory()
    client = get_client()

    if example:
        ex = get_example(example)
        if ex is None:
            theme.err_console.print(f"[{theme.ACCENT}]Unknown example:[/] {example}")
            raise typer.Exit(code=1)
        form = ex.form
        claim_text = ex.claim
    elif claim:
        with theme.status_spinner("translating..."):
            form = translate_claim(claim, client=client, memory=memory)
        claim_text = claim
    else:
        theme.err_console.print("Give a claim, or use --example (see `breach examples`).")
        raise typer.Exit(code=1)

    theme.console.print(
        f"[dim]Splitting the search space into cubes and dispatching them across "
        f"{workers} workers...[/dim]"
    )
    with theme.status_spinner("searching cubes in parallel..."):
        results, cert = run_cube_search(
            form,
            claim_text,
            memory=memory,
            num_splits=splits,
            workers=workers,
            timeout=timeout,
        )
    theme.console.print(theme.certificate_panel(cert))
    theme.console.print(
        f"[bold]Searched {cert.get('cubes_solved', 0)} cases across "
        f"{cert.get('workers', workers)} workers in "
        f"{cert.get('wall_clock_seconds', 0)}s "
        f"(eliminated {cert.get('cubes_eliminated_by_symmetry', 0)} by symmetry).[/bold]"
    )
    sat = [r for r in results if r["verdict"] == "counterexample_found"]
    if sat:
        theme.console.print(
            f"[{theme.ACCENT}]Counterexample found in cube {sat[0]['cube_id']}:[/] "
            f"{sat[0].get('counterexample')}"
        )
    else:
        theme.console.print(
            "[green]No cube produced a counterexample in the searched space.[/green]"
        )
    theme.console.print(
        "[dim]For comparison, the 2016 Boolean Pythagorean Triples proof covered "
        "~2^7825 cases on 800 cores over 2 days. This is the same architecture, "
        "at laptop scale — not a replication of that result.[/dim]"
    )


@app.command()
def examples() -> None:
    """List the built-in greatest-hits gallery."""
    _print_examples()


@app.command()
def web() -> None:
    """Launch the web interface with the current session."""
    _launch_web(_load_session())


def _print_examples() -> None:
    table = Table(title="Breach greatest hits", header_style=f"bold {theme.ACCENT}")
    table.add_column("key", style="bold")
    table.add_column("title")
    table.add_column("expect", width=12)
    table.add_column("history", overflow="fold")
    for ex in list_examples():
        table.add_row(ex.key, ex.title, ex.expected.replace("_", " "), ex.history)
    theme.console.print(table)
    theme.console.print("[dim]Try: breach check --example euler[/dim]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
