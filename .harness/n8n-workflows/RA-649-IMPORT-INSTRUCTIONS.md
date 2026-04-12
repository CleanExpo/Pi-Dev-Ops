# RA-649 — Telegram Command Interface: Import Instructions

## Pre-requisites

1. **Reset n8n admin password** (if you can't log in):
   ```
   docker exec -it <n8n-container-name> n8n user-management:reset
   ```
   Then follow the prompts to set a new password.

2. **Set environment variables in n8n** (Settings → Variables, or your n8n Docker `environment:` block):

   | Variable | Value |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | `8630069375:AAH5CDnCm5ApdFsdfFz1KwNGEFDtgy9yvDA` |
   | `SUPABASE_SERVICE_ROLE_KEY` | (from Pi-Dev-Ops `.env`) |

   These are read via `process.env.TELEGRAM_BOT_TOKEN` inside the Code nodes — no credentials object needed.

---

## Import Steps

1. Open n8n → **Workflows** → click **+** (New Workflow)
2. In the blank canvas, click the **⋮** menu (top right) → **Import from file**
3. Select: `.harness/n8n-workflows/RA-649-telegram-command-interface.json`
4. Click **Save** and name it `RA-649 — Telegram Command Interface`
5. Click the **Activate** toggle (top right) to enable the workflow

---

## What the Workflow Does

```
[Schedule: every 30s]
  → [Read last update_id from Supabase]
  → [Telegram getUpdates with offset]
  → [IF no new messages → stop]
  → [Parse command + build reply]  ← /status /alerts /triage /help
  → [Telegram sendMessage]
  → [Persist new update_id to Supabase]
```

- **Only responds to user ID `8792816988`** (Phill) — all other users get `⛔ Unauthorised.`
- **Uses native `fetch()`** throughout — no `$http` helper (n8n v2 compatible)
- **Offset is stored in Supabase** `settings` table under key `telegram_last_update_id` — survives n8n restarts without re-processing old messages

---

## Commands

| Command | Response |
|---|---|
| `/status` | Live session count, autonomy poll age, effective autonomy %, stale flag |
| `/alerts` | Latest Pi-SEO monitor digest — portfolio health, alert count, critical count |
| `/triage` | Link to Pi-CEO dashboard |
| `/help` | Command list |

---

## Verify It's Working

1. Send `/help` to the bot (`@PiDevOps_bot` or whatever it's named)
2. You should get the command list back within ~30 seconds
3. Check Supabase → `settings` table → `telegram_last_update_id` should have updated

---

## Note on the Railway Python Bot

The Railway bot (`pi-dev-ops-production.up.railway.app`) is still running and handles the same commands. Once this n8n workflow is active, both will respond unless the Railway bot is disabled. They use the same Telegram bot token — Telegram routes each message to whichever one calls `getUpdates` first. The n8n workflow uses offset tracking so it won't fight with the Railway bot, but you may get duplicate replies. Consider disabling the Railway bot's Telegram polling (`TAO_TELEGRAM_ENABLED=0`) once the n8n workflow is confirmed working.
