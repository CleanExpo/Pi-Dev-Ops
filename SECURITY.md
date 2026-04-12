# Security & Credential Architecture

> Pi-Dev-Ops | Unite-Group | Last updated: 2026-04-12

---

## Rule: Never commit credentials

No API keys, tokens, passwords, or secret values belong in this repository.
If you accidentally commit a secret — rotate it immediately, do not just remove it from history.

---

## Credential map

| Credential | Location | Safe to commit? | Notes |
|-----------|----------|----------------|-------|
| `ANTHROPIC_API_KEY` | `.env` (gitignored) | NO | Rotate at https://console.anthropic.com |
| `LINEAR_API_KEY` | `.env` (gitignored) | NO | Rotate at https://linear.app/settings/api |
| `SUPABASE_URL` | `.env` + `dashboard/index.html` | URL yes, keys no | Project URL is non-secret |
| `SUPABASE_ANON_KEY` | `dashboard/index.html` | YES — by design | Public client key, RLS-protected. Read-only dashboard queries only. |
| `SUPABASE_SERVICE_ROLE_KEY` | `.env` (gitignored) | NO | Full DB access — treat like a root password |
| `SUPABASE_PUBLISHABLE_KEY` | `.env` (gitignored) | NO | |
| `TELEGRAM_BOT_TOKEN` | `telegram-bot/.env` (gitignored) | NO | Rotate via @BotFather |
| `TELEGRAM_CHAT_ID` | `telegram-bot/.env` (gitignored) | NO | Your personal Telegram ID |
| `TAO_PASSWORD` | `.env` (gitignored) | NO | |

---

## Why the Supabase anon key is in dashboard/index.html

`dashboard/index.html` is a local-only nginx-served dashboard (port 3001, no internet exposure).
The Supabase **anon** key is Supabase's public client key — it is intended to be present in
browser-side code. Access is controlled by Row Level Security (RLS) policies on each table.
The dashboard only reads from: `heartbeat_log`, `triage_log`, `workflow_runs`, `claude_api_costs`.

**The SERVICE_ROLE key is never embedded in HTML.** It lives only in `.env` and is accessed
server-side via `process.env.SUPABASE_SERVICE_ROLE_KEY`.

---

## .gitignore coverage

The following patterns are protected at the repo root (`.gitignore`):

- `.env` and all `.env.*` variants (except `.env.example`)
- `telegram-bot/.env`, `telegram-bot/.env.railway`
- `dashboard/*.png` (generated binary assets)
- `dashboard/render-images.html` (browser-side canvas renderer, not production code)
- `.harness/scan-results/` (may contain real secret values from scanned repos)
- `.harness/telegram-inbox/*.json` (live Telegram messages)
- `app/data/`, `app/logs/`, `app/workspaces/` (runtime data)
- `*.key`, `*.pem`, `id_rsa`, `id_ed25519` (SSH/TLS keys)
- `secrets.json`, `credentials.json`, `service-account*.json` (cloud credentials)

---

## n8n workflows

n8n workflows (port 5678) contain embedded credentials in their Code nodes
(Supabase service role key, Telegram token, Linear API key).

- n8n workflow JSON is stored only in the n8n SQLite database on the Mac Mini
- Workflow JSON is NOT exported to this repository
- Do not use the n8n "Export workflow" feature and commit the result

---

## If you find a leaked credential

1. Rotate the key immediately (do not wait)
2. Remove it from git history: `git filter-branch` or `git filter-repo`
3. Force-push the cleaned history
4. Create a Linear issue tagged `[SECURITY]` with the finding
5. Check if the key was ever pushed to a remote — if yes, assume it is compromised

---

## Scanning

The `app/server/scanner.py` `SecurityScanner` class runs regex-based secret detection across
all portfolio repos. False positives are managed via `_PLACEHOLDER_RE` allowlist (RA-654).

To run a manual scan:
```bash
python3 -c "
from pathlib import Path
from app.server.scanner import SecurityScanner
findings = SecurityScanner().scan(Path('.'))
critical = [f for f in findings if f.severity == 'critical']
print(f'{len(critical)} critical findings')
for f in critical[:10]:
    print(f'  {f.file_path}:{f.line_number} — {f.description}')
"
```
