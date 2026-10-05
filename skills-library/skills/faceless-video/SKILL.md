---
name: faceless-video
description: Produce a faceless YouTube-style video (hand-drawn doodle / simple-illustration channels like Zen, Nick Invest) end-to-end from a single topic. ASKS FACT-vs-STORY mode first (non-fiction educational vs fiction storytelling) and branches the whole run — built to serve multiple clients/channels, not one fixed format. Reverse-engineers a proven reference video's script format, writes a new script in that format, generates an ElevenLabs voiceover with timestamps, creates one styled Artlist (AI Toolkit) image per timestamp, and stitches everything with FFmpeg — fully automated, no human recording. Use when the user says "faceless video", "/faceless-video", "doodle video", "make a YouTube short/long-form in the Zen style", or wants an organic faceless-channel content piece. Composes with video-distribution-strategist (channel/launch) and video-director (when motion/edit polish is wanted instead of stills).
---

# Faceless Video Pipeline

Build a faceless-channel video as a deterministic 4-stage pipeline. Source teardown:
`~/2nd Brain/2nd Brain/Wiki/research-faceless-youtube-claude-code-pipeline-2026-06-26.md`.

## Hard rules (platform risk + quality)
1. **Voice = ElevenLabs Voice Artist** (Phill's paid plan), NOT a human recording. The source video's "AI voice gets you banned" fear is WRONG — see the YouTube disclosure policy in `Sources/youtube-synthetic-content-disclosure-policy-2026-06-26.md`. The real rule: YouTube's altered/synthetic disclosure is required for AI **music**, a synthetic voice that is NOT the creator's own clone, or realistic AI of real people/places/events — and is **NOT** required for animation/doodles. Disclosure is costless (no audience/monetization hit), so **default to YES** whenever the video has AI music or a non-self synthetic voice (our pipeline always does). Set it in YouTube Studio → Attributes → "AI use" → Yes. Set "Made for kids" = Yes only for child-directed content (STORY/childcare).
2. **One style token, every image.** Lock a single style description up front; every generated image carries it verbatim so the channel stays visually consistent.
3. **Mode-appropriate authority** (see Stage 0 switch). **FACT/non-fiction:** cite real studies / dates / stats, research before writing, accuracy-gate the claims. **STORY/fiction:** invented narrative; authority is emotional resonance, not facts; gate for age- and brand-appropriateness instead (e.g. childcare = gentle, safe, age-suitable). NEVER present fiction as fact or invent "facts" in fact mode.
4. **Stills + voiceover, not motion graphics.** This is the doodle-channel format. If the user wants animation/edit polish, hand off to `video-director` instead.

## Substrate — IMPORTANT distinction
The source video uses **Higgsfield** (Claude Code MCP). **We do NOT use Higgsfield.** Phill's image platform is **Artlist** (`artlist.io`, AI Toolkit), driven in-browser via `browser-harness`. NB: "artist.io" is a typo for artlist.io.
- **Image gen (primary): Artlist AI Toolkit** at `toolkit.artlist.io/image-video-generator?mode=image` (model Nano Banana 2, 16:9 / 2K). Dogfood-proven mechanics in Stage 3.
- **Image gen (fallback): `mcp__margot__image_generate`** (also Nano Banana 2) — unattended test runs only. Never Higgsfield.
- **Voiceover: ElevenLabs** TTS via REST API. Key + default voice in `~/.hermes/.env` (`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`) — resolve programmatically, never paste. No human recording.
- Transcript pull: `yt-dlp`. Timestamps: ElevenLabs alignment (primary) or `whisper-cli` (fallback). Stitch: `ffmpeg`.

## Working folder
Create `~/faceless-video/<topic-slug>/` and keep every artifact there: `reference-format.md`, `script.md`, `voiceover.mp3`, `transcript.json`, `images/NN.png`, `final.mp4`.

## Stage 0 — MODE SWITCH (ASK FIRST, before anything else)
The engine serves opposite jobs across clients/applications, so the FIRST question every run is:
> **"Is this a FACT (non-fiction) or STORY (fiction) script?"**
Record `mode` in the working folder (`mode.txt`). It branches the whole run:

| | **FACT (non-fiction)** | **STORY (fiction)** |
|---|---|---|
| Use case | educational product, explainers, "did-you-know" | childcare tales, parables, bedtime/brand stories |
| Reference lane | hook + 3-pillar body + payoff | character → flaw → journey → lesson → resolution |
| Authority | researched real studies/stats/dates; **accuracy-gate** | emotional resonance; **age/brand-appropriateness gate** |
| Hard rule | never invent facts | never present fiction as fact |
| YouTube disclosure | AI-use = Yes (AI music/voice present) | AI-use = Yes + **Made for kids = Yes** (child-directed) |

If the caller already implies the mode (e.g. "a childcare story for my wife" → STORY; "explain X for my product" → FACT), confirm it in one line rather than re-asking. Default reference handling, script template, and gating all follow from this switch.

## Stage 0b — Style token (once per channel, then reuse)
Ask the user for 3–5 reference screenshots of the target visual style. Prompt the analysis:
> "Analyse this image's visual style for an AI image generator. Give (1) a short positive style description I can paste as a prompt, (2) a list of negative prompts to prevent drift toward polished/realistic output. Focus on style only, not subject matter."
Save the result as `style-token.md` in the channel root (reused across all videos for that channel).

## Stage 1 — Script (branches on Stage 0 mode)
1. Ask for the **topic** and a **proven reference video URL** *in the chosen mode's lane* (a fact channel for FACT, a story channel for STORY — don't cross lanes).
2. Pull the reference transcript: `yt-dlp --write-auto-sub --sub-lang en --skip-download --sub-format vtt -o 'ref-%(id)s.%(ext)s' '<URL>'`. Clean the `.vtt` (strip timestamps/tags, dedupe rolling auto-sub lines).
3. Decompose into a reusable template, **per mode**:
   - **FACT:** hook (the micro-beats), intro/promise, the 3-pillar body, transition sentences, total length.
   - **STORY:** protagonist + one shared flaw, the ache, inciting incident, journey, a SHOWN demonstration (not told), one quotable wisdom line, internal realisation, carry-forward close.
   Save as `reference-format.md`.
