# Pi Dev Ops — Sprint Plan

_Sprint 10 active | 2026-04-14 | ZTE v2: 81/100_

## Status

Sprints 1–9 complete. Sprint 10 active. 85 features shipped.

---

## Sprint 10 — Active (2026-04-14)

**Theme:** MARATHON-4 + BVI Baseline + ZTE v2 C2/C3

| Issue | Priority | Title |
|-------|----------|-------|
| RA-588 | High | MARATHON-4: First 6-hour autonomous self-maintenance run — **In Progress** |
| RA-814 | High | BVI First Baseline — Cycle 24 snapshot |
| RA-815 | High | Harness doc regeneration — sprint_plan.md + feature_list.json |

**Sprint 10 targets:** ZTE v2 90/100 · MARATHON-4 completion · BVI baseline established

---

## Sprint 9 — Complete (2026-04-13)

**Theme:** Karpathy Enhancement Layer + Gap Audit

| Issue | Change |
|-------|--------|
| RA-674 | KARPATHY-1: Confidence-weighted evaluator — three-tier routing (auto-accept / review / retry), `CONFIDENCE: N%` parsing, Telegram low-confidence alert |
| RA-675 | KARPATHY-2: Reality-check sprint — closed 19-pt self-scan gap (41/60 → 60/60 ZTE); Pi-CEO scan accuracy fixed |
| RA-676 | KARPATHY-3: AUTONOMY_BUDGET single-knob — unified budget control across generator + evaluator |
| RA-677 | KARPATHY-4: Session Scope Contract — hard limits on file-touch radius, test-pass gate, reversibility check |
| RA-678 | KARPATHY-5: Progressive brief complexity — difficulty tiering for autonomous sessions |
| RA-679 | KARPATHY-6: Plan variation discovery — autoresearch-style 3-variant selection before generator runs |
| RA-680 | KARPATHY-7: Layered abstraction — TAO tier separation enforced in build pipeline |
| RA-681 | KARPATHY-8: Dependency alerting — CVE + breaking-change detection injected into session context |
| RA-682 | KARPATHY-9: Vercel drift monitoring — deployed SHA vs git HEAD parity watchdog |
| RA-683 | KARPATHY-10: Ship Chain Educational Series — 5-doc `docs/ship-chain/` nn-zero-to-hero style |
| RA-684 | Scout Agent: autonomous external intel loop — Monday 04:30 UTC cron, `agents/scout.py` |
| RA-685 | spec.md stale fix — harness doc regeneration pipeline wired to cron |
| RA-686 | CEO Board Skill: 9 personas wired into `board_meeting.py` (Revenue, Contrarian, Compounder, etc.) |
| RA-687 | 3 CRITICAL security alerts resolved — false-positive scanner bugs fixed (multiline regex, env files) |
| RA-651 | Supabase `gate_checks` table created + `log_gate_check()` in `supabase_log.py` |
| RA-656 | `gate_checks` writes wired into `sessions.py` Phase 5 evaluator |
| RA-660 | Incident history RAG — prior `lessons.jsonl` entries injected into session generator context |
| RA-673 | Pi-SEO activation — `PI_SEO_ACTIVE=1` set in Railway; live sweep running |
| RA-696 | BVI framework defined — Business Velocity Index replaces ZTE as primary board metric Cycle 24+ |
| RA-694 | Gap Audit Sprint — all 9 disconnected components wired (RA-684–693) |

**ZTE v2: 81/100** (was 60/60 v1)

---

## Sprint 8 — Complete (2026-04-11)

| Issue | Change |
|-------|--------|
| RA-551 | `agents/board_meeting.py`: Claude Agent SDK Phase 1 gap audit + `_run_prompt_via_sdk()` added |
| RA-556 | `_run_prompt_via_sdk()` migration in board_meeting.py; `TAO_USE_AGENT_SDK=1` to enable |
| RA-557 | dotenv `override=True` fix; `LINEAR_API_KEY` added to `.env`; `config.py` updated |
| RA-571–576 | `sessions.py` SDK migration: generator + evaluator → `claude_agent_sdk`; canary rollout; subprocess fallback removed |
| RA-577 | `CLAUDE.md` + `.harness/config.yaml` updated for SDK architecture |
| RA-579 | `cron.py`: startup catch-up + 12h watchdog fires Urgent Linear ticket if scheduler silent |
| RA-580 | Harness doc staleness watchdog — 48h alert if files not regenerated |
| RA-581 | `DEPLOYMENT.md`: production URLs, env matrix, rollback procedures |
| RA-582 | `scripts/verify_deploy.py`: commit parity audit — git HEAD vs Vercel + Railway SHAs |
| RA-583 | CI `smoke-prod` job: `smoke_test.py --target=prod` on main-branch pushes |
| RA-584 | `app/server/autonomy.py`: Linear todo poller, `/api/autonomy/status` endpoint |
| RA-585 | MARATHON-1: `pipeline.py` + `orchestrator.py` migrated to Agent SDK; 7 new tests (46 total) |
| (CI fix) | `app/server/main.py`: health endpoint no longer gates on `_claude_ok`; CI 28/28 pass |

---

## Sprint 7 — Complete (2026-04-10)

| Issue | Change |
|-------|--------|
| RA-546 | Mobile/tablet responsive layout: bottom tab bar, card history, iOS zoom fix |
| RA-547 | `.claude/settings.json`: WorktreeCreate/WorktreeRemove hooks for worktree isolation |
| RA-548 | `dashboard/app/api/telegram/route.ts`: @piceoagent_bot commands + Claude chat |
| RA-549 | Railway: claude-code-telegram agentic bot (full Claude Agent SDK, tool use via Telegram) |

---

## Sprint 6 — Complete (2026-04-10)

| Issue | Change |
|-------|--------|
| RA-531–543 | Pi-SEO autonomous scanner: 10-repo monitoring, triage engine, auto-PR, health dashboard, 6h cron rotation, 13 MCP tools |

---

## Sprints 1–5 — Complete (2026-04-07–09)

Foundation → Security Hardening → Capability → ZTE Sprint: 0 → 81/100 v2 across 70+ issues.
