---
name: remotion-editing
description: Use when a Remotion video has timing, sync, transition, caption, pacing, or audio-fit risk and needs editing discipline before render.
owner_role: Editor
status: remotion-wave-1
intents: remotion-editing, video-editing, timing-sync
---

# remotion-editing

Fixes the current pain points: sync, timing, render correctness, voice speed, captions, and transition rhythm.

## Editing rules

- Use actual audio duration to extend scene durations.
- Never shorten a scene below the audio length.
- Keep transitions short and intentional.
- Captions should come from narration text where possible.
- Final render must pass ffprobe drift validation.

## Verification checklist

- [ ] Estimated speech budget is recorded.
- [ ] Audio-fit runs after TTS.
- [ ] Final MP4 has audio in production.
- [ ] Audio does not overrun video beyond tolerance.
