---
name: remotion-render-pipeline
description: Final step. Synthesises ElevenLabs voiceover for each scene, runs `npx tsx render/render.ts` to produce an MP4, validates duration / codec / resolution / size, uploads to Supabase storage, ships the result via Telegram, and opens a Linear ticket. Triggered after remotion-composition-builder reports ready. Failure modes (timeout, hang, type error) escalate to Linear.
automation: automatic
intents: render-video, ship-video, deliver-video
---

# remotion-render-pipeline

Turns the composition into a delivered MP4.

## Triggers

- `remotion-composition-builder` reports `ready: true`.
- User says "render it" / "ship it" with a known job.

## Inputs

- `jobId`
- `composition` — id matching `src/Root.tsx` (e.g. `Explainer`)
- `outputPath` — relative to `remotion-studio/output/`
- `props` — full input props (brand + storyboard + ...) as JSON
- `linear` — `{teamId, projectId}` for ticket routing

## Method

1. **Pre-flight typecheck** — `cd remotion-studio && npx tsc --noEmit`. On red, return to `remotion-composition-builder` with the error.
2. **Voiceover synthesis** — `render/voiceover.ts` writes per-scene MP3s into `public/audio/{jobId}/scene-N.mp3` (under `public/` so `staticFile()` resolves them). Uses cache key `sha1(voiceId|style|text)`. Skips if `ELEVENLABS_API_KEY` is missing — composition must still render with on-screen text only.
3. **Render** — `npx tsx render/render.ts --comp={composition} --out={outputPath} --props='{...}' --jobId={jobId}`. Wraps in 600s timeout; one retry on hang/crash.
4. **Validate** — file exists, duration ±0.5s of expected, codec `h264`, resolution matches composition, size <100MB.
5. **Deliver**:
   - Upload to Supabase bucket `remotion-renders` — signed URL, 90-day retention.
   - Telegram via `app.server.telegram_video.send_telegram_video()` (the shared util). If file >45MB, send the signed URL link instead of inline upload (Telegram cap is 50MB).
   - Open Linear ticket in `{teamId}/{projectId}` with: render URL, source brief, BrandConfig version (git sha of `src/brands/{slug}.ts`), composition file path.
6. **Status** — write summary to `.research/renders/{jobId}.json`.

## Output

```jsonc
{
  "jobId": "ra-nir-explainer-2026-04-28T15-30-00",
  "mp4Path": "remotion-studio/output/ra-nir-explainer-2026-04-28T15-30-00.mp4",
  "supabaseUrl": "https://<project>.supabase.co/storage/v1/object/sign/remotion-renders/...",
  "telegramSent": true,
  "linearIssue": "RA-2049",
  "validation": { "durationSec": 60.0, "codec": "h264", "resolution": "1920x1080", "sizeMB": 12.4 }
}
```

## Boundaries

- Never run the render with `tsc --noEmit` failing — wastes 2-5 minutes for a guaranteed bad output.
- Never auto-merge the source PR (composition + brand changes) before render verification passes.
- Never upload renders with `[DRAFT]` baked in to the brand bucket — drafts go to `remotion-drafts`.

## Failure escalation

- Timeout / hang → kill, retry once → if second failure, open Linear with `priority: 2`, attach stderr.
- Validation fail (wrong duration / codec) → Linear `priority: 3` with diff vs expected.
- Telegram fail → fall back to `send_telegram_document()` with `.mp4` as attachment.

## Reused

- [`render/render.ts`](/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/remotion-studio/render/render.ts)
- [`render/voiceover.ts`](/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/remotion-studio/render/voiceover.ts)
- `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/app/server/telegram_video.py` (shared util)
- `.harness/projects.json` for Linear team/project resolution

## Per-project API keys

This skill is invoked **from inside the calling project** (Synthex, Pi-SEO, RestoreAssist, anywhere). Each project supplies its own keys via its own `.env` / `.env.local`. The skill never reads keys from Pi-Dev-Ops.

Required-or-warned env at render time:
- `ELEVENLABS_API_KEY` — voiceover synthesis. Missing = silent render with on-screen text only (warning logged, render continues).
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — Telegram delivery. Missing = skip Telegram step (the MP4 still lands on disk + Supabase if configured).
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` — signed-URL upload. Missing = skip Supabase step.
- `LINEAR_API_KEY` — ticket creation. Missing = skip Linear step.
- `REMOTION_LICENSE_KEY` — required for any commercial render under Remotion's fair-source licence.

Invocation pattern from a project shell:
```bash
cd ~/Pi-CEO/Synthex
source .env.local                     # project's own keys
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/remotion-studio
npx tsx render/render.ts \
  --comp=Explainer \
  --out=$OLDPWD/.remotion-renders/synthex-launch.mp4 \
  --jobId=synthex-launch-$(date +%s) \
  --props='{"brand":"synthex","hookSec":8,"ctaSec":8,"storyboard":[...]}'
```

Or invoke through the Pi-Dev-Ops orchestrator API which inherits the calling project's env at session-spawn time.

Output convention: write MP4 into `<calling-project>/.remotion-renders/` (gitignored) by default — keeps each project's artifacts in its own tree. Override with `--out=...`.
