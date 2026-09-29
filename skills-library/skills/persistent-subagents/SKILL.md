---
name: persistent-subagents
description: Use when orchestrating multi-round agent work — a second task in a domain an agent already served, any iterate-review loop (UI rounds, fix cycles), or before spawning a fresh sub-agent for follow-up work. Encodes the warm-specialist pattern - resume via SendMessage instead of re-spawning, tiered context economy, naming, retirement.
---

# persistent-subagents — keep one warm specialist per domain, feed it by resume

Sub-agents are resumable (SendMessage to their name/agentId re-hydrates the full transcript)
and can nest 5 deep. So the unit of work is the durable specialist, not the one-shot spawn.
Verified live on this estate 15/07/2026 (CLI 2.1.209, `cleanupPeriodDays: 365`). Knowledge
page: vault `Wiki/persistent-subagents.md`.

## The three tiers

- **T0 — main thread conserves.** Coordinate, review, relay. Never absorb a specialist's
  tool noise into the main window.
- **T1 — persistent specialist maximizes.** ONE warm, named agent per domain per session.
  Deep gather at spawn is an investment: every resume reuses it. Keep its window
  high-signal by pushing noisy collection down to T2 — a compacted T1 resumes as a
  summary-of-a-summary and quietly loses fidelity.
- **T2 — throwaways absorb noise.** The specialist (or you) spawns one-shot children for
  grep sweeps, web fan-outs, bulk reads. They over-collect freely and return only the
  distilled verdict. "Fill the disposable window" applies here ONLY.
- **Completion criterion:** every noisy sub-task in the plan is assigned to a T2 child, not
  to the T1 window or the main thread.

## Resume, fork, or fresh — decide before every spawn

1. Same domain, iterating → **resume**: `SendMessage({to: "<name-or-agentId>"})` with a
   self-contained message (repo state, constraint, acceptance criterion — written so a cold
   replacement could run it). Running agents receive it next tool round; completed agents
   re-hydrate and re-report once.
2. One-shot needing parent context → **fork** (default Agent spawn; shares prompt cache, no
   identity).
3. Domain change → **fresh** agent, full stop. A cross-domain resume carries stale context
   that actively hurts.
- **Completion criterion:** the choice is stated in one line before the spawn/send.

## Naming — frozen at spawn, must survive resume #8

`description` = `<Agent Type> - <durable mission>` (the domain, never the first task);
`name` = kebab-case mirror, e.g. `frontend-founder-deck`, `db-supabase-nexus`. Task
specifics live only in prompt/resume messages. Test: still true on resume #8?
- **Completion criterion:** name passes the resume-#8 test.

## Retirement and recovery

- Window grows monotonically per resume (each resume replays the transcript). At roughly
  **300k tokens**, finish the thread: write the handoff (decisions, file map, open items)
  to disk/ticket, boot a named successor from it.
- Dead handle ("no transcript to resume"): the handle is session-scoped and may not survive
  main-thread compaction or overnight gaps. The transcript survives at
  `~/.claude/projects/<project>/<session>/agent-<id>.jsonl` (365 days here) — point a fresh
  agent at it to **grep for specific prior decisions**, never ingest whole.
- Durable truth lives in commits, reports, and tickets — the agent's memory must survive
  the agent by design, not luck.
- **Completion criterion:** every T1 retirement leaves a written handoff artifact.
