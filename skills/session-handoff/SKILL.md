---
name: session-handoff
description: Durable session handoff (/session-handoff). Gates the tree green via scripts/handoff-loop.sh, then generates a precise handoff before stopping, switching terminals, opening a PR, handing work to another agent, or resuming later. Writes a durable report + healthcheck log; the "1" of the 1-2 combo with /resume-from-handoff. Captures what was done, decisions locked, what shipped, key files, running state, verification, deferred/open questions, exact pickup point, risk notes, and a quality check.
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

1. Summary of what was done (attempted / completed / partial / not touched)
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
