# ADR 005: Voice transcription provider — DEFERRED to v1.1

**Date:** 2026-05-15
**Status:** Deferred — pending Phill decision

## Context

ADR 003 locked the Discuss verb's voice-reply branch. v1 Phase 4 ships a typed
`Transcriber` Protocol with a `StubTranscriber` that raises `NotImplementedError`,
so call sites + intake-router are wired but no live transcription occurs.

Note: ADR 004 in this repo covers implementation conventions. This ADR is numbered
005 to avoid a collision.

## Decision (DEFERRED)

The concrete provider needs Phill's call between:
- **OpenAI Whisper API** — proven, $0.006/min, Anthropic-compatible billing path
- **Deepgram Nova-2** — faster latency (~0.5s vs Whisper's 2-4s), $0.0043/min
- **Self-hosted whisper.cpp** — $0 marginal but adds infra surface

Trigger to land this ADR: a single voice reply lands in the test bot AND Phill
states a provider preference.

## Implementation contract once chosen

1. New module `swarm/pilot/transcribers/{provider}.py` implementing `Transcriber` Protocol.
2. Wire selection via env var `PILOT_TRANSCRIBER_PROVIDER=whisper|deepgram|local`.
3. Replace `voice.StubTranscriber()` call in `intake_router._maybe_handle_pilot_voice`
   with a factory `voice.get_transcriber()` that reads the env var.
4. Add per-provider tests + secret-handling per `[[feedback-secrets-handling]]`
   (key in `~/.hermes/.env` or 1Password — never paste in chat).

## Cross-refs

- `[[adrs/003-interactive-game-mode]]` — parent decision
- `[[context.md#discuss-verb]]` — glossary entry
- `[[feedback-secrets-handling]]` · `[[feedback-make-calls-not-questions]]`
