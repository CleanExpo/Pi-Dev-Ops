---
name: session-handoff
description: Gate the tree green, then generate a precise session handoff before stopping, switching terminals, opening a PR, handing work to another agent, or resuming later. Runs the definition-of-done gates via scripts/handoff-loop.sh, writes a durable report + healthcheck log, then captures what was done, decisions locked, files changed, running state, verification, deferred questions, and exact pickup point.
argument-hint: "[optional: ticket, branch, PR, feature, repo area, or handoff scope]"
allowed-tools: Read, Grep, Glob, LS, Bash, Write
---

# /session-handoff — Durable Session Handoff

The **"1" of the handoff combo**: gate the tree green, then write a durable handoff that
`/resume-from-handoff` (the "2") verifies against and continues from. Run before stopping,
switching terminals, opening a PR, or handing to another agent.

**Boundary.** This command runs LOCAL verification gates and writes the handoff report +
log. It must NOT commit, push, deploy, run migrations, modify tickets, rotate secrets, or
touch production — surface those for the user to do after the handoff.

## Phase 0 — Gate the tree green (run FIRST, every time)

Before writing anything, run the definition-of-done gates:

```bash
scripts/handoff-loop.sh            # --quick for a fast interim handoff; --full to install deps first
```

It cleans cache/build bloat, then runs deps → generated-files-current → type → lint →
tests → production build → audits, writing a timestamped healthcheck log to
`.handoff-logs/handoff-<ts>.log` and printing that path on its last line. A gate whose
toolchain is absent is SKIPPED with a reason, not failed.

- **Exit 0 (READY)** → proceed to write the handoff; cite the log path + pass/skip counts in
  §5 Running state and §6 Verification.
- **Non-zero (BLOCKED)** → do NOT declare the repo ready. Name the failing gate(s) from the
  log, stop forward progress, and either fix the gate and re-run, or write a **BLOCKED**
  handoff whose §8 first command is the fix + re-run. Never claim green without exit 0.

If `scripts/handoff-loop.sh` is absent (another repo), run that repo's detected equivalents
(type-check, lint, test, build, audit) and record the real results the same way.

## Input scope

User supplied handoff scope:

```text
$ARGUMENTS
```

If `$ARGUMENTS` is empty, infer the scope from:

- Current branch
- Git status
- Recent commits
- Current diff
- Recently changed files
- Current conversation context
- Repo guidance in CLAUDE.md
- Agent boundaries in AGENTS.md
- Relevant `.harness/`, `skills/`, `scripts/`, `tests/`, `app/`, `dashboard/`, or `mcp/` state

## Read-only inspection checklist

Inspect what is available without modifying anything:

```bash
git branch --show-current
git status --short
git log --oneline -n 8
git diff --stat
git diff --name-only
```

If safe and useful, also inspect:

```bash
git diff
```

Only run tests if the user specifically asks for verification execution. Otherwise, report the verification commands to run.

## Required output

**Write the handoff to `docs/session-handoffs/handoff-<YYYYMMDD-HHMMSS>.md`** (create the
directory if absent) AND print it to the user — durable on disk is what lets
`/resume-from-handoff` find it. Follow the 10-section structure in the shared template
[`.session-handoff/report-template.md`](../../../.session-handoff/report-template.md):

1. **Summary** — attempted / completed / partial / not touched
2. **Where it started** — request, branch, files, problem, constraints (`Unknown from available context` if unclear)
3. **Decisions locked + what shipped** — separate the two; if nothing committed/pushed, say `Nothing shipped yet. Current work is local/session-only.`
4. **Key files** — table; Status ∈ Created / Modified / Deleted / Read-only inspected / Needs review / Deferred / Unknown
5. **Running state** — branch, tree, server/process (never claim running unless verified), open PR, blockers, safe-to-stop
6. **Verification** — exact commands (backend / dashboard / smoke); cite the Phase 0 log path
7. **Deferred + open questions** — two lists, each item with Owner / Blocking / Why
8. **Pick up here** — `Start here` steps · `Do not redo` · explicit `First command to run`
9. **Risk notes** — unverified assumptions, failed commands, stale context, secrets/env gaps
10. **Handoff quality check** — no faked verification, no hidden "still running", completed-vs-deferred clear

If Phase 0 was BLOCKED, mark the handoff **BLOCKED** and make §8's first command the gate fix.

End with: `Handoff complete. Next safe action: <one sentence>.`

## The 1-2 combo

`/session-handoff` (this, the "1") and `/resume-from-handoff` (the "2") are a pair:
gate-and-write here → verify-and-continue there. The report at
`docs/session-handoffs/handoff-<ts>.md` and the log at `.handoff-logs/handoff-<ts>.log` are
the shared contract between them. `/resume-from-handoff` reads the latest of each and
re-runs `scripts/handoff-loop.sh` as its own verification gate before resuming — so the tree
is proven green on the way out AND on the way back in.
