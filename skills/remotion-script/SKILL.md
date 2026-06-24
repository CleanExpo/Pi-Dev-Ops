---
name: remotion-script
description: Use when a Remotion marketing video needs a timed script, scene narration, on-screen text, CTA, and voice pacing that fits a single ElevenLabs voice.
owner_role: Script Producer
status: remotion-wave-1
intents: remotion-script, video-script, narration-script
---

# remotion-script

Creates the script layer for `/remotion-video`.

## Rules

- single voice only: all narration is written for one Synthex ElevenLabs narrator.
- Target calm professional cadence: approximately 145-160 WPM.
- Prefer 5 scenes for a 60s marketing video: hook, problem, mechanism, proof, CTA.
- On-screen text must be shorter than narration.
- Every scene has `sceneId`, `sceneType`, `durationSec`, `voiceover`, `onScreenText`.

## Timing budget

Before rendering, estimate words per scene at 2.6 words/sec. If a scene cannot fit, shorten the copy or extend the scene. Never let Remotion clip narration at sequence boundaries.

## Verification checklist

- [ ] No scene requests a second voice.
- [ ] CTA is singular.
- [ ] Script fits duration budget.
- [ ] On-screen text is readable and not a transcript dump.
