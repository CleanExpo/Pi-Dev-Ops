# Pi-Dev-Ops — Deployment Reference

Single source of truth for production services, hosting, env vars, and rollback procedures.

**Last updated:** 2026-04-11 (RA-581)

---

## Production URLs

| Service | Canonical URL | Status |
|---------|--------------|--------|
| Dashboard (frontend) | https://dashboard-unite-group.vercel.app | ✅ Live |
| Backend API | https://pi-dev-ops-production.up.railway.app | ✅ Live |
| Backend health | https://pi-dev-ops-production.up.railway.app/health | ✅ |
| Telegram Bot | (Railway background service, no public URL) | ✅ Live |

**URL note:** The canonical frontend URL is `dashboard-unite-group.vercel.app`. A second Vercel project (`pi-dev-ops-unite-group.vercel.app`, `prj_I5sYqNTlL51DlvyzSFjiHX6FrLAX`) is GitHub-linked and auto-deploys from `main`. Both point at the same Next.js code; `dashboard` is the primary serving alias.

---

## Hosting Inventory

### Vercel (Frontend)

| Project | Vercel Project ID | Domain | GitHub Repo | Root Dir |
|---------|-------------------|--------|-------------|---------|
| dashboard | `prj_eIA6deQ13rgCFU3jhMBHAA4g27ng` | dashboard-unite-group.vercel.app | (manual deploy) | — |
| pi-dev-ops | `prj_I5sYqNTlL51DlvyzSFjiHX6FrLAX` | pi-dev-ops-unite-group.vercel.app | CleanExpo/Pi-Dev-Ops | `dashboard/` |
| Team | `team_KMZACI5rIltoCRhAtGCXlxUf` | — | — | — |

### Railway (Backend)

| Service | Railway project | Host | Deploys from |
|---------|-----------------|------|--------------|
| pi-ceo (FastAPI) | `pi-ceo` | pi-dev-ops-production.up.railway.app | CleanExpo/Pi-Dev-Ops Dockerfile |
| pi-ceo-telegram-bot | `pi-ceo-telegram-bot` | (internal) | Separate Railway project |

Railway config: [`railway.toml`](railway.toml), [`Dockerfile`](Dockerfile)

### GitHub (CI/CD)

| Workflow | File | Triggers | Checks |
|----------|------|----------|--------|
| CI | `.github/workflows/ci.yml` | push/PR to main | ruff, pytest, eslint, frontend build |
| Smoke Test | `.github/workflows/smoke_test.yml` | push/PR to main | 28-check API smoke test |

---

## Health Check Endpoints

| Service | URL | Method | Expected Response |
|---------|-----|--------|-------------------|
| Backend | `/health` | GET | `{"status":"ok","uptime_s":N,...}` → HTTP 200 |
| Backend (degraded) | `/health` | GET | `{"status":"degraded",...}` → HTTP 503 |
| Autonomy | `/api/autonomy/status` | GET (auth) | `{"enabled":true,"last_poll_ago_s":N,...}` |

---

## Environment Variable Matrix

### Backend (`app/server/` — set in Railway env)

| Variable | Required | Notes |
|----------|----------|-------|
| `TAO_PASSWORD` | **Required** | Dashboard login password. Set in Railway env. |
| `TAO_SESSION_SECRET` | Optional | Auto-generated on first boot. Set explicitly to survive redeploys. |
| `ANTHROPIC_API_KEY` | **Required** | Starts with `sk-ant-`. Without it, Claude sessions fail. |
| `LINEAR_API_KEY` | **Required** | Starts with `lin_api_`. Without it, Pi-SEO runs dry-run mode. |
| `TAO_LINEAR_WEBHOOK_SECRET` | Optional | Webhook signature verification for Linear events. |
| `TAO_WEBHOOK_SECRET` | Optional | Webhook signature verification for GitHub events. |
| `GITHUB_TOKEN` | Optional | GitHub PAT (`ghp_...`) for private repo access. |
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram bot integration. |
| `TELEGRAM_WEBHOOK_SECRET` | Optional | Verifies Telegram webhook requests. |
| `TAO_AUTONOMY_ENABLED` | Optional | Set to `0` to disable Linear todo poller. Default: `1` (on). |
| `TAO_AUTONOMY_POLL_INTERVAL` | Optional | Seconds between polls. Default: `300` (5 min). |
| `TAO_EVALUATOR_ENABLED` | Optional | Enable/disable build evaluator. Default: `true`. |
| `TAO_EVALUATOR_THRESHOLD` | Optional | Minimum quality score (0-10). Default: `8`. |
| `TAO_MAX_SESSIONS` | Optional | Max concurrent Claude sessions. Default: `3`. |
| `TAO_GC_MAX_AGE` | Optional | Session workspace GC age in seconds. Default: `14400`. |
| `SCAN_WORKSPACE_ROOT` | Optional | Where Pi-SEO clones repos. Default: `~/pi-seo-workspace`. |

