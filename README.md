# BREACH — adversarial math checking agent

![BREACH CLI screenshot](docs/breach-cli.png)

> *"LLMs can hallucinate a proof that looks right. Breach's job is to try to **break** your proof, not confirm it."*

Breach is an adversarial mathematics agent. Give it an informal claim and it does
not try to prove it true — it tries to **falsify** it, using real solvers (Z3,
SymPy) to hunt for a counterexample, and it tells you honestly when it cannot
resolve something.

**Repository:** https://github.com/SoumalyaSaha/Breach

```
   ┌───────────┐   natural language    ┌────────────┐   structured form   ┌──────────┐
   │   claim   │ ────────────────────► │  the LLM   │ ──────────────────► │  Z3 /    │
   │ (English) │                       │ (translate │                     │  SymPy   │
   └───────────┘                       │   only)    │                     └──────────┘
                                                                      │ SAT / UNSAT / unknown
                                                                      ▼
   ┌───────────┐   counterexample,      ┌────────────┐
   │  verdict  │ ◄──────────────────── │  solver    │  ← the LLM never decides anything
   └───────────┘   scope, honesty       └────────────┘
```

The whole trust story is one sentence: **the LLM translates, the solver decides.**

---

## 1. What it actually does

1. **Translates** the informal claim into a structured, solver-checkable form
   (variables, bounds, constraints, a boolean predicate).
2. **Searches** for a point inside the declared bound where the claim is false —
   using Z3 (SMT) or SymPy (computer algebra), never LLM "reasoning".
3. **Reports** one of three honest outcomes:

   | verdict | meaning |
   |---|---|
   | `counterexample_found` | the claim is false — here is the exact witness |
   | `no_counterexample_in_bound` | nothing in the searched bound breaks it (**not** a proof of truth) |
   | `unknown` | the solver could not decide — with a *classified, scored* reason |

4. **Autopsies** the failure (Stage 5b): when a counterexample exists, Breach
   works out *which step's implicit assumption* it breaks, states that
   assumption, and offers to add it as a constraint and re-check.

---

## 2. Honest unknowns (the differentiator)

"Unknown" is never a shrug. Breach classifies *why* it stopped:

| kind | meaning | what would help |
|---|---|---|
| `timeout` | the solver ran out of time | more time, or tighter bounds |
| `undecidable` | the claim lies outside what solvers can decide | a human argument, or a bounded reformulation |
| `translation_ambiguity` | the statement itself was vague, or the formalisation is uncertain | pin the statement down (draw it) |
| `unsupported_backend` | the claim needs arithmetic the backend cannot express | a different formulation |

Each unknown carries a **confidence score** and a plain-language explanation.

---

## 3. Scope honesty (read this before you quote it)

Breach does **not** solve Millennium Prize problems. Navier–Stokes, Collatz, the
Riemann hypothesis and friends are open questions about unbounded, infinite-
dimensional structures. Z3 and SymPy work over *decidable, bounded or well-scoped*
fragments. If you hand Breach such a claim, the correct behaviour — and the
behaviour it implements — is to say so:

```console
$ breach check --example collatz
❓  UNKNOWN
  classification: undecidable (confidence 85%)
  Out of scope for mechanical verification: this is an open conjecture about
  unbounded iteration... No amount of solver time helps here.
```

What Breach *can* honestly do is automate the tedious, error-prone part of
real research workflows: the edge-case hunt. The same *technique* — cube-and-
conquer splitting with symmetry breaking, run in parallel, with a search
certificate — is the one that cracked the Boolean Pythagorean Triples problem
(2016, ~2^7825 cases on 800 cores over two days) and disproved Keller's
conjecture in 7 dimensions.

Breach runs that architecture at **laptop scale** and always prints the real
numbers next to the honest comparison:

```console
$ breach search --example pythagorean --splits 6 --workers 4
Searched 6 cases across 4 workers in 0.0984s (eliminated 6 by symmetry).
For comparison, the 2016 Pythagorean Triples proof covered ~2^7825 cases on
800 cores over 2 days. This is the same architecture, at laptop scale — not a
replication of that result.
```

