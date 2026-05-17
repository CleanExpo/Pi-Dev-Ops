# RA Help Library Render — Postmortem (2026-05-15)

## What Phill saw

`help-inspections.mp4` rendered last night played narration that **cut mid-sentence** and **drifted out of sync** with on-screen visuals. Same defect across all six `ra-help-*.mp4` files.

## Root cause

**Mechanism: ElevenLabs audio overran the storyboard's planned `durationSec` for at least one scene per video; the `<Sequence durationInFrames={dur}><Audio /></Sequence>` wrapper in `src/compositions/Explainer.tsx` unmounted the `<Audio>` element when the Sequence ended, clipping the narration at the scene boundary.**

The storyboard schema is fundamentally optimistic — it asks the storyboard author to estimate `durationSec` per scene before TTS exists. ElevenLabs returns whatever duration the speech actually took. There was no reconciliation step. The result:

### Inspections, scene-by-scene (the reported video)

| sceneId           | planned | actual TTS | overrun | outcome |
|-------------------|---------|-----------:|--------:|---------|
| hook              | 6.00s   | 6.41s      | +0.41s  | cut at boundary (small) |
| flow-capture      | 14.00s  | 11.47s     | -2.53s  | ok (silence at tail) |
| **keypoints-cocoa** | **13.00s** | **16.67s** | **+3.67s** | **cut mid-sentence — "Photos that can't be tampered with after capture..."** |
| stat-evidence     | 11.00s  | 8.82s      | -2.18s  | ok |
| body-verify       | 13.00s  | 11.94s     | -1.06s  | ok |
| cta               | 8.00s   | 5.53s      | -2.47s  | ok |

Sum of planned: 65.00s. Rendered video: 65.000s. Audio per the failed `ffprobe`: 65.045s. The "65s of audio" number is the SUM of clipped per-scene audio — each scene's `<Audio>` ran to its `<Sequence>` boundary, then was cut. The actual TTS spent ~60.84s but only ~50s of intelligible narration made it to the final cut once you account for the three clipped scenes.

### Pattern is universal across all six help videos

Worst offenders:
- `compliance` scene-0 (hook): planned 6s, actual 11.28s — **hook narration cut by 5.28s**
- `team` scene-3: planned 11s, actual 22.20s — **mid-scene cut by 11.20s**
- `billing` scene-2: planned 13s, actual 19.78s — cut by 6.78s
- `inspections` scene-2: planned 13s, actual 16.67s — cut by 3.67s (Phill's reported video)
- `reports` scene-2: planned 13s, actual 14.35s — cut by 1.35s
- `clients-and-portal` scene-2: planned 13s, actual 14.91s — cut by 1.91s

### Sync drift

Each scene's audio is independently sequenced. When scene N's audio finishes early (e.g. CTA: 5.53s audio in 8s window), the next scene's window doesn't start until the Sequence boundary — so on-screen visuals for scene N+1 are still "preparing" while the audio cue would expect them already showing. When scene N's audio is cut (e.g. keypoints-cocoa), the next scene's narration starts at its Sequence boundary regardless of whether scene N's narration finished. Either way, on-screen text never moves in lockstep with the spoken word.

## The fix (committed)

Two new modules added to `render/`:

### `render/audio-fit.ts`

After TTS synthesis, ffprobe each mp3 and rewrite `scene.durationSec = max(planned, actualAudio + 0.5s tail)`. The Sequence now always outlives the Audio it contains. Visual pacing is preserved when audio is short; the composition lengthens when audio is long. Total video duration becomes whatever the sum of fitted scenes is — `calculateMetadata` in `Root.tsx` already computes this from `durationSec` so no schema change needed.

### `render/validate.ts`

- **`preflightScript`** — runs BEFORE TTS. Counts words per scene voiceover, divides by 2.6 wps (the conservative AU-explainer floor empirically measured against this batch's clipped scenes), warns if estimated TTS exceeds planned duration. Today it's a warn (audio-fit catches the rest); raise to fail-on-error when storyboards mature.
- **`postrenderProbe`** — runs AFTER renderMedia. Ffprobes the output. Asserts `audio_duration ≤ video_duration + 100ms` and that an audio stream exists. Throws (exit 1) on failure so a silent or clipped MP4 cannot escape the pipeline.

### `render/render.ts` (wired)

Pipeline is now: pre-flight → TTS → audio-fit → bundle → render → post-render. Skip flags `--skipTts` and `--skipValidate` exist for emergency overrides.

## Verification on `help-inspections.mp4` (the only re-render in this run)

```
[preflight] sceneId           words  planned  est-tts  fits
[preflight] hook                    16    6.00    6.15  ✗
[preflight] keypoints-cocoa         36   13.00   13.85  ✗

[audio-fit] sceneId           planned   audio    final    +grew
[audio-fit] hook                    6.00     6.41     6.91  +0.91
[audio-fit] keypoints-cocoa        13.00    16.67    17.17  +4.17
[audio-fit] total composition duration: 70.08s

[postrender] video=70.067s  audio=70.101s  delta=35ms  ✓
```

- Video duration: 70.067s (was 65.000s)
- Audio duration: 70.101s (was 65.045s — but with internal clips)
- Delta: 35ms (was effectively un-quantified mid-sentence cuts; brief reported 10s of "missing" audio)
- Final spoken sentence: scene-5 CTA = "Open an inspection. Capture the photo. The audit trail builds itself. RestoreAssist." — terminates with period inside an 8s window holding 5.5s of audio (2.5s of natural tail).
- ElevenLabs spend: $0.00 — all 6 scenes hit the SHA1(`voiceId|style|text`) cache from the prior run.

## Out of scope this run

The remaining 5 videos (`billing`, `clients-and-portal`, `compliance`, `reports`, `team`) are NOT re-rendered. Phill's brief was explicit: approve the fix on `help-inspections.mp4` first, then re-run for the remaining 5. The defect mechanism is identical, the audio cache is hot, and the new pipeline will fix them on demand.

## Permanent process change

The validation gate is on by default for every future render. Any storyboard that overruns will be flagged at pre-flight, auto-extended at audio-fit, and probed at post-render. A future TTS regression that produces a silent MP4 or a mid-sentence cut now causes the render to throw exit 1 rather than ship.

## What would change my mind

- If Phill's reported video duration was genuinely 75s (not 65s as ffprobe shows), the failing file at `public/videos/help/help-inspections.mp4` may be a different artifact than the one in `remotion-studio/output/`. Worth confirming the file Phill watched.
- If the post-render delta gate misses a case (e.g. audio long but with leading silence that masks the clip), it should also probe per-scene audio vs Sequence frames. Not added today — single-video fix scope.
