# ADR 001: Pillar canonicalisation — array-typed pillar + wiki-sourced master enum + per-source canonicaliser

**Date:** 2026-05-15
**Status:** Accepted

## Context

The Pilot bot ingests suggestions from 5+ sources (Linear, Margot research, GitHub, Gmail, wiki). The grill-with-docs smoke test 2026-05-15 surfaced a 3-way `pillar` drift:

- `goal_feed._PILLARS` declared 11 values (master plan).
- `linear_source._TEAM_TO_PILLAR` declared 8 Linear team keys → 6 pillars.
- `margot_source._VALID_PILLARS` declared a different 8-value subset.

Each source carrying its own pillar enum is a category error: Linear teams do not map 1:1 to business pillars (e.g. KR7 IEP has no Linear team), and a single initiative frequently advances multiple pillars (cross-pillar work is common). Forcing a 1:1 source-pillar mapping breaks both representational fidelity and ingestion correctness.

## Decision

1. **Array-typed `pillar` column.** `pilot_suggestions.pillar` becomes `text[]` (Postgres array). Cardinality is ≥1.
2. **Master enum lives in `[[master-plan-2b-by-2028-v3]]` YAML frontmatter** under key `pillars:`. Loaded at startup, cached, invalidated on wiki sync. Phill edits the master plan — pillar list updates without a code deploy.
3. **Per-source `PillarCanonicaliser`.** Each source extracts its native identifier (Linear team key, Margot tag, GitHub label, etc.) and delegates to `PillarCanonicaliser.canonicalise_<source>(raw) -> list[str]`. The canonicaliser returns ≥1 master pillars from the wiki-frontmatter list. Sources no longer carry their own pillar enums.
4. **Fallback contract.** Unmapped raw identifiers return `["uncategorised"]` — preserves the ≥1 invariant and surfaces in UI as a signal to add the mapping. Never returns empty.

## Consequences

**Easier:**
- Single source of truth for the pillar list (the master plan wiki page).
- Multi-pillar suggestions accurately represented (no more arbitrary "primary pillar" picks).
- Sources stay loosely coupled to business strategy — adding a new pillar is a wiki edit, not a code change.
- Refactoring out `_TEAM_TO_PILLAR` and `_VALID_PILLARS` removes hidden divergence.

**Harder:**
- Schema migration: `pilot_suggestions.pillar` from `text` (or unset) to `text[]`. Backfill scalar values to single-element arrays. ~1 migration, reversible by collapsing arrays back to first element.
- Downstream consumers (dashboards, goal feeds, Telegram message composer) must handle array-typed pillar fields — chip-style UI rendering, multi-pillar filters, etc.
- Adds a startup dependency: wiki must be reachable + parseable to load the master enum. Mitigation: cache to disk fallback, TTL ~24h, hard-fail on missing canonical list (don't silently default to empty enum).

**Now hard to undo:**
- Once the array column ships and downstream consumers depend on it, reverting to scalar requires choosing which pillar to drop per row.
- Once the canonicaliser is the only path from source-raw to master pillar, removing it forces every source to re-implement its own mapping.

## Alternatives considered

- **Shape A — `goal_feed._PILLARS` is law (11-value enum in code):** rejected. Forces hacky fallbacks in Linear and Margot sources (header parsing, label scraping) and re-creates the 3-way drift problem when one of the three places gets edited without the others.
- **Shape B — wiki frontmatter is law, single-value pillar per suggestion:** rejected. Single-value cardinality is a category error — real initiatives span pillars. Forces arbitrary "primary pillar" picks at ingestion time, which then drift from the actual cross-pillar reality the human assigner sees.
- **Shape C — per-source pillars + scalar canonicaliser output:** rejected. Half-fix. Solved the source-coupling problem but kept the cardinality category error.

Adopted shape = **C array + B master enum** — the canonicaliser pattern with wiki-sourced authority and ≥1 cardinality.

## Implementation path (deferred to `superpowers:writing-plans`)

Plan-time concerns, NOT glossary-time. The plan agent receives this ADR as a locked input and authors:

1. Schema migration (text → text[]) with backfill.
2. Wiki frontmatter reader utility with TTL + webhook invalidation strategy.
3. `PillarCanonicaliser` class with per-source methods.
4. Source refactors — strip `_TEAM_TO_PILLAR` from linear_source, `_VALID_PILLARS` from margot_source.
5. Consumer refactors — dashboards, goal_feed, Telegram composer handle arrays.

Per `[[feedback-substrate-change-discipline]]`: shadow-run the canonicaliser against current production suggestions for ≥50 dispatches before cutover. Per `[[feedback-tight-code]]`: the canonicaliser stays ≤200 lines.

## Cross-refs

- `[[context.md#pillar]]` · `[[context.md#canonicaliser]]` · `[[context.md#master-enum-pillar]]`
- `[[master-plan-2b-by-2028-v3]]` — the master enum source-of-truth
- `[[agency-bot-design-2026-05-14]]` — Pilot bot spec being refined
- `[[grill-output-pilot-bot-pilot-2026-05-15]]` — smoke-test that surfaced this drift
- `[[feedback-substrate-change-discipline]]` · `[[feedback-tight-code]]` · `[[feedback-quality-over-quantity]]`
