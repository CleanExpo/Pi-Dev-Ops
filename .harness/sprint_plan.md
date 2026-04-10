# Pi Dev Ops — Sprint Plan

_Sprint 8 in progress | 2026-04-11 | ZTE Score: 60/60 Zero Touch_

## Status

Sprints 1–7 complete. Sprint 8 active. 69 features shipped.

---

## Sprint 8 — Done (2026-04-11)

| Issue | Change |
|-------|--------|
| RA-551 | `agents/board_meeting.py`: Claude Agent SDK Phase 1 gap audit + `_run_prompt_via_sdk()` added |
| RA-556 | `_run_prompt_via_sdk()` migration in board_meeting.py; `TAO_USE_AGENT_SDK=1` to enable |
| RA-557 | dotenv `override=True` fix; `LINEAR_API_KEY` added to `.env`; `config.py` updated |
| RA-579 | `cron.py`: startup catch-up for overdue triggers; 12h watchdog fires Urgent Linear ticket |
| RA-581 | `DEPLOYMENT.md`: production URLs, env matrix, rollback procedures (single source of truth) |
| RA-582 | `scripts/verify_deploy.py`: commit parity audit — git HEAD vs Vercel + Railway SHAs |
| RA-584 | `app/server/autonomy.py`: Linear todo poller, `/api/autonomy/status` endpoint |
| (CI fix) | `app/server/main.py`: health endpoint no longer gates on `_claude_ok`; CI 28/28 pass |

## Sprint 8 — Open

| Issue | Priority | Title |
|-------|----------|-------|
| RA-583 | High | Post-deploy verification harness: `smoke_test.py --target=prod` in CI |
| RA-577 | High | Update CLAUDE.md + `.harness/config.yaml` for SDK architecture |
| RA-580 | High | Harness doc regeneration + 48h staleness watchdog |
| RA-571 | Medium | Migrate `sessions.py` generator call to `claude_agent_sdk` |
| RA-572 | Medium | Migrate `sessions.py` evaluator call to `claude_agent_sdk` |
| RA-573 | Medium | Wire SDK metrics collection (tokens, latency, success rate) |
| RA-574 | Medium | Canary rollout + validation plan for sessions.py SDK migration |
| RA-575 | Medium | Smoke-test the SDK path via `scripts/smoke_test.py` |
| RA-576 | Medium | Remove `claude -p` subprocess fallback paths (post-canary) |

---

## Sprint 7 — Complete (2026-04-10)

| Issue | Change |
|-------|--------|
| RA-546 | Mobile/tablet responsive layout: bottom tab bar, card history, iOS zoom fix |
| RA-547 | .claude/settings.json: WorktreeCreate/WorktreeRemove hooks for worktree isolation |
| RA-548 | dashboard/app/api/telegram/route.ts: @piceoagent_bot commands + Claude chat |
| RA-549 | Railway: claude-code-telegram agentic bot (full Claude Agent SDK, tool use via Telegram) |

---

## Sprint 6 — Complete (2026-04-10)

| Issue | Change |
|-------|--------|
| RA-531 | app/server/scanner.py: autonomous multi-project Pi-SEO scanner |
| RA-532 | Triage engine: auto-Linear ticket creation from findings |
| RA-533 | .harness/projects.json: registry of 10 monitored repos |
| RA-534 | skills/pi-seo-security: OWASP Top 10 + secret detection |
| RA-535 | skills/pi-seo-deployment: Vercel Sandbox + Core Web Vitals |
| RA-536 | skills/pi-seo-dependencies: CVE + outdated packages |
| RA-537 | Auto-PR generation for auto-fixable findings |
| RA-538 | dashboard/app/(main)/health: 10-repo health dashboard |
| RA-539 | cron-triggers.json: 6h scan rotation for all 10 repos |
| RA-540 | MCP: scan_project + get_project_health (13 tools total) |
| RA-541 | Vercel Sandbox pre-baked Chromium snapshot |
| RA-542 | Pi-SEO intelligence layer: 3 specialist skills + synthesiser |
| RA-543 | Ship-chain: /spec /plan /build /test /review /ship pipeline |

---

## Sprint 5 — Complete (2026-04-09)

| Issue | Change |
|-------|--------|
| RA-489–RA-508 | Security hardening: bcrypt, CSP nonce, Next.js auth middleware, pytest suite (34 tests) |
| RA-515–RA-527 | Pydantic validation, graceful shutdown, crash recovery, health 503, CI expansion |
| RA-528–RA-530 | .env.example, sessions.py refactor, structured logging |
| RA-485 | Claude Agent SDK PoC: board-meeting agent, parallel 14-cycle comparison run |

---

## Sprint 4 — Complete (2026-04-08)

| Issue | Change |
|-------|--------|
| RA-473 | scripts/smoke_test.py: 28-check E2E regression script |
| RA-474 | Dashboard /builds page + Pi CEO proxy route |
| RA-475 | Real build validated: 6/7 phases confirmed |
| RA-476 | linear_status diagnostic tool in Pi CEO MCP |

---

## Sprint 3 — Complete (2026-04-08)

| Issue | Change |
|-------|--------|
| RA-469 | MCP get_zte_score reads leverage-audit.md directly |
| RA-470 | E2E smoke test 22/22 pass; PITER priority bug fixed |
| RA-471 | git push retry: 3 attempts, 2s/4s backoff |
| RA-472 | handoff.md created |

---

## Sprints 1+2 — Complete (2026-04-07/08)

Foundation → Capability → ZTE Sprint: 35/60 → 60/60 across 26 issues (RA-449–RA-468 + ZTE sprint items).
