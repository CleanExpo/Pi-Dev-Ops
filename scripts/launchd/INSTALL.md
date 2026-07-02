# Pi-CEO launchd Agents (RA-3752 / RA-3753)

Canonical source for all `com.piceo.*` macOS launchd jobs.
Hand-edited `~/Library/LaunchAgents/` plists are forbidden — drift will be
detected by the daily `--check` cron (see RA-3752).

## Files

| File | Purpose |
|---|---|
| `com.piceo.fastapi-standby.plist` | Pi-CEO FastAPI at `127.0.0.1:7777`. KeepAlive + RunAtLoad. Sources `app/.env.local` before uvicorn (not repo-root `.env.local`). |
| `com.piceo.healthcheck.plist` | Every 5 min probe of Ollama + n8n + Pi-CEO API. Auto-restarts Pi-CEO if down (RA-3753). Telegram alerts on failure. |
| `health_check.py` | The script driven by `com.piceo.healthcheck.plist`. |
| `../install_launchd_agents.sh` | Idempotent installer — copies canonical plists into `~/Library/LaunchAgents/` and `launchctl bootstrap`s each one. Detects `.disabled` renames + canonical drift. |

## First-time setup

```bash
# 1) Secrets file for healthcheck (NEVER commit)
mkdir -p ~/.config/piceo
cat > ~/.config/piceo/healthcheck.env <<'EOF'
PICEO_BOT_TOKEN=<your-piceoagent-bot-token>
PICEO_CHAT_ID=8792816988
EOF
chmod 600 ~/.config/piceo/healthcheck.env

# 2) Drop the health_check.py into the runtime path
mkdir -p ~/pi-ceo/logs
cp scripts/launchd/health_check.py ~/pi-ceo/health_check.py
chmod +x ~/pi-ceo/health_check.py

# 3) Install + bootstrap the launchd jobs
./scripts/install_launchd_agents.sh

# 4) Verify
launchctl list | grep com.piceo
curl -s http://127.0.0.1:7777/health   # → {"status":"ok"}
```

## Daily drift check

Add to your `.harness/cron-triggers.json` (suggested 06:00 UTC):

```json
{
  "id": "launchd-drift-check-daily-0600",
  "type": "script",
  "script": "scripts/install_launchd_agents.sh",
  "args": ["--check"],
  "hour": 6, "minute": 0, "enabled": true
}
```

Run manually anytime:

```bash
./scripts/install_launchd_agents.sh --check
```

Exit code is non-zero if any plist is renamed, missing, or differs from the canonical version. Wire that into your alerting if you want a passive watchdog.

## Why we changed this (2026-05-12)

A `~/Library/LaunchAgents/com.piceo.fastapi-standby.plist` rename to `*.disabled` (timestamp `Apr 19 18:03`) wasn't tracked by anything. The running uvicorn process stayed alive in memory until it shut down at `2026-05-12 05:56:38 UTC` — then launchd had no plist to load, and the existing `com.piceo.healthcheck` script wasn't probing the Pi-CEO API anyway, so the alert path was silent. 20 minutes of dead swarm before manual detection.

Both gaps closed in PR — see RA-3752 + RA-3753.
