# Pi-CEO Enhanced — Linear Ticket Package

**Board Decision Date:** 2026-04-12
**Approved by:** CEO Board (9 personas, full deliberation)
**Deliberation:** `.harness/BOARD-DELIBERATION-ENHANCED-2026-04-12.md`

---

## Summary

16 tickets filed across 3 committed phases + governance.
Phases 3-6 approved in principle, gated on 14-day clean-operation metric.

## Architecture (Board-Approved)

| Component | Where | RAM Cost |
|-----------|-------|----------|
| Qwen 3 14B / Llama 3.3 8B | Ollama native (NOT Docker) | ~10-12GB |
| n8n | Docker (single container) | ~0.5GB |
| Supabase | Cloud free tier (NOT local) | 0GB |
| Open WebUI | Native Python or Docker (Phase 2) | ~0.5GB |
| Qdrant | DROPPED (pgvector sufficient) | 0GB |
| macOS | Always-on, never sleeps | ~4GB |
| **Total** | | **~17GB / 24GB** |

## Critical Research Findings Incorporated

1. **Qwen 3 14B tool-calling broken on Ollama** → test both Qwen and Llama 3.3 8B
2. **M4 Mac Mini auto-restart unreliable** → UPS is mandatory, not optional
3. **n8n misses crons if Mac sleeps** → caffeinate via launchd in Phase 0
4. **Docker Desktop defaults to 4GB RAM** → cap at 2GB
5. **Ollama health check** → use `/api/tags` not just process alive

---

## Phase 0 — Self-Healing Setup (Day 1, Monday Apr 13)
*All Urgent priority. Blocks everything else.*

| Ticket | Title | Owner |
|--------|-------|-------|
| [RA-637](https://linear.app/unite-group/issue/RA-637) | Configure Mac Mini auto-restart + sleep prevention | Phill |
| [RA-638](https://linear.app/unite-group/issue/RA-638) | Install Ollama + Qwen 3 14B + launchd auto-restart | Phill + Pi-CEO |
| [RA-639](https://linear.app/unite-group/issue/RA-639) | Deploy n8n Docker container with restart policy | Phill + Pi-CEO |
| [RA-640](https://linear.app/unite-group/issue/RA-640) | Create health-check aggregation + Telegram alerting | Pi-CEO |
| [RA-641](https://linear.app/unite-group/issue/RA-641) | Purchase/confirm UPS for Mac Mini — MANDATORY | Phill |

## Phase 1 — Local Brain Online (Days 2-6, Tue Apr 14 - Sat Apr 18)
*All High priority.*

| Ticket | Title | Owner |
|--------|-------|-------|
| [RA-642](https://linear.app/unite-group/issue/RA-642) | Create Supabase cloud project for Pi-CEO memory | Phill + Pi-CEO |
| [RA-643](https://linear.app/unite-group/issue/RA-643) | Build n8n Linear polling workflow (5-min cron) | Pi-CEO |
| [RA-644](https://linear.app/unite-group/issue/RA-644) | Build triage prompt — test Qwen 3 14B AND Llama 3.3 8B | Pi-CEO |
| [RA-645](https://linear.app/unite-group/issue/RA-645) | Build n8n Telegram escalation workflow | Pi-CEO |
| [RA-646](https://linear.app/unite-group/issue/RA-646) | Migrate heartbeat crons from Cowork to n8n | Pi-CEO |

## Phase 2 — Dashboard + Command Interface (Days 7-11, Sun Apr 19 - Thu Apr 23)
*All High priority.*

| Ticket | Title | Owner |
|--------|-------|-------|
| [RA-647](https://linear.app/unite-group/issue/RA-647) | Install and configure Open WebUI | Pi-CEO + Phill |
| [RA-648](https://linear.app/unite-group/issue/RA-648) | Build portfolio health dashboard view | Pi-CEO |
| [RA-649](https://linear.app/unite-group/issue/RA-649) | Build Telegram command interface | Pi-CEO |
| [RA-650](https://linear.app/unite-group/issue/RA-650) | Build Claude API routing logic with cost tracking | Pi-CEO |

## Governance
*High priority.*

| Ticket | Title | Owner |
|--------|-------|-------|
| [RA-651](https://linear.app/unite-group/issue/RA-651) | Define 14-day clean-operation gate criteria | Pi-CEO + Phill |
| [RA-652](https://linear.app/unite-group/issue/RA-652) | Revise ZTE scoring to include operational health | Pi-CEO |

---

## 14-Day Gate (Phases 3-6 gated on this)

The Mac Mini must run for 14 consecutive days without manual intervention.

| Metric | Target |
|--------|--------|
| Uptime | > 99.5% |
| Ollama crashes | < 3 |
| n8n success rate | > 95% |
| Triage accuracy | > 80% |
| Manual interventions | 0 |
| Escalation effectiveness | ≥ 1 acted-on alert |

**If gate fails twice:** fall back to GH-Actions-only architecture (previous board decision).

---

## Day 1 Phill Actions (Monday Apr 13)

1. Enable Mac Mini Energy Settings (auto-restart + prevent sleep) — 2 min
2. Install Ollama via `brew install ollama` — 2 min
3. Pull models: `ollama pull qwen3:14b && ollama pull llama3.3:8b` — 10 min
4. Install Docker Desktop (if not installed) — 5 min
5. Cap Docker memory to 2GB in Docker Desktop settings — 1 min
6. Confirm UPS is present or order one — 5 min
7. Run `docker compose up -d` for n8n — 1 min

**Total Phill time Day 1: ~26 minutes.**
Everything else is Pi-CEO autonomous from that point.
