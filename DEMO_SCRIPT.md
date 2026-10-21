# Breach — demo script (4 minutes)

Everything below is pre-tested. The exact command strings matter: a 30-second
solver hang on camera is the single biggest demo-killer. The gallery examples
resolve in milliseconds and never touch the network.

---

## 0:00–0:25 — Cold open (no slides, no logo)

*Screen: a plausible-but-false claim, typed in plain text.*

> "AI can write a proof that looks right and is actually wrong. Most tools ask
> an AI to confirm a claim — ours does the opposite. Breach's job is to try to
> break your proof, not agree with it."

---

## 0:25–1:10 — Live CLI: `breach check`

```console
$ breach check "for every integer n between 1 and 40, n^2 + n + 41 is prime"
```

> "Here's Breach running from the terminal."

*(Let the banner, spinner and result play out unedited.)*

> "It translates the claim into something a solver can actually check — not
> just reason about in English — and searches for a counterexample."

*(Counterexample appears: `n = 40`, `d = 41`.)*

> "And there it is — 40² + 40 + 41 is 41². The claim breaks, and the witness is
> exact."

**Backup claim (identical behaviour, zero risk):**

```console
$ breach check --example euler
```

> "Euler's sum-of-powers conjecture. It stood for two hundred years, until
> Lander and Parkin found this in 1966. Breach finds the same witness."

---

## 1:10–2:10 — Live CLI: `breach chat` + `/web`

```console
$ breach chat
```

> "Breach also runs as an interactive session."

*(Type a claim, e.g. `for every integer n, n^2 is never negative`.)*

> "Now watch — I can launch the full web interface without losing any of this."

```console
/web
```

> "That's the same session, same proof state, now in a visual workspace. The
> terminal stays live too — they share one file."

---

## 2:10–2:50 — Blackboard challenge (the strongest segment)

In the browser: click **Challenge a step**, pick a step, type
`what if a = 0?` and submit.

> "This is the part I think matters most. Most proof tools give you one answer
> and the conversation ends. Here, you can challenge any step directly."

> "The agent has to respond to that specific objection — not restart, not
> deflect — and the board updates with its answer."

*(If the claim was false, the autopsy line appears: which step's implicit
assumption the counterexample breaks, plus `Add constraint '…' and re-check?`.)*

> "And when it finds a counterexample, it does an autopsy: it tells you which
> step's unstated assumption broke, and offers to add that assumption and
> re-check. No other tool does that part."

---

## 2:50–3:15 — Export

*(Click Export → `md`, then open the file on screen.)*

> "Everything here is yours to keep, not just read once in a terminal. One
> click, a real file — Markdown, HTML or plain text."

---

## 3:15–3:45 — Hard-case search (cube-and-conquer)

```console
$ breach search --example pythagorean --splits 6 --workers 4
```

> "Breach can also split a hard problem into smaller pieces and search them in
> parallel, eliminating equivalent cases along the way. You can see the
> symmetry breaking in the count: six cubes were eliminated before we started."

> "This is the same technique — cube-and-conquer search with symmetry breaking
> — that was used to resolve the Boolean Pythagorean Triples problem in 2016,
> and to disprove Keller's conjecture in seven dimensions. We're running it
> here at a scale that fits a laptop and four minutes, not a supercomputer —
> but it's the real method, not a toy imitation."

> "And for honesty: Breach will tell you when it *can't* resolve something.
> `breach check --example collatz` comes back UNKNOWN — 'undecidable', because
> no amount of solver time helps. It never fakes an answer."

---

## 3:45–4:00 — Close

> "Next, we'd scale the search further and sharpen the symmetry detection.
> For now — this is Breach, trying to break your proof before someone else has
> to."

*(End on the live tool, not a title card.)*

---

## Fallbacks

| if this breaks | do this |
|---|---|
| the live claim hangs | `breach check --example euler` (0.04 s, no network) |
| the browser does not open | the Streamlit URL is printed in the terminal; paste it |
| the network is down | the gallery examples still work — every one has a baked formalisation |
| you are short on time | cut from the close first, never from the blackboard challenge |

## Pre-flight checklist

- [ ] `pip install -e .` done, `.env` has a working key
- [ ] `breach check --example euler` returns the counterexample
- [ ] `breach check --example collatz` returns UNKNOWN
- [ ] `breach search --example pythagorean` prints the scale readout
- [ ] `breach chat` → `/web` opens the browser with the session loaded
- [ ] the terminal font is large enough for the counterexample block