**Never claim Breach "solved an open problem".** Claim: *it runs the real
technique, at a demo scale, and it is honest about the difference.*

---

## 4. Install

### Quick start (already installed on this machine)

Double-click one of these in `D:\breach`:

| file | what it does |
|---|---|
| `run_cli.bat` | opens the interactive Breach CLI (`breach chat`) in a terminal |
| `run_web.bat` | starts the web UI and opens http://localhost:8501 |

Or from any terminal:

```powershell
cd D:\breach
D:\breach\.venv\Scripts\breach.exe chat          # interactive CLI
D:\breach\.venv\Scripts\breach.exe web           # web UI on http://localhost:8501
D:\breach\.venv\Scripts\breach.exe check --example euler
```

To use the plain `breach` command (instead of the full path), activate the
environment first:

```powershell
cd D:\breach
.venv\Scripts\Activate.ps1      # PowerShell
# or: .venv\Scripts\activate.bat  (cmd)
breach chat
```

### From scratch

```bash
git clone https://github.com/SoumalyaSaha/Breach.git && cd Breach
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
pip install -e .            # installs the `breach` command
cp .env.example .env        # then paste your keys into .env
```

### LLM providers (first one available wins)

| provider | env var | notes |
|---|---|---|
| Groq | `GROQ_API_KEY_1..4` | primary; keys are rotated with per-key cooldowns |
| Google AI Studio | `GOOGLE_API_KEY` | automatic fallback |
| local Ollama | `OLLAMA_URL` | automatic fallback, no network needed |

The LLM is used **only** to translate and to explain. Everything that decides
anything is Z3 or SymPy, so Breach still works (with a reduced offline
translator) when no key is configured.

> Note on the multi-key rotation: rotating several Groq accounts may conflict
> with Groq's Acceptable Use Policy. The provider chain above means you never
> *need* the rotation to stay alive — Groq alone is the primary, the rest is
> failover.

---

## 5. Usage

```bash
breach check "for every integer n, n^2 >= 0"     # attack a claim
breach check --example euler                     # greatest-hits gallery
breach check --example euler --json              # machine-readable output
breach examples                                  # list the gallery
breach search --example pythagorean --splits 6   # cube-and-conquer + symmetry breaking
breach chat                                      # interactive blackboard session
breach challenge 2 "what if a = 0?"              # contest a specific step
breach export md|html|txt                        # export the session
breach web                                       # launch the web UI
```

### Inside `breach chat`

```
/web                     launch the web interface with this session loaded
/challenge <id> <text>   contest a specific proof step
/export md|html|txt      export the current session
/examples                show the built-in gallery
/clear                   clear the board
/quit                    leave
```

`/web` is a **live handoff**: the CLI writes the current proof state to a
session file, starts Streamlit as a background process, opens your browser, and
**keeps the terminal session alive**. Both views read and write the same state
file, so a step challenged in the browser shows up in the terminal within a
couple of seconds (and vice versa).

### Built-in gallery (`breach examples`)

| key | claim | expected |
|---|---|---|
| `euler` | Euler's sum-of-powers conjecture (k = 5) | counterexample — the 1966 Lander–Parkin witness |
| `pythagorean` | no integer solutions to x² + y² = z² | counterexample — (3, 4, 5) |
| `squares_mod4` | squares are 0 or 1 mod 4 | no counterexample in bound |
| `square_nonneg` | n² ≥ 0 | no counterexample in bound |
| `goldbach` | every even n > 2 is a sum of two primes | no counterexample in bound (4..200) |
| `collatz` | Collatz conjecture | unknown — honestly out of scope |
| `landau` | infinitely many twin primes | unknown — honestly out of scope |

Every gallery entry carries its own formalisation, so the demos resolve in
milliseconds and never depend on the network.

---

## 6. The blackboard, and the proof autopsy

A proof state is not a one-shot answer — it is a board you can argue with:

