---
name: boardroom
description: Multi-model triangulation for high-stakes decisions. Fan out 2–4 panellists, score divergence via Jaccard, synthesise one answer. Use for architecture, strategy, or machine spec pipeline board review — not routine single-model tasks.
owner_role: Orchestrator
status: active
automation: manual
---

# boardroom — multi-model triangulation

Programmatic API: `app.server.spec_pipeline.boardroom.boardroom_query`.

See ADR 007 (`adrs/007-machine-ship-gate.md`) for machine ship integration.

## When to invoke

- High-stakes outputs where wrong call cost exceeds extra panellist cost
- Machine spec pipeline stage after `/spm` spec is drafted
- User asks "what does the boardroom think"

## When NOT to invoke

- Routine routing — use single-model intent matrix
- More than 4 panellists

## Output contract

Returns `answer`, `panel` (verbatim per model), `min_pairwise_similarity`, `escalated`, `decision`, `confidence`.

## Hard rules

- Never skip synthesis — concatenate-only is banned
- Never swallow panellist responses
- Survive panellist failures (`asyncio.gather` with exceptions)
