# Pi Dev Ops — Cross-Session Handoff

_Last updated: 2026-04-10 | Sprint 7 / Cycle 13 | ZTE Score: 60/60 Zero Touch_

---

## Current State

The system is fully operational at **ZTE Level: Zero Touch (60/60)**. 62 features complete across 7 sprints.

- **MCP server:** 13 tools
- **Skills:** 31 across 7 layers
- **Telegram:** @piceoagent_bot live (dashboard webhook + Railway agentic bot)
- **Pi-SEO:** scanner running across 10 repos on 6h rotation
- **Ship-chain:** /spec /plan /build /test /review /ship pipeline live

**Server:** FastAPI at `127.0.0.1:7777` (start with `cd app && uvicorn server.main:app --host 127.0.0.1 --port 7777`)
**Dashboard:** Next.js at `dashboard/` (Vercel-deployed)
**MCP Server:** `mcp/pi-ceo-server.js` v3.1.0 (restart required to pick up latest code changes)

---

## Architecture (Post-Sprint 8 State)

```
Browser → POST /api/build → FastAPI → run_build()
                                          │
  Phase 1: git clone (3-attempt backoff)  │
  Phase 2: workspace analysis             │
  Phase 3: Claude Code availability check │
  Phase 3.5: sandbox verification         │
  Phase 4: generator                      │
    ├─ TAO_USE_AGENT_SDK=true  → _run_claude_via_sdk()  [SDK, bypassPermissions]
    │                                                     [falls back to subprocess on failure]
    └─ TAO_USE_AGENT_SDK=false → claude -p subprocess   [original path]
  Phase 4.5: evaluator (blocking gate)    │  ← closed-loop retry with critique injection
    └─ subprocess path (both modes)       │  ← evaluator uses subprocess only
  Phase 5: git push (3-attempt backoff)   │
                                          ▼
             lessons.jsonl ← auto-learn from evaluator scores
Browser ← WebSocket /ws/build/{sid} (live stream)
```

**SDK canary state:** Not yet activated. Set `TAO_USE_AGENT_SDK=true` or
`TAO_USE_AGENT_SDK_CANARY_RATE=0.10` in Railway to open Phase A.
See `.harness/agents/sdk-phase2-rollout.md`.

**Key supporting modules:**
- `app/server/brief.py` — PITER classifier + ADW template engine + lesson/skill injection
- `app/server/sessions.py` — full build lifecycle, phase checkpoints, resume
- `app/server/persistence.py` — atomic JSON session persistence to `app/logs/sessions/`
- `app/server/orchestrator.py` — fan-out parallelism via `POST /api/build/parallel`
- `app/server/webhook.py` — GitHub + Linear webhook parsing
- `app/server/cron.py` — cron trigger engine (`GET/POST/DELETE /api/triggers`)
- `app/server/gc.py` — workspace GC (4h TTL, runs every 30 min)
- `app/server/lessons.py` — lessons.jsonl CRUD (`GET/POST /api/lessons`)
- `app/server/scanner.py` — Pi-SEO autonomous multi-project scanner
- `app/server/pipeline.py` — ship-chain pipeline orchestrator
- `app/server/agents/board_meeting.py` — Claude Agent SDK PoC (parallel board-meeting agent)

---

## Sprint 1 — Foundation (2026-04-07) | 35 → 41/60

| Issue | Change |
|-------|--------|
| RA-449 | MCP server rebuilt as v3.0.0 using official `@modelcontextprotocol/sdk` |
| RA-450 | `persistence.py`: atomic JSON saves on every status change; restored on startup |
| RA-451 | `gc.py`: workspace GC loop (30min interval, 4h TTL) |
| RA-452 | `auth.py`: inline rate-limit GC — evicts IPs not seen in 120s every 5 min |
| RA-453 | `lessons.jsonl` seeded with 12 entries; `GET/POST /api/lessons` endpoints |
| RA-458 | `CLAUDE.md` fully documented (replaced stub template) |
| RA-459 | `.claude/settings.local.json` added to `.gitignore` and untracked |

## Sprint 2 — Capability (2026-04-07) | 41 → 50/60

| Issue | Change |
|-------|--------|
| RA-454 | Evaluator tier: second `claude -p` pass, 4-dimension scoring, scores streamed to WS |
| RA-455 | `webhook.py` + `POST /api/webhook`: GitHub + Linear event parsing, auto-brief |
| RA-456 | `brief.py`: PITER intent classifier + 5 ADW templates (feature/bug/chore/spike/hotfix) |
| RA-457 | `src/tao/skills.py`: skills loader/registry with intent-to-skill mapping |
| RA-460 | Linear webhook: issue move to "In Progress" auto-triggers a build session |
| RA-461 | `.harness/leverage-audit.md` baseline score recorded |
| RA-462 | Leverage audit updated to 50/60 post-P2 sprint |
| RA-463 | `.harness/agents/`, `contracts/`, `qa/`, `templates/` all populated (10 new files) |
| RA-464 | `orchestrator.py`: fan-out parallelism, `POST /api/build/parallel` |
| RA-465 | TAO engine wired: BudgetTracker per session, `_select_model()` reads config |
| RA-466 | `scripts/fetch_anthropic_docs.py`: daily docs pull cron at 5:50am AEST |
| RA-467 | Autonomous board meetings: scheduled at 0/6/12/18 AEST, fully autonomous |
| RA-468 | Sandbox enforcement: Phase 3.5 auto-re-clones if workspace GC'd mid-session |

