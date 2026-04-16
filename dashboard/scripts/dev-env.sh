#!/usr/bin/env bash
# dev-env.sh — loads .env.local, auto-resolves 1Password refs, falls back to dev defaults.
#
# Defence-in-depth against the "unresolved op:// ref blocks local dev login" bug:
#   1. If `.env.local` exists, source it.
#   2. If any known secret is still an `op://` ref, try the 1Password CLI.
#   3. If `op` isn't installed/signed-in, substitute a dev default so `npm run dev`
#      never silently fails with "Invalid password".
set -e

cd "$(dirname "$0")/.."

# Optional .env.local handling
if [ -f .env.local ]; then
  set -a
  # shellcheck disable=SC1091
  source .env.local
  set +a
fi

# Detect unresolved 1Password refs and attempt resolution
has_op_refs=false
for var in DASHBOARD_PASSWORD PI_CEO_PASSWORD ANTHROPIC_API_KEY GITHUB_TOKEN TELEGRAM_BOT_TOKEN; do
  val="${!var:-}"
  if [[ "$val" == op://* ]]; then
    has_op_refs=true
    break
  fi
done

if [ "$has_op_refs" = true ]; then
  if command -v op &>/dev/null && op whoami &>/dev/null; then
    echo "[dev-env] Found unresolved op:// refs. Resolving via 1Password CLI..."
    exec op run --env-file=.env.local -- next dev
  else
    echo "[dev-env] Unresolved op:// refs in .env.local and 'op' CLI not available/signed-in."
    echo "[dev-env] Falling back to dev defaults. Login password: 'dev'"
    [[ "${DASHBOARD_PASSWORD:-}" == op://* ]] && export DASHBOARD_PASSWORD=dev
    [[ "${PI_CEO_PASSWORD:-}" == op://* ]] && export PI_CEO_PASSWORD=dev
  fi
fi

exec next dev