4. Write a NEW script on the topic in that template. **FACT:** first run the `source-ingest` skill to pull credible Tier 1–2 data into the vault `Sources/` library, then write the script citing only those stored sources and accuracy-gate every claim against them. **STORY:** invent freely, age/brand-gate. Output a CLEAN script (no scene directions) to `script.md`.
5. Confirm the script with the user before generating the voiceover.

## Stage 2 — Voiceover + timestamps (ElevenLabs, automated)
1. Generate the voiceover from `script.md` via the ElevenLabs **with-timestamps** endpoint (returns audio + character alignment in one call):
   `curl -s -X POST "https://api.elevenlabs.io/v1/text-to-speech/$ELEVENLABS_VOICE_ID/with-timestamps" -H "xi-api-key: $ELEVENLABS_API_KEY" -H "content-type: application/json" -d '{"text":"<script>","model_id":"eleven_multilingual_v2"}'` → save base64 audio to `voiceover.mp3` and the alignment to `transcript.json`.
2. Derive per-phrase/sentence timestamp segments from the alignment — each segment becomes one image beat. (Fallback if alignment is unusable: `whisper-cli -f voiceover.wav -ml 1 --output-json -of transcript` after `ffmpeg -i voiceover.mp3 voiceover.wav`.)
3. **Voice is per-channel/client**, not fixed — pick the ElevenLabs voice that fits the mode/brand (e.g. warm, gentle storyteller for childcare fiction; clear, authoritative voice for an educational fact product). Pass that `voice_id` instead of the default in `ELEVENLABS_VOICE_ID`. Browse the user's ElevenLabs voice library when choosing.
4. No human pause — Stage 2 runs unattended.

## Stage 3 — One image per timestamp (Artlist AI Toolkit, browser-proven)
Per beat: scene prompt + **locked style token verbatim**. Drive Artlist via `browser-harness` (needs Phill's Chrome logged in; Way-1 remote-debugging enabled). Hard-won mechanics:
1. Open `toolkit.artlist.io/image-video-generator?mode=image`. Prompt is a `[contenteditable=true]` div; the **Generate** button matches innerText `Generate`. Default settings are already 16:9 / 2K / 1 image (good).
2. Per image: snapshot existing generated UUIDs → click box, `document.execCommand('selectAll')`, `type_text(prompt)` → click Generate → poll until loader text (`on its way|Almost ready|Generating`) clears AND a new UUID appears.
3. Result lives at `ai-toolkit-generations.imgix.net/...png?...&s=<sig>`. Extract UUID with the GENERIC regex `[0-9a-f]{8}-[0-9a-f]{4}-...{12}\.png` (filename prefix varies: `image-<uuid>` OR `-t-e-x-t_-t-o_-i-m-a-g-e-<uuid>`). Download the **EXACT src** — rewriting any imgix param (e.g. `w=`) breaks the signature → 403.
4. **Go ONE AT A TIME.** Rapid bursts queue/throttle and the grid view virtualizes the DOM, both of which break new-UUID detection. If a generation completes after the poll window, salvage it from the grid (download distinct unmapped UUIDs, montage, map visually).
Fallback (unattended only): `mcp__margot__image_generate` — saves `<save_as>.jpg`, account for the extension.

## Stage 4 — Stitch
Build an FFmpeg concat that holds each image for `(next_start - this_start)` seconds and muxes the voiceover:
1. Generate a concat list with per-image durations from the timestamps.
2. `ffmpeg -f concat -safe 0 -i list.txt -i voiceover.wav -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest final.mp4`
3. Recommend 2K source images for real uploads (low-res only for test runs).

## Stage 5 — Finalise (for a real upload, not test runs)
Turn the raw stitch into a finished deliverable:
- **1080p** — render the concat scaled/padded to `1920:1080` (white pad blends the sketchbook bg), `crf 19`.
- **Fades** — `fade=t=in:st=0:d=0.6:color=white` and `fade=t=out` over the last ~0.8s. Keep **hard cuts on the beats** between images (on-style — do NOT crossfade).
- **Music bed** — generate a calm track via Artlist **AI Music** (`toolkit.artlist.io/music-generator?mode=music`, Lyria 3; same browser flow as images, result is a signed `.wav` at `cms-toolkit-artifacts.artlist.io/...music-<uuid>` — download EXACT src). Mix UNDER the VO: `volume≈0.13` (~−18 dB), `afade` in 1.5s / out ~1.8s, `amix=inputs=2:normalize=0`. Verify with `volumedetect`: overall peak < 0 dB (no clip), music mean ~15+ dB below VO.

## Output
`final-1080p-music.mp4` (the deliverable) + a reusable `style-token.md`. Report the path and per-stage artifacts. For publishing/channel strategy hand off to `video-distribution-strategist`; remember the synthetic-content disclosure on upload.
