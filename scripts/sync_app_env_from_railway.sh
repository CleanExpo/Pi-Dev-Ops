#!/usr/bin/env bash
# sync_app_env_from_railway.sh — refresh app/.env.local secrets from Railway production.
#
# Use when local Linear/GitHub keys are stale (401) but Railway prod is healthy.
# Never prints secret values.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ENV="${ROOT}/app/.env.local"

if ! command -v railway >/dev/null 2>&1; then
  echo "railway CLI not found" >&2
  exit 1
fi

cd "${ROOT}"

python3 <<'PY'
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
APP_ENV = ROOT / "app" / ".env.local"

SYNC_KEYS = (
    "LINEAR_API_KEY",
    "GITHUB_TOKEN",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
)

proc = subprocess.run(
    ["railway", "variables", "--kv"],
    capture_output=True,
    text=True,
    check=False,
)
if proc.returncode != 0:
    print((proc.stderr or proc.stdout or "railway variables failed").strip(), file=sys.stderr)
    raise SystemExit(1)

remote: dict[str, str] = {}
for line in proc.stdout.splitlines():
    if "=" not in line:
        continue
    key, _, value = line.partition("=")
    key = key.strip()
    if key in SYNC_KEYS and value.strip():
        remote[key] = value.strip().strip('"').strip("'")

if "LINEAR_API_KEY" not in remote:
    print("LINEAR_API_KEY missing from Railway variables", file=sys.stderr)
    raise SystemExit(1)

if APP_ENV.is_file():
    text = APP_ENV.read_text(encoding="utf-8")
else:
    text = (
        "# Auto-synced — DO NOT COMMIT. Source: Railway production\n"
        "# Regenerate: bash scripts/sync_app_env_from_railway.sh\n\n"
    )

for key, value in remote.items():
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    line = f'{key}="{value}"'
    if pattern.search(text):
        text = pattern.sub(line, text, count=1)
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += line + "\n"

# Ensure machine-ship + local host defaults for standby
for key, value in (
    ("TAO_MACHINE_SHIP_MODE", "1"),
    ("GITHUB_REPO", "CleanExpo/Pi-Dev-Ops"),
    ("TAO_HOST", "127.0.0.1"),
    ("TAO_PORT", "7777"),
):
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    line = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(line, text, count=1)
    else:
        text += line + "\n"

APP_ENV.write_text(text, encoding="utf-8")
APP_ENV.chmod(0o600)
print(f"Wrote {APP_ENV} ({len(remote)} Railway secrets synced, values not shown)")
PY

# Validate Linear auth without printing the key
cd "${ROOT}/app"
op run --env-file=.env.local -- bash -c \
  'code=$(curl -s -o /dev/null -w "%{http_code}" -H "Content-Type: application/json" -H "Authorization: $LINEAR_API_KEY" -d "{\"query\":\"{ viewer { id } }\"}" https://api.linear.app/graphql); test "$code" = "200" || { echo "Linear API still returned HTTP $code after sync" >&2; exit 1; }'
echo "Linear API auth: OK"
