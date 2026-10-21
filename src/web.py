"""Stage 12 — The web interface (Streamlit).

Two panels over ONE shared `ProofState`:

    BLACKBOARD — canvas drawing -> vision transcription -> proof steps
    CHAT       — conversational claims, symbol shortcuts, challenges

Both panels read and write the same state, and the state is synced to the
session file so the CLI and the browser never disagree. The CLI and this file
are thin wrappers: every solver call goes through `engine`.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Optional

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import ui_theme as theme  # noqa: E402
from src.argue import apply_patch, challenge_step, diagnose_failure, offer_patch  # noqa: E402
from src.citations import attach_citations  # noqa: E402
from src.engine import breach_check  # noqa: E402
from src.export import export_proof  # noqa: E402
from src.llm_client import get_client  # noqa: E402
from src.memory import ProofMemory  # noqa: E402
from src.state import ProofState  # noqa: E402
from src.symbols import apply_shortcut, find_completion  # noqa: E402

# ---------------------------------------------------------------------------
# Session file (shared with the CLI)
# ---------------------------------------------------------------------------
DEFAULT_SESSION = os.path.abspath(".breach_session.json")


def _session_path_from_args() -> str:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    if "--session" in argv:
        i = argv.index("--session")
        if i + 1 < len(argv):
            return os.path.abspath(argv[i + 1])
    return DEFAULT_SESSION


SESSION_PATH = _session_path_from_args()


@st.cache_resource
def _memory() -> ProofMemory:
    return ProofMemory()


def _load_state_from_disk() -> Optional[ProofState]:
    if not os.path.exists(SESSION_PATH):
        return None
    try:
        return ProofState.load(SESSION_PATH)
    except Exception:
        return None


def _save_state_to_disk(state: ProofState) -> None:
    try:
        state.save(SESSION_PATH)
    except Exception:
        pass


def _file_mtime() -> float:
    try:
        return os.path.getmtime(SESSION_PATH)
    except OSError:
        return 0.0


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Breach", page_icon="🕳️", layout="wide")

st.markdown(
    """
    <style>
      .stApp { --accent: #d1380d; }
      h1, h2, h3 { color: #d1380d; }
      .breach-banner {
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-weight: 800; letter-spacing: .12em; color: #d1380d;
        border: 2px solid #d1380d; border-radius: 8px;
        padding: .6rem 1rem; display: inline-block; margin-bottom: .6rem;
      }
      .verdict-counter { border-left: 4px solid #d1380d; padding: .5rem .8rem;
                        background: rgba(209,56,13,.10); border-radius: 6px; }
      .verdict-clear   { border-left: 4px solid #2e7d32; padding: .5rem .8rem;
                        background: rgba(46,125,50,.10); border-radius: 6px; }
      .verdict-unknown { border-left: 4px solid #b26a00; padding: .5rem .8rem;
                        background: rgba(178,106,0,.10); border-radius: 6px; }
      .step { border-left: 3px solid #d1380d; padding: .3rem .7rem; margin: .3rem 0; }
      .muted { opacity: .7; font-size: .88rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="breach-banner">BREACH</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="muted">Try to break the proof, not confirm it. The LLM translates; '
    "the solver decides.</div>",
    unsafe_allow_html=True,
)


def _init_state() -> None:
    if "proof_state" not in st.session_state:
        loaded = _load_state_from_disk()
        st.session_state.proof_state = loaded
        st.session_state.messages = []
        st.session_state.disk_mtime = _file_mtime()
        st.session_state.transcription = ""
        if loaded is not None:
            st.session_state.messages.append(
                {"role": "breach", "content": f"Session restored: **{loaded.claim}**"}
            )


_init_state()


def _sync_from_disk() -> None:
    """Reload if the CLI changed the session file."""
    mtime = _file_mtime()
    if mtime and mtime != st.session_state.disk_mtime:
        loaded = _load_state_from_disk()
        if loaded is not None:
            st.session_state.proof_state = loaded
        st.session_state.disk_mtime = mtime
        st.rerun()


def _push_state(state: Optional[ProofState]) -> None:
    st.session_state.proof_state = state
    if state is not None:
        _save_state_to_disk(state)
        st.session_state.disk_mtime = _file_mtime()


def _render_state(state: Optional[ProofState]) -> None:
    if state is None:
        st.info("No claim under attack yet.")
        return
    css = {
        "counterexample_found": "verdict-counter",
        "no_counterexample_in_bound": "verdict-clear",
        "unknown": "verdict-unknown",
    }.get(state.verdict, "verdict-unknown")
    label = {
        "counterexample_found": "⚠️ COUNTEREXAMPLE FOUND — the claim is false here",
        "no_counterexample_in_bound": "✅ NO COUNTEREXAMPLE FOUND in the searched bound",
        "unknown": "❓ UNKNOWN — the solver could not decide it",
    }.get(state.verdict, state.verdict)
    st.markdown(f'<div class="{css}"><strong>{label}</strong></div>', unsafe_allow_html=True)

    if state.counterexample:
        st.markdown("**Counterexample**")
        st.code("\n".join(f"{k} = {v}" for k, v in state.counterexample.items()), language="text")
    if state.verdict == "unknown" and state.unknown_info:
        info = state.unknown_info
        st.markdown(f"**Why we stopped** — {info.detail}")
        st.caption(f"classification: {info.kind} (confidence {info.confidence:.0%})")
        if info.remedy:
            st.caption(f"what would help: {info.remedy}")
    if state.scope_note:
        st.caption(f"Scope: {state.scope_note}")
    if state.symbolic_form:
        with st.expander("Formalisation", expanded=False):
            st.code(state.symbolic_form, language="text")
    if state.steps:
        st.markdown("**Proof steps**")
        for s in state.steps:
            mark = "⚠ implicated" if s.implicated else s.status
            st.markdown(f'<div class="step"><strong>{s.id}.</strong> {s.text} <em>({mark})</em></div>',
                        unsafe_allow_html=True)
            if s.challenge_text:
                st.markdown(f"   - **Challenge:** {s.challenge_text}")
                if s.agent_response:
                    st.markdown(f"   - **Response:** {s.agent_response}")
            if s.missing_assumption:
                st.markdown(f"   - **Missing assumption:** `{s.missing_assumption}`")
    if state.diagnosis:
        st.warning(f"Autopsy: {state.diagnosis}")
    if state.search_certificate:
        with st.expander("Search certificate"):
            st.json(state.search_certificate)
    if state.citations:
        st.markdown("**Related work**")
        for c in state.citations:
            st.markdown(f"- **{c.title}** — {c.authors_or_source}. {c.relevance_note}")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_bb, tab_chat, tab_side = st.tabs(["🧠 BLACKBOARD", "💬 CHAT", "📚 TOOLS"])

with tab_bb:
    st.subheader("Draw it — we transcribe it, you confirm it")
    st.caption(
        "Sketch the claim or the proof. The transcription is shown to you for "
        "confirmation before anything is checked — we never guess silently."
    )
    col_canvas, col_out = st.columns([3, 2])

    with col_canvas:
        try:
            from streamlit_drawable_canvas import st_canvas

            canvas = st_canvas(
                fill_color="rgba(209,56,13,0.15)",
                stroke_color="#d1380d",
                stroke_width=3,
                background_color="#ffffff",
                height=340,
                width=560,
                drawing_mode="freedraw",
                key="breach_canvas",
            )
        except Exception as exc:
            canvas = None
            st.warning(f"Canvas component unavailable ({exc}). Use the CHAT tab to type a claim.")

    with col_out:
        if canvas is not None and st.button("🎨 Transcribe drawing", type="primary"):
            with st.spinner("Transcribing (low-confidence parts are marked UNCLEAR)..."):
                try:
                    from src.vision import transcribe_drawing

                    image = canvas.image_data
                    buf = None
                    if image is not None:
                        from io import BytesIO

                        buf = BytesIO()
                        image.save(buf, format="PNG")
                    if buf is not None:
                        text = transcribe_drawing(buf.getvalue())
                        st.session_state.transcription = text
                except Exception as exc:
                    st.error(f"Transcription failed: {exc}")

        st.text_area(
            "Transcription (edit if needed, then check)",
            key="transcription_field",
            value=st.session_state.get("transcription", ""),
            height=140,
        )

        if st.button("⚔️ Check this claim", type="primary"):
            claim = st.session_state.get("transcription_field", "").strip()
            if not claim:
                st.warning("Nothing to check yet — transcribe or type a claim.")
            else:
                with st.spinner("BREACH is thinking..."):
                    state = breach_check(claim, memory=_memory(), client=get_client())
                    if state.verdict == "counterexample_found":
                        state = diagnose_failure(state, client=get_client())
                _push_state(state)
                st.session_state.messages.append({"role": "breach", "content": f"Checked: {claim}"})
                st.rerun()

    st.divider()
    st.subheader("The board")
    _render_state(st.session_state.proof_state)

with tab_chat:
    st.subheader("Challenge the argument")
    for m in st.session_state.messages:
        if m["role"] == "user":
            st.markdown(f"**You:** {m['content']}")
        else:
            st.markdown(m["content"])
    st.divider()

    text = st.text_input(
        "Your claim or objection",
        key="chat_input",
        placeholder="e.g. for all integers n, n^2 >= 0   (type 'pi' and press space)",
    )
    preview = find_completion(text) if text else None
    if preview:
        token, replacement = preview
        st.caption(f"symbol shortcut ready: {token} → {replacement}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("💬 Send", type="primary"):
            raw = (text or "").strip()
            if raw:
                if find_completion(raw):
                    applied = apply_shortcut(raw)
                    if applied:
                        raw, _ = applied
                        st.caption(f"symbol shortcut applied: {raw}")
                st.session_state.messages.append({"role": "user", "content": raw})
                with st.spinner("BREACH is thinking..."):
                    state = breach_check(raw, memory=_memory(), client=get_client())
                    if state.verdict == "counterexample_found":
                        state = diagnose_failure(state, client=get_client())
                _push_state(state)
                st.session_state.chat_input = ""
                st.rerun()
    with c2:
        if st.button("🎯 Challenge a step"):
            st.session_state.show_challenge = True

    if st.session_state.get("show_challenge"):
        state = st.session_state.proof_state
        with st.form("challenge_form"):
            step_ids = [s.id for s in (state.steps if state else [])]
            step_id = st.selectbox("Step", step_ids or [1])
            objection = st.text_input("Your objection (e.g. 'what if a = 0?')")
            go = st.form_submit_button("Challenge it")
        if go and objection:
            with st.spinner("answering that specific objection..."):
                state = challenge_step(state, int(step_id), objection, client=get_client(), memory=_memory())
                if state.verdict == "counterexample_found":
                    state = diagnose_failure(state, client=get_client())
            _push_state(state)
            st.session_state.messages.append(
                {"role": "user", "content": f"Challenge to step {step_id}: {objection}"}
            )
            st.session_state.show_challenge = False
            st.rerun()

    if st.session_state.proof_state is not None:
        prompt = offer_patch(st.session_state.proof_state)
        if prompt:
            st.markdown(f"**{prompt}**")
            if st.button("Apply the patch and re-check"):
                patched, message = apply_patch(
                    st.session_state.proof_state, client=get_client(), memory=_memory()
                )
                st.session_state.messages.append({"role": "breach", "content": message})
                if patched is not None:
                    _push_state(patched)
                st.rerun()

with tab_side:
    st.subheader("Tools")
    state = st.session_state.proof_state
    if state is None:
        st.info("Run a check first.")
    else:
        st.markdown("**Export this session**")
        fmt = st.selectbox("format", ["md", "html", "txt"])
        if st.button("📄 Export"):
            path = export_proof(state, fmt)
            st.success(f"Saved to {path}")
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
            st.download_button("Download", content, file_name=os.path.basename(path))

        st.divider()
        st.markdown("**Related work**")
        if st.button("🔎 Look up citations"):
            with st.spinner("Looking up related work..."):
                attach_citations(state, client=get_client())
            _push_state(state)
            st.rerun()
        if state.citations:
            for c in state.citations:
                st.markdown(f"- **{c.title}** — {c.authors_or_source}. {c.relevance_note}")
        else:
            st.caption("No citations yet. Breach returns an empty list rather than inventing one.")

        st.divider()
        st.caption(f"Session file: {SESSION_PATH}")
        if st.button("🔄 Reload from disk"):
            _sync_from_disk()

st.divider()
st.caption(
    "Breach uses the LLM only to translate language into solver-checkable form. "
    "All verification is done by Z3 / SymPy. 'No counterexample found' is not a proof of truth."
)


@st.fragment(run_every=2.0)
def _poll_disk() -> None:
    """Keep the browser in sync with the CLI (both read/write the same file)."""
    mtime = _file_mtime()
    if mtime and mtime != st.session_state.disk_mtime:
        loaded = _load_state_from_disk()
        if loaded is not None:
            st.session_state.proof_state = loaded
        st.session_state.disk_mtime = mtime
        st.rerun()


try:
    _poll_disk()
except Exception:
    pass
