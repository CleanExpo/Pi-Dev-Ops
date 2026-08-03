#!/usr/bin/env bash
# Register the Telegram webhook. Replaces the unauthenticated GET /api/telegram handler
# deleted 2026-08-02 — see the note in dashboard/app/api/telegram/route.ts.
#
# The target URL is passed in explicitly and never derived from an inbound request, which is
# what made the old handler a channel-hijack primitive.
#
#   TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_SECRET=... \
#     scripts/register-telegram-webhook.sh https://pi-dev-ops.vercel.app
set -euo pipefail

BASE="${1:-}"
if [ -z "$BASE" ]; then
  echo "usage: $0 <https://app-origin>   (no trailing slash)" >&2
  exit 2
fi
case "$BASE" in
  https://*) ;;
  *) echo "refusing a non-https origin: $BASE" >&2; exit 2 ;;
esac

: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is not set}"
: "${TELEGRAM_WEBHOOK_SECRET:?TELEGRAM_WEBHOOK_SECRET is not set — registering without one leaves the POST handler unable to distinguish Telegram from anyone else}"

WEBHOOK_URL="$BASE/api/telegram"
echo "registering webhook -> $WEBHOOK_URL"

# --data via stdin so the secret never appears in the process list.
RESPONSE=$(printf '{"url":"%s","secret_token":"%s"}' "$WEBHOOK_URL" "$TELEGRAM_WEBHOOK_SECRET" \
  | curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
      -H "content-type: application/json" --data @-)

# Print Telegram's verdict without echoing what was sent.
echo "$RESPONSE" | grep -q '"ok":true' && echo "OK: webhook registered" || {
  echo "FAILED: $RESPONSE" >&2
  exit 1
}