### Frontend (`dashboard/` — set in Vercel project env)

| Variable | Required | Notes |
|----------|----------|-------|
| `PI_CEO_URL` | **Required** (prod) | Backend URL. Prod: `https://pi-dev-ops-production.up.railway.app` |
| `PI_CEO_PASSWORD` | **Required** (prod) | Same value as `TAO_PASSWORD`. |
| `NEXT_PUBLIC_SUPABASE_URL` | Optional | Supabase project URL. Needed if using Supabase features. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Optional | Supabase anon key. |
| `SUPABASE_SERVICE_ROLE_KEY` | Optional | Supabase service role (server-side only). |
| `ANTHROPIC_API_KEY` | Optional | Used by dashboard API routes for direct AI calls. |
| `GITHUB_TOKEN` | Optional | For GitHub API calls from dashboard routes. |
| `TELEGRAM_BOT_TOKEN` | Optional | For Telegram integration in dashboard. |
| `ANALYSIS_MODE` | Optional | Default: `api`. Controls how analysis runs. |

### CI (`.github/workflows/` — set in GitHub repo secrets)

| Secret | Used by | Notes |
|--------|---------|-------|
| `TAO_PASSWORD` | smoke_test.yml | Falls back to `ci-smoke-test-password` if not set. |

---

## Deployment Log

| Ticket | What shipped | Service |
|--------|-------------|---------|
| RA-483 | Initial FastAPI server + Railway deployment | Backend (pi-ceo) |
| RA-549 | Telegram bot Railway service | pi-ceo-telegram-bot |
| RA-518 | CSP headers + nonce middleware | Frontend |
| RA-528 | .env.example + secrets audit | All |
| RA-551 | Sprint 6 Agent SDK Phase 1 (board_meeting) | Backend |
| RA-556 | SDK `_run_prompt_via_sdk()` migration | Backend |
| RA-557 | dotenv fix, LINEAR_API_KEY | Backend |
| RA-584 | Linear todo poller (autonomy) | Backend |
| RA-579 | Cron watchdog + startup catch-up | Backend |
| RA-582 | `scripts/verify_deploy.py` | Tooling |
| RA-581 | This document | Docs |

---

## Rollback Procedures

### Vercel (Frontend)

```bash
# Option 1: Promote a previous deployment to production
vercel promote <deployment-url> --scope unite-group

# Option 2: Via dashboard
# Vercel Dashboard → Pi-Dev-Ops → Deployments → select previous → "Promote to Production"
```

### Railway (Backend)

```bash
# Option 1: Redeploy a previous commit
# Railway Dashboard → pi-ceo service → Deployments → select previous → "Redeploy"

# Option 2: Git revert + push (triggers auto-deploy)
git revert HEAD && git push origin main
```

### Emergency Stop

```bash
# Disable autonomous Linear poller (doesn't require deploy):
# Set TAO_AUTONOMY_ENABLED=0 in Railway env and restart service

# Kill all active Claude sessions:
curl -X POST https://pi-dev-ops-production.up.railway.app/api/sessions/<id>/kill \
  -H "Authorization: Bearer <session-token>"
```

---

## Verify Deployment Parity

```bash
# Check git HEAD vs deployed SHAs on Railway + Vercel:
python scripts/verify_deploy.py

# Run full smoke test against production:
python scripts/smoke_test.py \
  --url https://pi-dev-ops-production.up.railway.app \
  --password "$TAO_PASSWORD"
```
