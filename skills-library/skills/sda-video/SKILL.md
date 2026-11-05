---
name: sda-video
description: The SDA short-form video production chain, choreographed and timed as one run. Margot presents (HeyGen avatar driven by her own ElevenLabs voice), Blender renders the 3D inserts, Claude edits, the transitions skills join the beats, Artlist supplies music and sound effects, and the SDA evidence gate decides release. Use for any Margot or brand short-form video, the daily 10-video batch, or when asked to "use the SDA skill".
---

# SDA video: one choreographed run

Founder rule, 31/10/2026: "SDA Skill uses blender for 3d rendering, claude for additional video
editing, you also have transitions skills, and artlist for background sounds and music all
choreographed and timed as a Skill." This file is that skill. Do not swap a stage for something else.

## The chain (in this order, every video)

| Step | Stage | Tool | Output |
|---|---|---|---|
| 1 | Script and timing sheet | Claude (nexus-copywriter rules) | `timing.json` |
| 2 | Margot's voice | ElevenLabs voice "Margot - Bright, friendly and upbeat", ID `tAtHhBlA3E0eKZJKNSKE` (pinned in Synthex `packages/brand-config/src/brands/*.ts` and `tests/unit/brand-config/product-voice.test.ts`); call it through the ElevenLabs connector, no key file needed | `voice.mp3` with word timestamps |
| 3 | Margot on camera | HeyGen avatar, audio-driven from step 2 (skill `heygen-director`) | `margot.mp4` |
| 4 | 3D inserts | Blender, headless: `scripts/blender_title.py` | `insert-N.mp4` |
| 5 | Edit | Claude through skills `video-use` and `video-editor` | rough cut |
| 6 | Transitions | skill `remotion-motion-language` (Remotion) or HyperFrames | joined cut |
| 7 | Music and sound effects | skill `artlist-mcp` (licensed bed plus SFX on real on-screen actions) | `music.wav`, `sfx/` |
| 8 | Mix | skill `video-sound-designer`: voice on top, music low, about -16 LUFS | final `.mp4` 1080x1920 |
| 9 | Gate | SDA evidence gate (below) | PASS or HOLD |

Never use a voice other than Margot's ElevenLabs voice. A clip made with any other voice is held,
not shipped.

## Timing sheet (the choreography)

Write `timing.json` before anything renders. Every stage reads it, so cuts, inserts, transitions
and sound hits land on the same frame.

```json
{"fps": 30, "length_s": 30, "beats": [
  {"t": 0.0, "dur": 2.0, "kind": "hook", "source": "margot", "line": "..."},
  {"t": 2.0, "dur": 3.0, "kind": "insert", "source": "blender", "text": "One card. | Every link."},
  {"t": 5.0, "dur": 0.4, "kind": "transition", "style": "push"},
  {"t": 5.0, "dur": 0.1, "kind": "sfx", "cue": "whoosh"}
]}
```

Rules: hold shots 3 to 5 seconds (no rapid cuts); full-frame type 1 second max unless it is a 3D
insert; the logo is the approved file composited in the edit, never generated; voice timestamps
from step 2 set the beat times, not the other way round.

## Every shot shows what Margot is saying (founder rule, 01/11/2026)

Phill: "The images are getting repetitive and not actually representive of the actual discussion
point". Cause: the old edit dealt a fixed image list along the timeline and wrapped round when it ran
out (`body[k % len(body)]`), so pictures repeated and landed on unrelated lines. Never lay out
footage by count or even spacing again.

- Write a beat map per video: `(trigger words, asset, what it shows)`. The shot starts on the first
  spoken occurrence of its trigger (from the step 2 word timestamps) and must be on screen while
  those words are said. Pick the picture for that line, not for the brand in general.