```python
proof_state = {
  "claim": "...",
  "steps": [
    {"id": 1, "text": "...", "status": "unchallenged"},
    {"id": 2, "text": "...", "status": "challenged",
     "challenge": "what about a = 0?", "response": "...",
     "implicated": True, "missing_assumption": "x >= 0"},
  ],
  "verdict": "counterexample_found",
  "counterexample": {"x": -1.0},
}
```

When you challenge a step, the agent receives the **whole** proof state plus
your objection and must answer *that* objection — concede it (re-running the
solver with the new assumption) or explain why the step still holds.

The **autopsy** (Stage 5b) closes the loop:

```
$ breach check "the square root of x squared equals x for every real number x"
⚠️  COUNTEREXAMPLE FOUND      x = -1.0
Autopsy: Step 3 treats the original universal claim as if it required x ≥ 0,
implicitly assuming the domain is restricted to non-negative numbers.
Add constraint 'x >= 0' and re-check? [y/n]
```

Applying the patch re-runs the solver with `x >= 0` added and reports the
result honestly ("no counterexample found in the searched bound", or "still
breaks — here is the next counterexample").

---

## 7. Architecture

```
src/
  state.py         ProofState / ProofStep / UnknownInfo  (the shared data model)
  memory.py        ProofMemory — lock-guarded, never overwrites
  llm_client.py    provider chain + Groq key rotation (the only network layer)
  engine.py        translation, solver invocation, scored unknowns, tautology guard
  orchestrator.py  worker dispatch (symbolic / constraint / numeric) over shared memory
  cases.py         cube-and-conquer splitting, symmetry detection, search certificate
  argue.py         challenge loop + proof autopsy + patch
  examples.py      the built-in greatest-hits gallery
  symbols.py       symbol shortcuts (function names are protected)
  vision.py        canvas → LaTeX transcription (always confirmed by the user)
  citations.py     related work — returns an empty list rather than inventing one
  export.py        .md / .html / .txt reports
  ui_theme.py      shared rich theme (red/orange accent) + banner
  cli.py           Typer CLI (thin wrapper)
  web.py           Streamlit UI (thin wrapper)
tests/
  test_engine.py   solver-level tests (true claim / false claim / unknown + gallery)
```

![Breach architecture diagram](docs/diagram.png)

**Design rule:** the CLI and the web app are *thin renderers*. All logic lives
in `engine.py`, `orchestrator.py`, `cases.py` and `argue.py`. If logic appears
inside `cli.py` or `web.py`, that is a bug.

---

## 8. miniF2F-curated validation corpus

Breach is validated against an external, citable corpus — not only against
problems we wrote ourselves. This corpus is **curated from miniF2F**, the
standard cross-system academic benchmark for automated/formal mathematical
reasoning (arXiv:2109.00110).

- [`validation/VALIDATION.md`](validation/VALIDATION.md) — what the corpus
  contains, what it deliberately does *not* claim, and the exact commands to
  reproduce it (including the one case that was flaky, how it was root-caused
  and how it was fixed).
- [`validation/validation_corpus.json`](validation/validation_corpus.json) — the
  machine-readable version (5 entries: 4 executable, 1 historical context).

See [`CHANGELOG.md`](CHANGELOG.md) for the translation-validation fix that made
BVC-002 deterministic.

---

## 9. Tests

```bash
python -m pytest -q
```

The suite covers a true claim (no counterexample), a false claim (exact witness
values checked arithmetically), an undecidable claim (scored unknown), every
gallery example against its expected verdict, memory discipline (no
overwrites), state serialisation, symbol shortcuts, and export.

---

## Acknowledgements

Breach was built with the help of AI coding tools — chiefly **OpenCode**
(agentic coding in the terminal) and **Claude** (Anthropic) — used exclusively
as research assistants while designing and implementing this project: exploring
solver encodings, drafting the translation prompt, and writing the code.

Every mathematical claim, solver verdict, search certificate and published
number in this repository was produced by **running the code** — Z3, SymPy and
the validation corpus — not by taking a model's word for it. Where the tools
were unsure, Breach says so instead of guessing.

## License

MIT — see [`LICENSE`](LICENSE).

The mathematics, of course, belongs to the mathematicians.
