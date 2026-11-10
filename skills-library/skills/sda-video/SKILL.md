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
| 2 | Margot's voice | ElevenLabs voice "Margot - Bright, friendly and upbeat", ID `tAtHhBlA3E0eKZJKNSKE` (pinned in `~/Synthex/packages/brand-config/src/brands/*.ts` and `~/Synthex/tests/unit/brand-config/product-voice.test.ts`); call it through the ElevenLabs connector, no key file needed | `voice.mp3` with word timestamps |
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
colours. Look at a frame of every insert before it goes into the cut.

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
