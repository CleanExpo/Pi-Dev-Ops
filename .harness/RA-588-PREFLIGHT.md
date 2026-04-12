# RA-588 — MARATHON-4 Pre-Flight Checklist
## First 6-Hour Autonomous Self-Maintenance Run

**Date:** 2026-04-12  
**Current ZTE Score:** 71/75 (Zero Touch Band)  
**Status:** All dependencies complete. Awaiting Railway env var activation.

---

## 🔧 STEP 1 — Set Railway Environment Variables

Log into Railway → Pi Dev Ops project → Variables tab. Set all of the following:

| Variable | Value | Purpose |
|---|---|---|
| `PI_SEO_ACTIVE` | `1` | Enables live scan/monitor cron triggers |
| `TELEGRAM_BOT_TOKEN` | `8630069375:AAH5CDnCm5ApdFsdfFz1KwNGEFDtgy9yvDA` | Pi-SEO critical finding alerts + /status command |
| `TELEGRAM_ALERT_CHAT_ID` | `8792816988` | Your Telegram user ID (receives critical alerts) |

After setting: **Redeploy** (Railway → Deployments → Redeploy latest).

**Verify:** Within 10 minutes of redeploy, check the Railway logs for:
```
PI_SEO_ACTIVE=0 — Pi-SEO cron scans are paused
```
should disappear, replaced by scan trigger firings.

---

## 🔧 STEP 2 — Verify Telegram Bot is Responding

Send `/status` to your Telegram bot. You should get a reply within 30 seconds showing:

```
🤖 Pi-CEO Status
Active sessions: 0/3
Autonomy poll: Xm ago
Effective autonomy: 100%
Stale: ✅ no
```

If no reply: check that `TELEGRAM_BOT_TOKEN` is set in Railway and that the Railway Python bot is running (it handles the polling — the n8n workflow is an optional overlay).

---

## 🔧 STEP 3 — Confirm Linear API Key is Active

In Railway Variables, verify `LINEAR_API_KEY` is set (it should be already from previous sprints).

**Verify:** Send `/status` to Telegram and confirm sessions count is not showing errors.

Alternatively, check Railway logs for:
```
Autonomy poll #N: X todo issues found
```

---

## ✅ PRE-FLIGHT READINESS CHECKLIST

```
[ ] PI_SEO_ACTIVE=1 set in Railway
[ ] TELEGRAM_BOT_TOKEN set in Railway  
[ ] TELEGRAM_ALERT_CHAT_ID set in Railway
[ ] Railway redeployed after env var changes
[ ] /status Telegram command responding
[ ] Autonomy poller last_poll_ago_s < 300 (confirmed via /status or /api/autonomy/status)
[ ] lessons.jsonl has 30+ entries (currently 38 ✅)
[ ] ZTE score 68+ (currently 71/75 ✅)
[ ] cron-triggers.json has 12 triggers (confirmed ✅)
[ ] intel-refresh-monday trigger merged (confirmed ✅)
```

---

## 🚀 HOW TO START THE RUN

The 6-hour run starts **automatically** once the above checklist is complete. No manual trigger needed.

The autonomy poller (every 5 minutes) will:
1. Fetch Urgent/High priority Todo issues from the Pi-Dev-Ops Linear project
2. Transition each to In Progress
3. Fire a build session via the 5-phase pipeline (Plan → Generate → Evaluate → Test → Ship)
4. Comment on the Linear issue with session ID + outcome

The Pi-SEO cron rotation will simultaneously:
- Scan all 11 repos on the 6-hour schedule
- Triage new critical/high/medium findings → Linear tickets
- Alert you on Telegram for every critical finding

---

## 📊 HOW TO MONITOR THE RUN

### Telegram Commands (every ~60 min)
```
/status   → active sessions, autonomy poll age, effective autonomy %
/alerts   → latest portfolio health + alert count
```

### Railway Logs (continuous)
Watch for:
- `Autonomy poll #N: X todo issues found`
- `Autonomy: session XXXX started for RA-NNN`
- `Scan trigger id=scan-high-XXXX complete: N tickets created`
- `intel_refresh id=intel-refresh-monday complete: fetched=3`

### Dashboard
```
https://pi-dev-ops-production.up.railway.app/
```
Live session panel, ZTE score, recent events.

### Linear Board
Pi-Dev-Ops project → watch issues transition Todo → In Progress → Done

---

## 🛑 KILL SWITCH

To stop the autonomous run at any time:

**Option A — Railway env var:**
Set `TAO_AUTONOMY_ENABLED=0` in Railway → Redeploy

**Option B — Telegram:**
Send `/stop` to the bot (if RA-649 n8n workflow is active)

**Option C — Emergency:**
Railway → Pi Dev Ops → Deployments → Rollback

---

## 📋 SUCCESS CRITERIA (from RA-588)

| Criterion | Pass Condition |
|---|---|
| Duration | 6 continuous hours without manual intervention |
| Feature shipped | ≥1 Linear issue: Plan → Build → Test → Merged |
| Error rate | 0 unhandled exceptions in run log |
| Evaluator trend | Score stable or improving over the run |
| Cost | Under configured ceiling (Claude Max 20x plan = $0 API cost) |

---

## ⚠️ KNOWN RISKS

| Risk | Mitigation |
|---|---|
| No Urgent/High Todo tickets in Linear | Create 1-2 synthetic test tickets before the run |
| Scan triggers skipped if PI_SEO_ACTIVE not set | Set Railway env var first (Step 1) |
| n8n admin password unknown | Use Railway Python bot for Telegram commands; see `.harness/n8n-workflows/RA-649-IMPORT-INSTRUCTIONS.md` to restore n8n |
| UPS not installed (RA-641) | Power cut during run = outage. Ensure Mac Mini is on stable power for 6h window |

---

## 📁 REFERENCE FILES

| File | Purpose |
|---|---|
| `.harness/cron-triggers.json` | All 12 active cron triggers |
| `.harness/n8n-workflows/RA-649-telegram-command-interface.json` | n8n workflow to import |
| `.harness/n8n-workflows/RA-649-IMPORT-INSTRUCTIONS.md` | n8n setup guide |
| `app/server/autonomy.py` | Autonomous poller code |
| `app/server/cron.py` | Cron dispatch (scan/monitor/intel_refresh/analyse_lessons) |
| `app/server/triage.py` | Triage engine + Telegram critical alerts |
| `scripts/sandbox_health_check.py` | Sandbox verification health check |

---

*Generated 2026-04-12 by Pi-CEO Enhanced — Cycle 21 (RA-586, RA-587 deploy session)*
