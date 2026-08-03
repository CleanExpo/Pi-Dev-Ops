# preflight-report.md — carsi-restoration-method-social-2026-07-01

Mode: **dry-run** (no MP4 rendered). Governed `/remotion-video` path.

## Brief gate — LOCKED ✅
| Field | Value | Status |
|---|---|---|
| brand | `carsi` (authority layer; house style only) | ✅ resolves in `packages/brand-config/src/brands/carsi.ts` |
| composition | SocialAd → **Explainer** (v1 fallback, social 9:16 framing) | ✅ acknowledged |
| channel | instagram (+ tiktok / yt-shorts identical cut) | ✅ |
| aspectRatio | 1080x1920 | ✅ |
| durationSec | 30 | ✅ (≤3-wave plan) |
| topic | specific claim (dry vs dry-to-S500-standard) | ✅ not a category |
| audience | restoration trainees/inspectors + homeowner hook | ✅ (founder may flip to homeowner-primary) |

## Rails — enforced in script ✅
- Single voice only: `EXAVITQu4vr4xnSDxMaL`, en-AU narration. ✅
- No on-screen product/brand names — cross-links are role-based CTAs. ✅
- On-screen standard = `IICRC S500` only (industry standard, not one of the four products). ✅
- No verbatim IICRC prose (method paraphrased). ✅
- No personal/customer names (Daniel = seed only). ✅
- No new vendors/accounts. ✅

## Blockers before a production render ⛔
1. **props.json not yet authored** — `remotion-composition-builder` (wave 3) must produce the brand+storyboard props the Explainer composition + `render.ts` require. `render-command.sh` fails closed until it exists.
2. **ElevenLabs creds** — present in `Synthex/.env.local`; verify `ELEVENLABS_API_KEY` resolves at render time (the render synthesises VO before compositing).

## Advisory (not blocking) ⚠
- `carsi.ts` is a STUB ("refined by remotion-brand-research"). Recommend running `remotion-brand-research` + `remotion-brand-codify` to refine palette/voice/logo from CARSI's live sources before the final render, so the house style is real, not placeholder.
- Confirm the four method beats against the current IICRC S500 text (paraphrase only) before publishing.

## Artifacts written
- `script.md` — VO + 5 scene beats + funnel map + copyright rails
- `production-packet.json` — the governed job spec
- `render-command.sh` — dry-run scaffold (fails closed w/o props.json)
- `.research/wave-plans/<job>.json` — 3-wave dispatch plan

## RENDER OUTCOME — 16:9 master ✅ (2026-07-01)
- Output: `.remotion-renders/carsi-restoration-method-social-2026-07-01-16x9.mp4` — 4.0 MB, **1920x1080 h264 + aac, 32.2s**.
- Single voice: all 5 scenes synthesised via ElevenLabs `EXAVITQu4vr4xnSDxMaL` (en-AU). Post-render gate PASSED: `video=32.167s audio=32.192s delta=25ms ✓` (audio-fit extended the CTA scene so no VO is clipped — final ~32s vs planned 30s).
- **9:16 social master still PENDING** — Explainer composition is 1920x1080 only; needs a registered `1080x1920` variant (+ CARSI fonts) before the vertical cut-downs (reels/tiktok/shorts) in `distribution-synthex.json` can be produced.
- MP4 is NOT committed (job artifact).

### ffprobe env fix (needed to re-render on this Mac)
No system ffmpeg/brew. Remotion bundles `ffprobe`/`ffmpeg` in `node_modules/@remotion/compositor-darwin-arm64/` but they dynamically link `libav*.dylib` there. macOS SIP strips `DYLD_*` across `execFileSync`, so `render/audio-fit.ts`'s bare `ffprobe` call fails unless the loader finds the dylibs via **cwd**. Fix before rendering:
```bash
cd remotion-studio
for l in node_modules/@remotion/compositor-darwin-arm64/*.dylib; do ln -sf "$l" "./$(basename "$l")"; done
export PATH="$PWD/node_modules/@remotion/compositor-darwin-arm64:$PATH"
# ... run render ... then: rm -f *.dylib
```

## Next step to actually render
Run waves 1–3 (brand-research advisory → storyteller → designer → composition-builder), then execute `render-command.sh`. That is the point where an MP4 is produced — **explicit go required** (governed path starts dry-run).
