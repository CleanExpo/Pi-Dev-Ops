---
name: tao-context-vcc
description: Deterministic, LLM-free conversation compactor for TAO sessions. Port of @sting8k/pi-vcc. Reduces transcript bytes via tool-output dedup, verbose-block head/tail truncation, repeat-pattern collapse, and whitespace normalisation. No model calls — runs in the hot path with zero token cost.
owner_role: Tier-Worker (compaction primitive, called by orchestrator + tao-loop)
status: wave-1
linear: RA-1967
---

# tao-context-vcc

Algorithmic compactor that shrinks long TAO transcripts before they hit the model. Same input always produces the same output. Idempotent on a second pass.

## When to trigger

- A TAO session has accumulated >75% of the model's context window.
- Token-budget telemetry on `.harness/agent-sdk-metrics/*.jsonl` shows tokens-per-turn climbing past the historical baseline.
- A new tao-loop iteration is about to start and the autoresearch lens flags rising tokens/turn.

## Public API

```python
from app.server.tao_context_vcc import compact, compact_for_sdk

compacted, stats = compact(messages, target_token_budget=120_000)
# stats.bytes_in / bytes_out / messages_in / messages_out / techniques_applied
```

## Techniques (all deterministic)

1. tool-output dedup — repeat tool turns become `<truncated: same as msg N>`.
2. verbose-block truncate — >2000 lines or >50 KB clipped to head + tail with `<elided ...>`.
3. repeat-pattern collapse — runs of identical messages collapse to one with `<repeated K times>`.
4. whitespace + log-noise normalisation — trailing-ws strip, blank-line dedup, CRLF → LF.

## Validation harness

`scripts/validate_tao_context_vcc.py <dir>` runs `compact()` on every saved TAO session jsonl and prints `tokens_in / tokens_out / pct_reduction / techniques_applied`. Exits 0 if the median reduction is ≥30%.

## Out of scope

- Semantic summarisation (LLM-based compaction lives in `context-compressor`, not here).
- Cross-session compaction. Each call is per-transcript, pure.
