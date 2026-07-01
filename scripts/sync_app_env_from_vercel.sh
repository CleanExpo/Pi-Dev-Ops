#!/usr/bin/env bash
# sync_app_env_from_vercel.sh — build app/.env.local from dashboard/.env.local (Vercel pull).
#
# Prerequisites:
#   cd dashboard && vercel env pull .env.local --environment=production --yes
#
# Merges OPENROUTER_API_KEY from ~/.hermes/.env when present (Railway-only var).
# Never prints secret values. Writes app/.env.local with mode 600.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DASHBOARD_ENV="${ROOT}/dashboard/.env.local"
APP_ENV="${ROOT}/app/.env.local"
HERMES_ENV="${HOME}/.hermes/.env"

if [[ ! -f "${DASHBOARD_ENV}" ]]; then
  echo "Missing ${DASHBOARD_ENV}. Run: cd dashboard && vercel env pull .env.local --environment=production --yes" >&2
  exit 1
fi

_get() {
  local key="$1" file="$2"
  grep -E "^${key}=" "${file}" 2>/dev/null | head -1 | cut -d= -f2- || true
}

BACKEND_KEYS=(
  ANALYSIS_MODE
  ANTHROPIC_API_KEY
  GITHUB_TOKEN
  LINEAR_API_KEY
  NEXT_PUBLIC_SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  TELEGRAM_BOT_TOKEN
)

{
  echo "# Auto-synced — DO NOT COMMIT. Source: dashboard/.env.local (Vercel production)"
  echo "# Regenerate: bash scripts/sync_app_env_from_vercel.sh"
  echo ""
  for key in "${BACKEND_KEYS[@]}"; do
    val="$(_get "${key}" "${DASHBOARD_ENV}")"
    if [[ -n "${val}" ]]; then
      printf '%s=%s\n' "${key}" "${val}"
    fi
  done
  tao_pw="$(_get DASHBOARD_PASSWORD "${DASHBOARD_ENV}")"
  if [[ -z "${tao_pw}" ]]; then
    tao_pw="$(_get PI_CEO_PASSWORD "${DASHBOARD_ENV}")"
  fi
  if [[ -n "${tao_pw}" ]]; then
    printf 'TAO_PASSWORD=%s\n' "${tao_pw}"
  fi
  echo "GITHUB_REPO=CleanExpo/Pi-Dev-Ops"
  echo "TAO_HOST=127.0.0.1"
  echo "TAO_PORT=7777"
  echo "TAO_MACHINE_SHIP_MODE=0"
  if [[ -f "${HERMES_ENV}" ]]; then
    or_key="$(_get OPENROUTER_API_KEY "${HERMES_ENV}")"
    if [[ -n "${or_key}" ]]; then
      printf 'OPENROUTER_API_KEY=%s\n' "${or_key}"
    fi
  fi
} > "${APP_ENV}"

chmod 600 "${APP_ENV}"
echo "Wrote ${APP_ENV} ($(grep -cE '^[A-Z]' "${APP_ENV}" || echo 0) vars, values not shown)"
