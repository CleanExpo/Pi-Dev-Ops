---
name: session-handoff
description: Durable session handoff (/session-handoff). Gates the tree green via scripts/handoff-loop.sh, classifies the session SHIPPED / READY-TO-SHIP / WIP-BLOCKED against a Definition-of-Done, then generates a precise handoff before stopping, switching terminals, opening a PR, handing work to another agent, or resuming later. Refuses to present unfinished work as a clean stop; for ready work hands off the exact merge-gate-guarded ship command. Writes a durable report + healthcheck log; the "1" of the 1-2 combo with /resume-from-handoff. Captures what was done, decisions locked, what shipped, key files, running state, verification, deferred/open questions, exact pickup point, risk notes, and a quality check.
owner_role: Tier-Architect (end-of-session handoff; gate-then-report)
status: active
automation: manual
---

# session-handoff — Durable Session Handoff

The **"1" of the handoff combo** with `/resume-from-handoff`: gate the tree green, then write
a durable handoff the resume side verifies against. It runs LOCAL verification gates and
writes the report + log — but never commits, pushes, deploys, migrates, modifies tickets,
rotates secrets, or touches production. Any such mutation follows a separate, explicit user
request after the handoff.

Companion to `judge`: `/judge` decides *whether to build*; `/session-handoff` records
*what happened and where the next agent picks up*. Distinct from `tao-judge` (machine
loop-termination scorer).

## Phase 0 — Gate the tree green (run first, every time)

```bash
scripts/handoff-loop.sh          # --quick for interim; --full to install deps first
```

Runs the definition-of-done gates (clean → deps → generated-files → type → lint → tests →
build → audits), logging to `.handoff-logs/handoff-<ts>.log`. **Exit 0** → write the handoff.
**Non-zero** → write a **BLOCKED** handoff naming the failing gate; do not claim ready.

## Phase 0.5 — Definition of Done & ship classification (before writing the report)

Phase 0 proves the tree *green*; Phase 0.5 proves the session *finished* — a green tree can hide
half-done, uncommitted, or never-shipped work. Never let an unfinished session pass as a clean
stop. Classify into exactly one state and record it in §1:

- **SHIPPED** — committed, pushed, PR open/merged on a green tip. Record the PR URL in §3.
- **READY-TO-SHIP** — complete + green but no PR yet. Do not silently stop: run the `merge-gate`
  pre-open checklist, then make §8's `First command` the exact `gh pr create`. session-handoff
  does **not** open it — opening a PR here ≈ merging it (see `merge-gate`).
- **WIP / BLOCKED** — a task unfinished, a gate red, or a surface not demonstrable. Mark the
  handoff **INCOMPLETE**; §7 lists what remains to finish + test, §8 is the finish-then-ship path.

Definition-of-Done (answer each from a this-session tool result; any "no" forbids SHIPPED):

1. Every task/goal the session set out to do is done, or explicitly deferred in §7 with an owner.
2. Tests actually ran green (Phase 0 exit 0) — not just types compiling; cite the log path.
3. `git status` clean and `git stash list` empty — nothing uncommitted belongs in the change.
4. Work is PR'd (SHIPPED) or carries the exact ready-to-open command (READY-TO-SHIP).
5. Any user-visible change has a demonstrable outcome (RA-1109), not just HTTP 200 / green CI.

For READY-TO-SHIP, the handed-off `gh pr create` is only safe when all `merge-gate` Iron-Law
conditions already hold (Whole · Green-on-pushed-tip · Dark-by-default · Atomic · Standards-clean
· Authority reconciled). Any false ⇒ the session is WIP, not READY-TO-SHIP. Invoke `merge-gate`
for the full gate; do not paraphrase it.

## Input scope

Handoff scope is supplied as `$ARGUMENTS` (a ticket, branch, PR, feature, or repo area).
If empty, infer scope from the current branch, git status, recent commits, current diff,
recently changed files, conversation context, and the CLAUDE.md / AGENTS.md guidance.