## ZTE Sprint (2026-04-08) | 50 → 60/60

All 12 leverage points raised to 5/5. Changes included in sessions.py/brief.py:
- Lesson context injection per intent into every brief (`_get_lesson_context`)
- `_select_model()` reads `.harness/config.yaml` agents block
- Fan-out workers escalate to opus tier on failure
- Closed-loop evaluator retry: critique → retry prompt → re-generate → re-evaluate
- Clone 3-attempt backoff (2s/4s); generator 2-attempt retry
- Phase checkpoints persisted; `POST /api/sessions/{sid}/resume` skips done phases
- Evaluator is now BLOCKING gate (not fire-and-forget), max 2 retries
- `_parse_evaluator_dimensions()` extracts scores; auto-appends lessons below threshold
- `cron.py` + `.harness/cron-triggers.json` + `GET/POST/DELETE /api/triggers`

## Sprint 3 — Validation (2026-04-08) | 60/60 maintained

| Issue | Change |
|-------|--------|
| RA-469 | MCP `get_zte_score` reads `leverage-audit.md` directly; `feature_list.json` + `sprint_plan.md` created |
| RA-470 | E2E smoke test: 22/22 checks pass; PITER priority bug fixed (chore/spike before feature) |
| RA-471 | `git push` retry added: 3 attempts, 2s/4s backoff, auth error hard-stop |
| RA-472 | This file |

---

## Known Working Configuration

```
TAO_PASSWORD=<set or auto-generated on first run>
TAO_SESSION_SECRET=<auto-generated; set to persist across restarts>
TAO_EVALUATOR_ENABLED=true
TAO_EVALUATOR_THRESHOLD=8
TAO_EVALUATOR_MAX_RETRIES=2
TAO_EVALUATOR_MODEL=sonnet
TAO_GC_MAX_AGE=14400  # 4 hours
```

### Railway deployment — LIVE

**Public URL:** `https://pi-dev-ops-production.up.railway.app`
**Project:** airy-adventure | **Service:** Pi-Dev-Ops | **Region:** US East (Virginia)

---

## Sprint 4 — Complete (2026-04-08)

| Issue | Change |
|-------|--------|
| RA-473 | `scripts/smoke_test.py`: standalone 28-check E2E regression script, UTF-8 safe, CI exit codes |
| RA-474 | `dashboard/app/(main)/builds/page.tsx`: live Pi CEO builds view (phase bar, evaluator scores, fan-out grouping); `/api/pi-ceo/[...path]/route.ts` proxy handles auth |
| RA-475 | Real build validated: 6/7 phases ran (clone→analyze→claude_check→sandbox→generator running); `claude -p` subprocess confirmed working |
| RA-476 | `linear_status` diagnostic tool added to Pi CEO MCP; self-service setup guide built in |

---

## Sprint 5 — Complete (2026-04-08)

| Issue | Change |
|-------|--------|
| RA-477 | `.github/workflows/smoke_test.yml`: GitHub Actions CI — 28-check smoke test runs on push/PR to main; `TAO_EVALUATOR_ENABLED=false` skips real claude in CI |
| RA-478 | Railway deployment live: `Dockerfile` + `railway.toml` + `.dockerignore`; public URL `https://pi-dev-ops-production.up.railway.app`; Vercel `PI_CEO_URL` + `PI_CEO_PASSWORD` set; dashboard redeployed |

---

## Sprint 6 — Evaluator Quality Push (2026-04-08)

| Issue | Change |
|-------|--------|
| RA-479 | `brief.py`: `_QUALITY_GATE` constant injected into every generator brief — explicit 4-dimension self-review rubric mirroring the evaluator (target ≥9/10 per dimension) |
| RA-480 | `sessions.py`: Evaluator prompt now includes original brief for completeness checking + rigorous scoring guide (10=excellent → ≤6=clear deficiency) |
| RA-481 | `config.py`: Default `EVALUATOR_THRESHOLD` raised 7 → 8; Railway env var updated to match |

---

## Security Hardening Sprint (2026-04-09) — RA-489 through RA-508

Major security and feature completion pass across all layers:

**Security (6 items):**
- SHA-256 password hashing replaced with bcrypt + transparent migration on first login
- GitHub token removed from localStorage (XSS vector closed)
- CSP hardened: `unsafe-eval` replaced with `wasm-unsafe-eval`
- Session secret persisted to `app/data/.session-secret` (survives restarts)
- Structured JSON logging (`_JsonFormatter`) across all Python modules
- `print()` replaced with `logging.getLogger()` in cron.py, gc.py, sessions.py

