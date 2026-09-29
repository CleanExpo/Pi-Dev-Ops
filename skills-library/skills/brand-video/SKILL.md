---
name: brand-video
description: "Produce one or many consistent, on-brand faceless marketing videos from a topic: script, ElevenLabs voiceover with timestamps, one styled illustration per beat, ffmpeg stitch to 1080p, optional Unlisted YouTube upload. The look is a named style from styles.md (flat-line, hand-doodle, bold-kinetic, cinematic-photoreal, minimal-corporate, retro-print), so one command yields repeatable output per brand. The automated pipeline; distinct from faceless-video and video-director."
---

# brand-video — consistent styled faceless videos, on demand

Invoke as **`/brand-video`**. One command, many looks. Built from the validated
RestoreAssist run (9 videos shipped). Picks a **style** from `styles.md`, holds
everything else constant so output is consistent batch-to-batch and brand-to-brand.

## Inputs (ask only if missing; infer sensibly)
- **brand** — RestoreAssist / Synthex / DR / NRPG / CARSI / CCW / Unite, or a client. Sets claims + CTA + voice.
- **style** — a key from `styles.md` (default `flat-line`). This is the "look" / dropdown value.
- **topic(s)** — one angle, or a list for a batch (one video each, parallel).
- **voice** — `ELEVENLABS_VOICE_ID` (per-brand; from `~/.hermes/.env`). **CRITICAL: confirm the current value before generating — the user changes it.**
- **upload?** — default: render + stage only. Upload to YouTube Unlisted only when asked.

## Pipeline (per video — one slug folder each, never share a dir)
1. **Script** → `<slug>/script.md`: one clean VO paragraph, ~120–140 words, ~12–16 short sentences (one sentence = one visual beat = one image), problem→solution→CTA. Ground claims in the brand wiki; never invent features. End with the brand CTA line.
2. **Voiceover** → run the bundled tts.py (reads `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID` + `DIR`):
   `cd <workdir> && set -a && . ~/.hermes/.env && set +a && DIR=$PWD/<slug> python3 <skill>/pipeline/tts.py`
   Writes `<slug>/voiceover.mp3` + `<slug>/transcript.json` (beats). Note the beat count.
3. **Images** → one per beat, prompt = the chosen style's POSITIVE token + a concrete scene for that sentence + the style's NEGATIVE token, landscape 16:9, saved zero-padded `<slug>/images/01.png …`.
   - **Prod / headless (default):** `python3 <skill>/pipeline/image_gen.py "<prompt>" <out.png>` — Gemini `gemini-2.5-flash-image` ("Nano-Banana") over HTTPS, `GEMINI_API_KEY` from env. Works server-side; validated end-to-end. This is what app workers call (no local MCP needed).
   - **Interactive (optional):** `mcp__margot__image_generate` when running inside a Claude session; use slug-prefixed filenames to avoid parallel collisions (see [[parallel-agents-shared-output-collision]]).
4. **Stitch** → `python3 <skill>/pipeline/stitch.py <slug>` → `<slug>/final-1080p.mp4` (1920×1080@25, image timing from beats). Verify final duration ≈ voiceover duration.

## Batches & new looks
- **Batch:** dispatch one sub-agent per topic (parallel), each owning its slug dir. See the RestoreAssist run for the exact agent prompt shape.
- **Re-voice** (voice changed, same script/images): regenerate VO, rescale `list.txt` durations by `new_total/old_total`, re-stitch. (revoice pattern.)
- **Add a look:** append a block to `styles.md` (positive/negative token). That key immediately becomes a selectable style — this registry IS the dropdown's data source.

## Upload (YouTube, optional)
Browser file-upload is dead (host paths rejected). Use the YouTube Data API path documented in [[youtube-api-upload-restoreassist]]: Desktop OAuth client → token at `~/.hermes/yt-restoreassist-token.json` → `videos().insert` privacyStatus=unlisted, category 27, not-for-kids; guard on channel title; idempotent via `uploaded.json`. Requires YouTube Data API v3 enabled in the OAuth client's GCP project.

## Guardrails
- Claims must be real (brand wiki / product truth). Flat-illustration + synthetic voice → YouTube AI-disclosure usually "No" (confirm at upload; flip to Yes if AI music added).
- Keep one style per batch for consistency. Keep `SKILL.md` ≤200 lines per [[feedback-tight-code]].
- Reference implementation + assets: `/Users/phill-mac/restoreassist-videos/`.