- No asset twice in one video. Across a batch a still or clip appears in at most 2 videos (the
  product's own footage at most 3). Holds 3 to 5 s. Footage at least 75% of runtime, Margot alone
  10 to 28%, measured on what renders (union of shot windows, never a plain sum of durations).
- Landscape stills are cut to 1080x1920 around the subject (a focus point per image), never a
  blind centre crop: a centre cut of a two-person scene shows the wall between them.
- Gate: `beat_check.py` beside the batch (reference: `~/session-handoffs/shortform-engine/jobs/
  batch-2026-11-01/beats.py` and `beat_check.py`) prints each shot with the words spoken under it
  and exits 1 on any repeat, off-line shot, hold or share failure. It must pass before rendering,
  and it was proven to fail on the old layout (7 failures, one café image in 5 videos).
- Then look at a frame of every shot against its line before anything goes to Phill.

## Starting point: the gold batch (founder Keep, 02/11/2026)

Phill kept all 10 of batch 1 round 5: "This is the new and updated starting point now for short
video content to start working from.. Continue learning, testing and updating from this point".

- The bar is frozen at `~/session-handoffs/shortform-engine/gold/2026-11-02-batch1-r5/`: the 10
  finals, their plans, the method scripts (beat map, gate, layout, post, QA) and the QA results,
  with a SHA-256 for every file in `MANIFEST.json`. Never edit it; check the hashes before relying
  on it.
- Every new batch starts from that method, not from an older job or a blank template. Copy
  `method/` into the new job and change only what the new scripts need.
- A new video is finished only when it matches or beats its gold counterpart side by side (same
  brand: hook, shots on the words, holds, logo, captions, sound), and every gate above passes.
  Below that it is a preview.
- The bar only moves up. A video Phill rates higher replaces its counterpart in a new dated gold
  folder; the old one stays as history. Every correction he makes is a change to this file the
  same day.

## Blender insert (step 4)

```bash
~/Applications/Blender.app/Contents/MacOS/Blender -b --python \
  ~/.claude/skills/sda-video/scripts/blender_title.py -- \
  --text "One card. | Every link." --hex 0F2742 --accent F26B1D --seconds 3 --out insert-1.mp4
```

Blender 4.5 LTS lives at `~/Applications/Blender.app` on the MacBook (not `/Applications`). The
Mini has Blender 5.2.2 LTS at `/Applications/Blender.app` (checked 01/11/2026), so inserts can
render there too. `|` splits lines. Text is fitted to 80% of frame width. Use each brand's own
colours. The script is `scripts/blender_title.py` in this skill. Its default frame is 2160×3840.
Pass `--width 2160 --height 2160` for a square insert, or `--width 3840 --height 2160` for
widescreen. Do not render the insert at 1080 and scale it up. Look at a frame of every insert
before it goes into the cut.

## Gate (step 9)

```bash
python3 ~/.claude/skills/visual-qa/scripts/sda_evidence_gate.py <dir>/SDA_EVIDENCE_MANIFEST.json --release
```

Release mode needs the independent and human reviews recorded in the manifest. HOLD means not
done. Phill approves every video before it posts; nothing posts without him.

## Learning loop

Every correction Phill makes to a video goes into the video job's notes and becomes a change to
this file, the timing defaults or the brand brief, the same day. If he repeats a complaint, the
rule here is wrong: fix it here.

## Founder rules, 05/11/2026 (hard-coded — do not soft-pedal)

Phill watched the live Synthex marketing film and the Living Business Card openers and called
them not good enough. These rules are now part of the SDA chain. Every correction that day is
locked here the same day per the Learning loop above.

### Native resolution (no soft upscale)
- Ship targets: **9:16 → 2160×3840**, **1:1 → 2160×2160**, **16:9 → 3840×2160**.
- A deliverable whose `ffprobe` width/height is below that target is **FAIL_RES**, even if it
  "looks sharp" on a phone. Soft ffmpeg/AI upscale of a 720/1080 master is forbidden.
- Step 8 output line above that still says `1080x1920` is the *edit working format* only when
  the brief is explicitly 1080. Default new marketing / card / Margot short-form masters to
  native 2160. Living Card edition loops on card.unite-group.ink are 9:16 @ 2160×3840; Signature
  reveal is 1:1 @ 2160×2160.
- Generate native (Higgsfield Gemini Omni Flash 4K / MiniMax H3 2K only as interim, Artlist /
  Kling per brand fence). Prefer image-to-video from a real first/mid frame, not text-only drift.

### Pre-ship QC gate (mandatory before step 9 and before Phill sees it)
Run Playwright seek-screens **and** ffmpeg probes on the final MP4. Record evidence next to the
job (frames + `MARKETING-GATES.md` + probe JSON). No evidence = FAIL.

1. **Black / empty screens** — not only classic `blackdetect` on pure #000. Flag any stretch
   where mean frame luminance is near-black/near-white **or** the picture is empty UI chrome /
   void with no subject (Synthex FAIL ~55–76s). Near-black openers and cream-blank holds FAIL.
2. **Cutoffs** — OCR or frame review: no truncated words, clipped diagrams, or cards showing
   only their tops. Any on-screen text must be fully inside safe margins.
3. **Contrast / three-second rule** — Gate 1 from `marketing-release-gates`: muted picture at
   0 / 1.5 / 3.0s must show the product or problem (tight subject). Logo-card or mood-only open
   with tiny mark = FAIL. Brand/product by 2s in short-form feeds.
4. **Music bed / silence** — for any film with VO or branded storytelling: continuous low bed
   (Artlist / Mixkit ~0.20 ducked under voice). Count silence gaps at −35 dB / 0.2s and −45 dB /
   0.4s; any gap that leaves VO-only air is FAIL. Pure edition loops that are intentionally muted
   are exempt only when the brief says `audio: none` (Living Card edition openers). Margot,
   card-film, Synthex marketing, website film: never mute, never VO-over-silence.
5. **Claims / banned niches** — Gate zero A/B from `unite-group-video-pipeline` still apply.
   Unite-Group marketing never promotes restoration / mould / water damage / cleaning / courses.

### Specialised bots that must enforce the same rules
When SDA dispatches (or when `video-director` runs outside SDA), these skills own the matching
check and may not waive it without Phill's written GO:

| Check | Owner skill |
|---|---|
| Story / channel / native-2160 brief | `video-director` |
| No empty holds, no cutoffs in the cut | `video-editor` |
| Continuous ducked bed; silence = FAIL | `video-sound-designer` |
| Frame audit: empty/near-black, OCR cutoffs, brand marks, AI-slop | `video-brand-guardian` |
| Grade still readable at 2160 | `video-colorist` |
| Camera / start-frame grounding | `video-cinematographer` |
| Faceless / brand styled batches | `brand-video`, `faceless-video` (ship native 2160 when brief is marketing/card) |

### Evidence from 05/11/2026 (reference, do not delete)
- Synthex YT FAIL: `/workspace/synthex-video-qc/report/` + `MARKETING-GATES.md` (black/empty UI,
  ~30% silence, cutoffs, Gate 1 open fail). Source: https://www.youtube.com/watch?v=7L_swG39cEo
- Living Card inventory: `/workspace/lbc-video-qc/` — all 14 live MP4s on
  https://card.unite-group.ink below 2160 (editions 720×1280; Signature 960²). Soft upscale
  rejected; native regen GO'd the same day under Higgsfield house credit cap
  (≤10% balance, never >300 unless Phill raises it).
