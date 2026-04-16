# Pi Dev Ops — Handoff Document

_Last updated: 2026-04-16 | Sprint 12 active | ZTE v2: 85/100 | 98+ features_

---

## System State

Pi CEO is live and autonomous. The always-on path is:

- **Railway** — FastAPI backend, autonomy poller, cron scheduler, Telegram bot
- **Vercel** — Next.js dashboard
- **GitHub Actions** — CI/CD (pytest + ruff + ESLint + smoke test)

Local Mac processes (n8n, OpenCode, Claude Code desktop) are supplemental, not on the critical path.

---

## Architecture

```
Linear Todo → autonomy.py (5-min poll) → POST /api/build
  → Phase 1: git clone (workspace isolation)
  → Phase 2: repo scan + grounded brief construction
  → Phase 3: plan discovery (3-variant selection)
  → Phase 4: claude_agent_sdk generator (Sonnet 4.6)
  → Phase 5: confidence-weighted evaluator (Sonnet 4.6, parallel)
  → Phase 6: git push → pidev/auto-{sid[:8]} feature branch
  → Lessons extraction → Pi-SEO scan → Linear triage
```

Three tiers: Opus 4.6 (planner), Sonnet 4.6 (generator + evaluator), Haiku 4.5 (fast tasks).

---

## Key Services

| Service | URL | Host |
|---------|-----|------|
| Backend API | https://pi-dev-ops-production.up.railway.app | Railway |
| Dashboard | https://dashboard-unite-group.vercel.app | Vercel |
| Health | https://pi-dev-ops-production.up.railway.app/health | Railway |
| Telegram Bot | @piceoagent_bot | Railway (background) |

---

## Environment — What's Required

### Railway (backend)

| Var | Status | Notes |
|-----|--------|-------|
| `TAO_PASSWORD` | Required | Dashboard login |
| `ANTHROPIC_API_KEY` | Required | `sk-ant-` — Claude sessions |
| `LINEAR_API_KEY` | Required | `lin_api_` — autonomy poller |
| `GITHUB_TOKEN` | Required | Push to feature branches |
| `GITHUB_REPO` | Required | e.g. `CleanExpo/Pi-Dev-Ops` |
| `ENABLE_PROMPT_CACHING_1H` | Set to `1` | Cost reduction |
| `TAO_SWARM_SHADOW` | Set to `0` | Swarm active mode |
| `TELEGRAM_BOT_TOKEN` | Optional | Alerts |

### Swarm — still needs

- `TAO_SWARM_SHADOW=0` confirmed in Railway env
- `TAO_PASSWORD` in `.env.local` for local builder

---

## Open PRs (merge queue)

| PR | What |
|----|------|
| #22 | RA-1027: Multi-persona parallel evaluator |
| #24 | RA-1014–1017: Security batch 3 |
| #25 | RA-1018–1023: Security batch 4 |
| #30 | RA-1011: Routine run outcome tracker |

---

## Sprint 12 Focus

**Theme:** Swarm Activation + ZTE v2 → 90 + NotebookLM KB

Active: RA-822/823/824 (NotebookLM KB build), RA-838 (SDK canary), RA-886 (branch protection), RA-830 (Gemini evaluation post-Google Cloud Next).

Next board: 6 May 2026 (Enhancement Review, RA-949).

---

## How to Resume a Stalled Session

```bash
# Check autonomy status
curl https://pi-dev-ops-production.up.railway.app/api/autonomy/status \
  -H "Authorization: Bearer <token>"

# If autonomy.armed = false → check LINEAR_API_KEY in Railway env
# If sessions.total = 0 for >15 min → check /health autonomy block

# Reset a stalled Linear issue to Todo (makes it visible to poller):
# Linear → issue → change status to Todo
```

## Key Files

| File | What it is |
|------|-----------|
| `.harness/config.yaml` | Agent models, evaluator thresholds, autonomy budget |
| `.harness/cron-triggers.json` | 13 active cron triggers |
| `app/server/routes/` | 8 FastAPI route modules |
| `app/server/autonomy.py` | Linear poller loop |
| `app/server/sessions.py` | Session lifecycle facade |
| `mcp/pi-ceo-server.js` | 21 MCP tools |
| `skills/` | 33 SKILL.md files |