## Inspection

```bash
git branch --show-current
git status --short
git log --oneline -n 8
git diff --stat
git diff --name-only
```

## Required output — Session Handoff

**Write it to `docs/session-handoffs/handoff-<ts>.md`** (so `/resume-from-handoff` can find
it) AND print it. Use this structure (see `.session-handoff/report-template.md`); cite the
Phase 0 log path in §5/§6:

1. Summary of what was done (attempted / completed / partial / not touched) + the Phase 0.5 state (SHIPPED / READY-TO-SHIP / WIP-BLOCKED) and one-line Definition-of-Done result
2. Where it started (request, branch, files, problem, constraints; `Unknown from available context` if unclear)
3. Decisions locked + what shipped (separate decisions from implementation; if nothing committed/pushed, say `Nothing shipped yet. Current work is local/session-only.`)
4. Key files (table; Status ∈ Created / Modified / Deleted / Read-only inspected / Needs review / Deferred / Unknown)
5. Running state (never claim a process is running unless verified)
6. Verification — exact commands (backend / dashboard / smoke / skill check)
7. Deferred + open questions (two separate lists, each with Owner / Blocking / Why)
8. Pick up here (`Start here` steps, `Do not redo`, and an explicit `First command to run`)
9. Risk notes (unverified assumptions, failed commands, stale context, secrets/env gaps)
10. Handoff quality check

End with: `Handoff complete. Next safe action: <one sentence>.`

## Quality rules

- Do not claim tests passed unless they were actually run.
- Do not claim anything shipped unless commit/push/merge evidence exists.
- Do not claim a process is running unless verified.
- Clearly separate completed work from deferred work.
- Always provide the first command the next agent should run.

## The 1-2 combo

`/session-handoff` (this) gates + writes; `/resume-from-handoff` reads the latest
`docs/session-handoffs/` report and re-runs `scripts/handoff-loop.sh` before resuming — the
tree is proven green on the way out AND back in.

## Companion: merge-gate (the ship boundary)

Phase 0.5 decides *whether* a session is ready to ship; `merge-gate` owns *how* it ships safely.
session-handoff never opens a PR itself — for READY-TO-SHIP it hands off the exact `gh pr create`
in §8, gated by `merge-gate`'s Iron Law (opening a PR in this estate ≈ authorising its merge).
Division of labour: `session-handoff` = the definition-of-done gate run + completion
classification; `merge-gate` = the git-merge boundary and auto-merge threat; `ship-chain` /
`ship-it` / `ship-release` = the idea→ship lifecycle. Invoke `merge-gate` before any handed-off
ship command.

## Fork-slice mode (Pocock /handoff, 2026-07)

Lightweight alternative to the full Definition-of-Done gate for **mid-task context forks**:
spinning an out-of-scope task (bug, refactor, prototype spike) into a fresh agent while the
current session keeps working. No Phase 0 gate, no classification, no durable report — instead
of `/compact` (loses fork ability) or `/clear` (loses everything), the fresh agent boots from
a slice:

- Write a **context-slice markdown** to a temp path (e.g. `$TMPDIR/handoff-<slug>.md`), never
  the workspace — disposable by design. Contents: task state, decisions made, next action, and
  a **suggested-skills** list the fresh session should invoke.
- State the fork's purpose explicitly — a slice can't be written without knowing its consumer.
- Pointers, not duplication: reference existing docs/issues rather than restating them. Redact
  secrets/PII (the file lands in a temp dir).
- Boomerang: a spike session can write a slice back to the parent capturing non-obvious learnings.

**Which mode:** mid-task fork / parallel spike / prototype-and-return → fork-slice. Stopping,
switching terminals, opening a PR, or handing work to another agent → the full Phase 0 + DoD
gate above. Fork-slice never replaces the terminal gate.

Provenance: [[pocock-handoff-skill-2026-07-14-ingest]]
