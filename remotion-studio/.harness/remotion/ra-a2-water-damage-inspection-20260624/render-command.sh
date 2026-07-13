#!/usr/bin/env bash
set -euo pipefail
cd /Users/phillmcgurk/Pi-Dev-Ops/remotion-studio
PATH="$PWD/.harness/bin:$PATH" npx tsx render/render.ts --comp=Explainer --out=output/ra-a2-water-damage-inspection-20260624.mp4 --jobId=ra-a2-water-damage-inspection-20260624 --skipTts=true --skipValidate=true --props="$(cat .harness/remotion/ra-a2-water-damage-inspection-20260624/props.json)"
