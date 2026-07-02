## Summary

Margot M10 desk voice stack: ElevenLabs TTS verifiers, desk loop script, and automated preflight for RA-1694/1695/1696.

- `scripts/verify_margot_voice_tts.py` — ElevenLabs smoke via `swarm/voice_compose.synthesise_voice()` (~530–1600ms)
- `scripts/desk_voice_loop.py` — mic → faster-whisper → Hermes `:8642` → ElevenLabs → speakers (PTT/VAD modes)
- `scripts/verify_desk_voice_stack.py` — non-interactive preflight (profile, STT, Hermes health, TTS)
- `tests/test_verify_margot_voice_tts.py` — unit tests for TTS verifier
- `~/bron-workspace/voice/loop.py` — thin wrapper delegating to Pi-Dev-Ops script

**Voice SSOT:** ElevenLabs `p43fx6U8afP2xoq1Ai9f` (not Voicebox A/B). Voicebox remains optional local TTS only.

## Test plan

- [ ] `python -m pytest tests/test_verify_margot_voice_tts.py tests/test_verify_margot_voice_stt.py -q`
- [ ] `op run --env-file=~/.hermes/.env -- python scripts/verify_margot_voice_tts.py --json`
- [ ] `op run --env-file=~/.hermes/.env -- python scripts/verify_desk_voice_stack.py` (Hermes must be on `:8642`)
- [ ] Manual: `python scripts/desk_voice_loop.py --mode ptt` — PTT round-trip with headset

## Linear

- RA-1693, RA-1695 → Done (ElevenLabs locked)
- RA-1696 → In Review (automated preflight green; manual sign-off pending)
- RA-1697 → In Review (driving design doc at `~/bron-workspace/voice/driving-design-2026-05.md`)
