#!/usr/bin/env bash
# Render the CARSI S500 Explainer once prerequisites are met.
# Prereqs (currently BLOCKING):
#   1. export ELEVENLABS_API_KEY=...   (single-voice voiceover + audio-fit sync)
#   2. cd remotion-studio && npm install   (node_modules absent)
#   3. A topic-specific CARSI S500 vertical composition authored by
#      remotion-composition-builder (one-shot.ts is a GENERIC brand template — do not use it for this).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../../remotion-studio"

# Dry-run first (orchestrator hard rule). No upload/publish.
npx tsx render/render.ts \
  --brand=carsi \
  --composition=Explainer \
  --aspect=1080x1920 \
  --durationSec=60 \
  --script="../.harness/remotion/carsi-s500-explainer-2026-07-01/script.md" \
  --out="./.remotion-renders/carsi-s500-explainer-2026-07-01.mp4" \
  --dry-run

# Then QA: remotion-editing (timing/sync) -> remotion-professionalism (rubric) -> remotion-production (evidence),
# then /judge /spm /storm. Only after all green + founder sign-off: schedule via marketing-orchestrator.
