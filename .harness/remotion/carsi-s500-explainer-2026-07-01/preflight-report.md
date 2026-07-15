# Preflight — carsi-s500-explainer-2026-07-01

## Brief gate: PASS
brand=carsi (resolves; BrandConfig exists) · composition=Explainer (v1) · channel=youtube · aspect=1080×1920 · duration=60s · topic is a specific claim (not a category) · audience confirmed · voiceoverScript pre-written (Drive-verified) → storyteller may skip re-invention.

## Content integrity: PASS
- [x] Facts verified against the real IICRC S500 source in Google Drive.
- [x] Original wording; no copyrighted manual prose reproduced.
- [x] Single CTA; single brand (CARSI).

## remotion-professionalism (provisional, script-only — render not yet produced)
| Criterion | Score (1–5) | Note |
|---|---|---|
| Hook clarity | 4 | "Not all water damage is equal" lands the stakes in 5s |
| Audience fit | 5 | IICRC techs — exact ICP |
| Visual hierarchy | — | pending render (designer wave) |
| Typography/legibility | — | pending render vs carsi.design.md |
| Motion restraint | — | pending render |
| Voice pacing | — | **BLOCKED — no voiceover (ElevenLabs key absent)** |
| CTA clarity | 5 | singular, branded |
| Brand consistency | — | pending render vs BrandConfig |
| Evidence/proof quality | 5 | every claim traces to S500 source |
| Overall polish | — | pending render |

> Rule: any score <3 blocks production render. No score is <3 yet, but **Voice pacing is unscoreable until audio exists** — so the audio/sync gate is NOT green.

## BLOCKERS to "100% green for the CARSI brand"
1. **ELEVENLABS_API_KEY absent** → no voiceover → audio + sync (`audio-fit.ts`) cannot run → audio/timing/sync QA cannot pass. **REQUIRED from founder.**
2. **remotion-studio/node_modules absent** → `npm install` (in remotion-studio) needed before any render.
3. **Topic-specific composition** → `one-shot.ts` is a generic brand template; needs `remotion-screen-storyteller` + `remotion-composition-builder` (this script.md is the storyteller input).

## Mode: DRY-RUN. Publish: BLOCKED (no-auto-publish; founder sign-off + CARSI publish target).
