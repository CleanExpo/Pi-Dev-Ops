#!/usr/bin/env bash
set -euo pipefail
cd /Users/phillmcgurk/Pi-Dev-Ops/remotion-studio
PATH="$PWD/.harness/bin:$PATH" npx tsx render/render.ts --comp=Explainer --out=output/ra-moisture-map-showcase-20260624.mp4 --jobId=ra-moisture-map-showcase-20260624 --skipTts=true --skipValidate=true --props="$(cat .harness/remotion/ra-moisture-map-showcase-20260624/props.json)"
