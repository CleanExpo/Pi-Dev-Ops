# Task Brief

[HIGH] [Pi-CEO] Session resilience — Railway redeploys kill every in-flight session (architectural)

Description:
## Observed today (2026-04-18)

Every PR merge triggers a Railway auto-deploy. Each deploy sends SIGTERM/SIGKILL to the existing container. Every `_sessions` entry is destroyed because `_sessions` is an in-memory dict. All in-flight autonomous work is lost mid-flight.

Today's pattern: 7 PRs merged in succession = 7 Railway redeploys = every session started between merges dies. Orphan-recovery (RA-1373) brings the tickets back to Todo, but the session's actual work (minutes of Claude generator time, half-written diffs) is thrown away.

This is the operational ceiling on Pi-CEO's autonomy throughput. More merges = less work delivered.

## Fix options (pick one + file sub-tickets)

### Option A — Execute sessions OUTSIDE the web process (recommended)

Spawn each session as a separate Railway job / worker, or as a Cowork sandbox. Web process becomes a dispatcher; killing it doesn't kill workers. Mandatory for real autonomy.

Pros: True durability. Restarts don't affect in-flight work. Natural scaling.
Cons: New infra. Each worker needs env vars, git, claude CLI. Requires state/log handoff back to the web process or direct Supabase writes.

### Option B — Persist + resume sessions in Supabase

Store each session's `_resume_prompt`, current phase, log buffer, and modified-files list in Supabase after every phase transition. On startup, scan for `status=building` sessions in Supabase, and reconstruct `_sessions` entries pointing to them with a `_resumed_from_supabase=True` flag. Skip phases already completed.

Pros: Single service, no new infra. Reuses existing Supabase.
Cons: Doesn't actually resume the Claude SDK stream — the session has to restart plan+generate from scratch. Better than nothing, but wasteful.

### Option C — Deploy-window guardrails (interim)

Before a Railway deploy, poller checks `_sessions` for anything in `building` status. If found, deploy waits up to N minutes. Implement as a Railway pre-deploy webhook or a GitHub Actions gate.

Pros: Minimal code change; protects the critical in-flight window.
Cons: Deploy latency grows with session count. Not a real fix — a ceiling.

## Recommendation

Ship Option C this week (blocks wasted work today). Design Option A for next sprint (the real fix). Option B isn't worth the complexity.

## Acceptance (Option C interim)

* Before a Railway redeploy, the pre-deploy gate checks `/api/sessions` for `building` state; if count > 0 and max-age < 15 min, delay up to 15 min.
* GitHub Actions `deploy` workflow fails loudly if max-delay exceeded (operator chooses to kill or wait).
* Integration test: fire a session, start a deploy mid-session, verify deploy waits or fails cleanly — no orphans.

## Acceptance (Option A, follow-up ticket)

* Sessions run in a separate process (Railway service, Cowork sandbox, or Fly Machine).
* Web process remains up through session execution.
* Session log stream continues after a web-process restart.

## Related

* [RA-1371](https://linear.app/unite-group/issue/RA-1371/pi-ceo-orphan-transition-recovery-sessions-killed-by-railway-restart) (absorbed by [RA-1369](https://linear.app/unite-group/issue/RA-1369/ra-1297-pi-ceo-code-linear-contract-compliance-status-filter)) added orphan-transition recovery — mitigates the SYMPTOM but not the cause.
* RA-1373 (merged PR #92) adds orphan recovery to the poller — same mitigation.
* The real root cause is architectural: sessions shouldn't share a process with the web server.

Linear ticket: RA-1373 — https://linear.app/unite-group/issue/RA-1373/pi-ceo-session-resilience-railway-redeploys-kill-every-in-flight
Triggered automatically by Pi-CEO autonomous poller.


## Session: 50b375061865
