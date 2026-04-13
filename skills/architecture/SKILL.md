---
name: architecture
description: Architectural conventions and anti-patterns specific to Pi-Dev-Ops — companion model, sandbox isolation, ZTE leverage, CLAUDE.md hygiene, parallel dispatch, topology-first autonomy.
---

# Architecture Best Practices

Apply when making structural decisions about Pi Dev Ops — session handling, workspace isolation, pipeline design, documentation strategy, agent orchestration, or autonomy infrastructure.

## Core Model

Pi Dev Ops is a **split-screen companion**: Left = Claude Desktop CLI writing code; Right = Pi Dev Ops orchestrating, tracking, and pushing to Linear. It is NOT a standalone IDE. Every architectural decision must serve this companion model.

## CLAUDE.md Hygiene

**CLAUDE.md is the highest-leverage documentation fix in the codebase.** It is loaded into every future Claude session. An accurate, detailed CLAUDE.md (file map, conventions, smoke tests, env vars) eliminates all ramp-up time. An outdated one silently misdirects every AI session.

**DO** update CLAUDE.md immediately whenever:
- A new file, directory, or service is added
- A key pattern or convention changes
- A new environment variable is required
- The SDK/subprocess strategy changes

**DON'T** let CLAUDE.md drift. A stale file map is worse than no map — it sends the agent to the wrong file confidently.

## Sandbox Isolation

**Sandbox = workspace directory.** Each session gets an isolated clone at `app/workspaces/{session_id}/`.

**DO** verify the workspace directory exists before Phase 4 of the pipeline. Refuse to run `claude -p` or any SDK call outside it.

**DON'T** share state between workspace directories. Cross-session file access is a bug, not a feature.

## Persistence

**DO** persist session status to disk atomically after every state change — `_sessions` is an in-memory dict and any server restart loses all running sessions.

**DO** use write-to-.tmp-then-`os.replace()` for all JSON file writes:

```python
import os, json, pathlib

def atomic_write(path: pathlib.Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)  # atomic on POSIX and NTFS
```

`os.replace()` is atomic — a crash mid-write leaves the old file intact, not a corrupt half-written file.

## Parallel Agent Dispatch

**Parallel agent dispatch beats sequential by ~8x for independent tasks.** Dispatch multiple Agent tool calls in a single message rather than waiting for each to return.

**Constraint:** agents must not share target files — partition by file ownership before dispatching. If two agents write to the same file, the second write wins silently.

**DON'T** run independent agents sequentially. Sequential dispatch is the single biggest throughput killer in multi-agent orchestration.

## Recon Before Planning

**Always run a reconnaissance swarm against the actual `.harness/` state BEFORE drafting new project plans.**

Writing charters and plans without first reading the real system state produces orphan work. The 2026-04-11 Pi-SEO planning session lost ~2 hours because a parallel `/Pi-CEO/Pi-SEO/` folder duplicated existing `.harness/` content — discovered only after the plan was written.

Pattern:
1. Dispatch recon agents to read `.harness/` state
2. Identify what already exists vs what is missing
3. Then draft the plan against reality, not assumptions

## Autonomy is Topology, Not Code

**"Autonomous" is a property of topology, not of how clever the code is.**

The first overnight autonomous attempt failed because the rails depended on Cowork being open on Phill's Mac. Scheduled-tasks MCP runs in ephemeral Cowork sandboxes — when the Mac sleeps or Cowork exits, every cron entry goes silent.

**The always-on path must include every component that needs to run while the human sleeps:**

| Component | Always-on? | Notes |
|-----------|-----------|-------|
| Railway (backend) | Yes | 24/7, use for all server-side autonomy |
| Vercel (frontend) | Yes | Static/edge only |
| GitHub Actions | Yes | Use as test-truth source |
| Scheduled-tasks MCP | No | Requires Mac + Cowork open |
| Local `claude -p` | No | Requires Mac awake + CLI in PATH |

**DO** move autonomous work to Railway. Use GitHub Actions for CI truth. Webhook Telegram inbound rather than polling from a Mac process.

**DON'T** build "autonomy" that blocks on the human's laptop being awake.

## Scheduled Task Design

**Shrink every scheduled task prompt to a single shell command calling a standalone Python helper.** This minimises tool-approval surface to Bash alone, approvable with one click.

**DON'T** let a scheduled task prompt ask Claude to read files, compose text, and push messages as separate steps — each step is another potential approval prompt.

Scheduled-tasks MCP runs each task in a fresh Cowork sandbox at `/sessions/<random-id>/mnt/<folder>`. The session ID changes every run.

**DO** discover the repo dynamically at the top of every task prompt:
```bash
REPO=$(find /sessions -type d -name Pi-Dev-Ops 2>/dev/null | head -1)
cd "$REPO"
```

**DON'T** hardcode local Mac paths (`/Users/phill-mac/...`) in task prompts — they fail on every execution.

## Health Endpoint Truth

**`/health` must report the state of the WORK the service is supposed to do, not just whether the process is breathing.**

Every long-running background loop needs two things in `/health`:
1. A boolean: "this loop is armed and will actually do work on the next tick"
2. A timestamp/counter: "last successful tick was at X"

Without both, you get silent success theatre — `/health` returns 200 while the autonomy poller skips every cycle because `LINEAR_API_KEY` is missing from Railway env vars.

Surface at minimum: `autonomy.armed`, `autonomy.linear_key_ok`, `autonomy.last_poll_at`.

## Poller Bootstrap Pattern

**Use a do-while pattern with a short startup delay — not sleep-first.**

```python
# BAD — first poll delayed by full interval after Railway restart
while True:
    await asyncio.sleep(300)
    await poll()

# GOOD — polls immediately on boot, then every interval
startup_delay = int(os.getenv("TAO_AUTONOMY_STARTUP_DELAY", "10"))
await asyncio.sleep(startup_delay)
while True:
    await poll()
    await asyncio.sleep(300)
```

Sleep-first loops add the full interval delay after every Railway restart. Combined with a silent skip when `LINEAR_API_KEY` is missing, this looks like the system is dead for 5+ minutes on every cold start.

## Full-Clearance Sprint Pattern

**Full-clearance sprints outperform gated execution 10x.** All Priority 1+2 items complete faster in a single no-authority-gates sprint than issue-by-issue with approval loops.

**ZTE leverage points with highest ROI** (from Sprint 5→6 data):
- CLAUDE.md population: +4 pts
- Evaluator tier: +2 pts
- PITER + ADW: +4 pts
- Webhook triggers: +2 pts

Prioritise these when deciding what to build next.

## File Organisation

- Backend: `app/server/` — FastAPI, sessions, auth, webhooks, autonomy
- TAO engine: `src/tao/` — skills, tiers, budget (stub scaffolding — intelligence is in SDK/subprocess)
- Skills: `skills/` — 28+ SKILL.md files, one directory per skill
- Harness state: `.harness/` — YAML/JSON/Markdown, source of truth for system state
- MCP server: `mcp/pi-ceo-server.js` — 21 tools for harness reads + Linear
- Frontend: `dashboard/` — Next.js 16, React 19, Tailwind

**DON'T** duplicate harness state into a parallel folder outside `.harness/`. All state reads must go through `.harness/` — not a local copy, not a sibling directory.
