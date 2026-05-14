# Multi-bot Telegram setup (RA-2232)

The swarm now routes Telegram messages across **five logical channels**:

| Channel | Bot purpose | Token env var | Chat-id env var |
|---|---|---|---|
| `general` | Margot — Phill's direct inbox, ideas, voice notes | `TELEGRAM_BOT_TOKEN` | `TELEGRAM_HOME_CHANNEL` (legacy: `TELEGRAM_ALERT_CHAT_ID`) |
| `research` | Senior Research Analyst, PM bot recon, grounded-research output | `TELEGRAM_BOT_TOKEN_RESEARCH` | `TELEGRAM_CHAT_ID_RESEARCH` |
| `dev` | `feature_orchestrator` / `fix_orchestrator` PRs, CI, scan results | `TELEGRAM_BOT_TOKEN_DEV` | `TELEGRAM_CHAT_ID_DEV` |
| `ops` | CFO / COO / Compliance alerts, watchdog escalations, budget | `TELEGRAM_BOT_TOKEN_OPS` | `TELEGRAM_CHAT_ID_OPS` |
| `marketing` | CMO, brand-guardian violations, Synthex content drafts | `TELEGRAM_BOT_TOKEN_MARKETING` | `TELEGRAM_CHAT_ID_MARKETING` |

Channels with no token configured **fall back to `general`** with a `[fallback from <channel>]` prefix on the message body — so onboarding is gradual: mint one bot, add its env vars, reload the swarm, repeat.

---

## What to do — 5 minutes per bot

1. Open a chat with `@BotFather` in Telegram.
2. For each new bot, send `/newbot` and follow the prompts:

   | Display name | Username (must end in `Bot`) |
   |---|---|
   | `Pi-CEO Research` | `PiCeoResearchBot` |
   | `Pi-CEO Dev`      | `PiCeoDevBot`      |
   | `Pi-CEO Ops`      | `PiCeoOpsBot`      |
   | `Pi-CEO Marketing`| `PiCeoMarketingBot`|

3. BotFather returns a token like `123456:ABC-DEF...` for each bot — copy them.
4. Start a chat with each new bot (DM it `/start`) so it can message you back.
5. Get each chat's `chat_id`. Easiest path:
   1. Send any message in the chat.
   2. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser.
   3. Look for `chat.id` — positive for DMs, negative for groups.
6. Add to `~/.hermes/.env`:

   ```sh
   # research
   TELEGRAM_BOT_TOKEN_RESEARCH=123456:ABC-...
   TELEGRAM_CHAT_ID_RESEARCH=<chat id>
   # dev
   TELEGRAM_BOT_TOKEN_DEV=...
   TELEGRAM_CHAT_ID_DEV=...
   # ops
   TELEGRAM_BOT_TOKEN_OPS=...
   TELEGRAM_CHAT_ID_OPS=...
   # marketing
   TELEGRAM_BOT_TOKEN_MARKETING=...
   TELEGRAM_CHAT_ID_MARKETING=...
   ```

7. Reload the swarm so the new env is picked up:

   ```sh
   launchctl unload ~/Library/LaunchAgents/ai.pidev.swarm.plist
   launchctl load   ~/Library/LaunchAgents/ai.pidev.swarm.plist
   ```

8. Verify in Python:

   ```sh
   cd ~/Pi-CEO/Pi-Dev-Ops
   python3 -c "from swarm.telegram_router import configured_channels; print(configured_channels())"
   ```

   Should list every channel whose token + chat_id are both set.

---

## Gradual onboarding (recommended)

You don't have to mint all four at once. Mint **dev first** — that's the noisiest workload (PR/CI/scan pings flooding from `feature_orchestrator` and the cron watchdogs). Once dev is split out, Phill's general inbox is materially quieter and the value of routing the other three is obvious.

Order of operations Phill is likely to want:

1. **dev** — silences PR/CI noise in the main inbox immediately
2. **ops** — moves watchdog/health escalations to a dedicated chat
3. **marketing** — gates brand-guardian violations + Synthex content drafts
4. **research** — PM bot daily briefings + grounded research

Until a channel is minted, its messages route to general with the fallback prefix, so nothing is lost — it's just tagged so Phill can see how much volume each channel would relieve.

---

## Calling the router from code

Existing callers using `swarm.telegram_alerts.send(...)` keep working unchanged — they route to `general`. New code (or call sites being migrated) should call the router directly with `channel=`:

```python
from swarm.telegram_router import send

send("Watchdog: oldest urgent ticket 36h old",
     channel="ops", severity="high", bot_name="Watchdog")

send("PR opened: feature_orchestrator → IDD-3 → RA-4180",
     channel="dev", severity="info", bot_name="FeatureOrchestrator")
```

Already migrated (RA-2232):

- `swarm/feature_orchestrator.py::_alert` → `dev`
- `app/server/cron_watchdogs.py::_health_full_send_telegram` → `ops`

Everything else (orchestrator startup, bots/guardian, bots/builder, bots/scribe, bots/click, bots/chief_of_staff) still routes to `general` via `telegram_alerts.send`. Migrate further call sites as the channels are minted and the routing pattern proves stable.
