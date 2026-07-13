#!/usr/bin/env bash
# DRY-RUN scaffold — production render for job carsi-restoration-method-social-2026-07-01.
# Do NOT run until wave 3 (remotion-composition-builder) has written props.json.
# Never commit the resulting MP4.
set -euo pipefail

STUDIO=/Users/phillmcgurk/Pi-Dev-Ops/remotion-studio
JOB=carsi-restoration-method-social-2026-07-01
cd "$STUDIO"

# Single Synthex ElevenLabs voice creds come from the calling project's env (Synthex).
set -a
[ -f /Users/phillmcgurk/Synthex/.env.local ] && source /Users/phillmcgurk/Synthex/.env.local
set +a
: "${ELEVENLABS_API_KEY:?ELEVENLABS_API_KEY not set — source Synthex/.env.local}"

PROPS_FILE=".harness/remotion/$JOB/props.json"
if [ ! -f "$PROPS_FILE" ]; then
  echo "BLOCKED: $PROPS_FILE not found — run remotion-composition-builder (wave 3) first." >&2
  exit 1
fi

npx tsx render/render.ts \
  --comp=Explainer \
  --jobId="$JOB" \
  --out=".remotion-renders/$JOB.mp4" \
  --props="$(cat "$PROPS_FILE")"

echo "[render] done -> .remotion-renders/$JOB.mp4 (9:16, ~30s). Review before publishing. Do not commit the MP4."
