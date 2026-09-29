---
name: waterline
description: Dictate a goal and ramble at it. Grounds in the project's North Star, structures the intent, researches, drafts a build-ready brief, then has Codex challenge it until it holds.
argument-hint: "<goal>"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, Write
---

# waterline — ramble in, build-ready brief out

He talks; you build the brief. He will dictate in long, unedited prose with typos and
tangents, sometimes across several messages. That is the expected input, not a problem to
correct. You never make him re-explain the project, you ask at most one question the whole
run, and you never accept your own output — a fresh Codex process challenges the brief
until nothing blocking survives, or you hand back an honest `UNCONVERGED`.

Four phases. Do not announce them.

## 1. Ground — zero questions

```bash
scripts/ground.sh <project-root> "<goal>"
```

Resolves the pack, reads the waterline gate live from `CONSTITUTION.md` (zero cache), and
runs the recall lookup. **Exit 2 means the gate could not be read — stop there.** A gate
quoted from memory is not a gate, and this is a control with an exit code rather than a
rule you have to remember. Carry the `recall{…, go_external}` result into phase 3. No pack
is not fatal: run anyway and name the assumed project in the brief header.

Never ask him anything here. Everything in this phase is a lookup.

## 2. Reflect — the ramble loop

Hold five slots. Update them silently on **every** message until the brief is emitted:

```
want · why · done-looks-like · NOT in scope · what already exists
```

Each turn print **only the slots that changed**, ≤5 lines, ending with the flat handle
`keep going, or say go.` — a statement, not a question.

**Advance when either:** he says a go-token, **or** a message adds zero new slot content.
Repetition without new state means he has finished; that is the signal, and it costs him
nothing. Never ask "are you done".

**Hard floor:** never advance off the first message alone while `done-looks-like` or
`NOT in scope` is empty. A ramble that never says what finished looks like is not yet a
brief — and that is the one place the single permitted question may be spent.

**The bar lands here too**, in the same reflect-back. Propose **one** bar and list two
alternates at one line each; proceed on silence. A bar must be:

- **named** — a specific thing, not "good" or "production-ready"
- **fetchable** — you can go and get it, or observe it, right now
- **comparable** — you can hold the result against it and say which won

One stop, not two. A second blocking question is how this command stops being used.

## 3. Research

`recall.go_external` gates it. On a hit, use what came back. On a miss, `source-ingest` —
reuse before rescrape, 385+ sources already exist. Tier 1–2 only for anything load-bearing.
Nothing installed, nothing vendored: patterns only.

## 4. Draft, challenge, emit

Draft the brief:

```
goal (verbatim) · why now · done-looks-like · NOT in scope · what already exists ·
the bar · approach · risks · waterline points · next command
```

**Waterline points** names every step in the approach that falls below the line — publish
to a client's audience, production deploy, spend, irreversible without tested rollback —
so the handback is visible before the work starts, not discovered during it.

Ban-list, checked before every challenge round: no placeholder, no `TBD`, no unsourced
number, no "should" where a fact belongs.

Then the loop — mechanics in `references/codex-challenge.md`, and the command line lives
only in `scripts/challenge.sh`. Four rules that must never page out:

1. **Read-only sandbox, never the bypass flag.** A run with
   `--dangerously-bypass-approvals-and-sandbox` is not evidence and cannot clear anything.
2. **One blocking gate:** a fresh run over the current brief returning zero *anchored*
   P0/P1. Advisory findings never block. `anchor.py` decides what anchored, not you.
3. **Silence, timeout, or crash is not a pass.**
4. **Never auto-reconcile.** When you disagree with a finding, stop the loop and print both
   positions verbatim in a `CODEX SAYS` block. He adjudicates, not you.

Never run two challenges at once — the quota is the shared ChatGPT plan window.

**Emit one file.** The round ledger is its last section, not a second artifact. The last
line is the exact next command; `/spm <path>` is usually one of them — let `spm` apply its
own fast-lane-versus-full-spec judgment rather than hard-wiring the 17-seat bench into
every small ask.

`UNCONVERGED` is a legitimate output. Shipping it honestly beats a brief that claims a
clearance no run granted.

## What breaks this

- **A bar that isn't fetchable.** The challenger has nothing to compare against, so it
  invents the comparison and every round after that is theatre.
- **Copying decaying facts into a pack.** Ticket IDs, epic numbers, "current course". The
  Synthex north-star §7 carried its own instruction to re-sync and went 46 days stale
  anyway. Packs hold doctrine and pointers; everything else is fetched at run time.
- **Asking a second question.** He stops using the command, and an unused command is worth
  nothing regardless of how correct it is.
- **Spending a round to manufacture disagreement.** A clean round is allowed to be clean.
- **Treating a clean round 1 as proof.** Read `unchallenged[]` before believing it — the
  observed opening move is a lazy `PASS` with empty arrays.
- **Falling back to a weaker challenger silently.** If it ran on kimi-k3, the brief says
  `DEGRADED` on its face.
- **Rewriting the brief between the run and the report.** The report is bound to the exact
  bytes challenged; edit them and the clearance is void.

## Related

`gauntlet-loop` (the bar, and looping until you win) · `adversarial-review` (the
reviewer-context contract) · `nexus-recall` (phase 1 lookup) · `source-ingest` (phase 3) ·
`spm` (what usually comes next) · `goal-circuit-breaker` (when the loop will not converge).
