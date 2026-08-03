#!/usr/bin/env bash
set -euo pipefail
cd /Users/phillmcgurk/Pi-Dev-Ops/remotion-studio
npx tsx render/render.ts --comp=Explainer --out=output/ra-facebook-accidental-salesman-20260624.mp4 --jobId=ra-facebook-accidental-salesman-20260624 --skipTts=true --props='$(cat .harness/remotion/ra-facebook-accidental-salesman-20260624/props.json)'