**Bug Fixes (2 items):**
- Phase 4 (CONTEXT) result parser in `dashboard/lib/phases.ts` — was missing `case 4`, silently dropping all context data
- xterm.js CSS import missing in `dashboard/components/Terminal.tsx`

**Feature Wiring (5 items):**
- Vercel preview deployments wired into `/api/analyze` route after Phase 8
- Telegram notifications on analysis completion + failure
- ActionsPanel: download button (Blob) + commit-to-branch button (GitHub API)
- SSE reconnection with exponential backoff (1s→30s, max 6 retries)
- Enhanced `/health` endpoint: uptime, sessions, disk, Claude CLI status

**UX (3 items):**
- Toast notification system with Bloomberg styling (`dashboard/components/Toast.tsx`)
- ErrorBoundary with retry (`dashboard/components/ErrorBoundary.tsx`)
- 404 page (`dashboard/app/not-found.tsx`) and global error page (`dashboard/app/error.tsx`)

**New TAO Skills (3 items):**
- `skills/security-audit/SKILL.md` — OWASP Top 10, CVSS scoring
- `skills/product-manager/SKILL.md` — RICE prioritisation, feature completeness
- `skills/maintenance-manager/SKILL.md` — dependency health, debt calendar

---

## Sprint 6 — Pi-SEO Epic + Ship-Chain (2026-04-10)

| Issue | Change |
|-------|--------|
| RA-531 | app/server/scanner.py: autonomous multi-project scanner orchestrator |
| RA-532 | Triage engine: auto-creates Linear tickets from scanner findings |
| RA-533 | .harness/projects.json: registry of all 10 monitored repos |
| RA-534 | skills/pi-seo-security: OWASP Top 10 + secret detection |
| RA-535 | skills/pi-seo-deployment: Vercel Sandbox browser audit + Core Web Vitals |
| RA-536 | skills/pi-seo-dependencies: npm/pip outdated packages + CVE via OSV API |
| RA-537 | Auto-PR generation for auto-fixable findings |
| RA-538 | dashboard/app/(main)/health: projects health dashboard (10 repos) |
| RA-539 | cron-triggers.json: 6h scan rotation for all 10 projects |
| RA-540 | MCP: scan_project + get_project_health tools (13 total) |
| RA-541 | Vercel Sandbox pre-baked Chromium snapshot |
| RA-542 | Pi-SEO intelligence layer: 3 specialist skills + synthesiser |
| RA-543 | Ship-chain: /spec /plan /build /test /review /ship (6 phases, 5 skills, 7 MCP tools) |

## Sprint 7 — Mobile + Telegram (2026-04-10)

| Issue | Change |
|-------|--------|
| RA-546 | Mobile/tablet responsive layout: bottom tab bar, card history, iOS zoom fix |
| RA-547 | .claude/settings.json: WorktreeCreate/WorktreeRemove hooks for agent isolation |
| RA-548 | dashboard/app/api/telegram/route.ts: @piceoagent_bot wired to Pi-CEO dashboard |
| RA-549 | Railway: claude-code-telegram bot deployed (full Claude Agent SDK via Telegram) |

---

## Sprint 8 — SDK Phase 2 + Ops Hardening (2026-04-11)

| Issue | Change |
|-------|--------|
| RA-571 | `sessions.py`: `_run_claude_via_sdk()` — dual-path SDK/subprocess generator with fallback |
| RA-572 | `sessions.py`: evaluator retry also routes via SDK when `USE_AGENT_SDK=true` |
| RA-574 | `.harness/agents/sdk-phase2-rollout.md`: Phase A→B→C canary plan, pass criteria, rollback table |
| RA-575 | `scripts/smoke_test.py --agent-sdk`: SDK import check + session field check + metrics dir check |
| RA-578 | `config.py`: `USE_AGENT_SDK`, `SDK_CANARY_RATE`, `SDK_METRICS_FILE` env-backed settings |
| RA-580 | Harness refresh: `feature_list.json` → 68 features (Sprint 8/Cycle 16), `handoff.md`, `sprint_plan.md` |
| RA-581 | `DEPLOYMENT.md`: prod URLs, env matrix, deploy commands, activation checklist |
| RA-583 | `scripts/smoke_test.py --target=prod`: prod-safe mode, URL from DEPLOYMENT.md |

---

## What To Do Next

1. **Open canary Phase A** — set `TAO_USE_AGENT_SDK_CANARY_RATE=0.10` in Railway; monitor for 24h
2. Pi-SEO activation — run first full sweep across all 10 repos, review findings volume
3. Self-improvement loop — scheduled lesson-pattern analyser proposes CLAUDE.md updates
4. Multi-model parallel evaluation — Sonnet + Haiku consensus with Opus escalation
5. **DR-510** — enable Vercel Automation Bypass Secret (CEO browser action, 30 sec)
