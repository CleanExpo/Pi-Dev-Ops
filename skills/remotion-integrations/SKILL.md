---
name: remotion-integrations
description: Use when /remotion-video needs existing Synthex ElevenLabs, brand-config, Remotion, output storage, Claude, or Hermes integration without adding vendors.
owner_role: Integrations Producer
status: remotion-wave-1
intents: remotion-integrations, video-integrations, elevenlabs-remotion
---

# remotion-integrations

Integration layer for `/remotion-video`.

## Voice integration

- Use existing Synthex ElevenLabs credentials.
- Resolve the voice from `SYNTHEX_ELEVENLABS_VOICE_ID` first, fallback to `ELEVENLABS_VOICE_ID`.
- Use exactly one single voice for every scene.
- Do not print, commit, or copy API keys.

## Vendor boundary

- no new vendors.
- no new external accounts.
- no connector platforms.
- Cloud/CDN upload is a separate approved step.

## Availability

- Claude: `.claude/commands/remotion-video.md`.
- Pi-Dev-Ops/Hermes route: `video` and `remotion-video` intents.
- Synthex/Unite-Group consume the canonical Pi-Dev-Ops Remotion command unless a thin local command file is approved.

## Verification checklist

- [ ] One voice env source is documented.
- [ ] No key bytes are written.
- [ ] Command works as dry-run without credentials.
