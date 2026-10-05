---
name: image-reference-research
description: Build a rights-aware industry image REFERENCE library (research only — never republish) to design ORIGINAL images from. Query-expanded discovery via Exa/Firecrawl/Apify with browser fallback, canonical+perceptual dedup, licence classification + quarantine, provenance-complete records, visual-taxonomy reference boards, and style-token handoff to image-generation skills. Use when the user asks for industry image references / reference board / moodboard from real photos / image research for {industry}, or when faceless-video, brand-video, or heygen-director needs reference imagery.
---

# image-reference-research — rights-aware industry image references

Build a **reference** library of real industry images used to design *original* images. It is
research, never republication: the skill emits provenance records, taxonomy boards, and style
tokens — never a redistributable copy of an unlicensed source.

**Non-negotiable (state it, then honour it every run):** references inform original design.
Unknown-rights material is quarantined, never boarded. No source pixel is passed downstream for
republication — only descriptions and style tokens.

## Reuse before rebuild (single source of truth — never duplicate these)
- **Discovery ladder + credibility + reuse-before-rescrape + vault capture** → the `source-ingest`
  skill's tiered research substrate (Exa/whitelisted-WebSearch → WebFetch → crawl4ai → browser-harness,
  never-silent degradation) and its credibility tiers. Do not re-encode the ladder here.
- **Browser lane** → the `browser-routing` skill (exact-src download rule for Artlist-class sites).
- **Apify route** → the `apify-research-connector` card (paid; its Credential Gate owns cost).
- **Authoring/format** → `skill-authoring-standard` (this skill obeys it).

## Inputs → outputs
Input: an industry (+ optional facets, cost ceiling, downstream target). Output under
`.research/imgrefs/<run>/`: `manifest.jsonl` (one record per image), `quarantine/` (unknown
rights), an HTML `board.html`, `style-token.md` (faceless-video Stage-0b format), and a
coverage+blocker report. Completion = every board image has a complete record and a non-`unknown`
licence class.

## Process — each step ends on a checkable criterion

### 0. Reuse-before-rescrape
Read any prior `manifest.jsonl` for this industry; skip already-captured `sourcePageUrl`s.
Ground the industry vocabulary with the `nexus-recall` gate before expanding queries.
- **Done when:** the run manifest is seeded with prior captures and the reuse set is logged.

### 1. Ontology + query expansion
Expand the industry into a facet grid (subjects × scenes × angles × conditions) →
[`references/ontology-method.md`]. Emit per-facet queries.
- **Done when:** a facet grid exists and every facet has ≥1 query.

### 2. Discovery (never silent)
Run the `source-ingest` tiered ladder (Exa/whitelisted-WebSearch → WebFetch → crawl4ai → browser),
licence-native sources first. Every candidate page URL is stamped with the lane that found it
(`exa` | `websearch` | `webfetch` | `browser`); degradation is logged, never silent.
- **Done when:** candidate page URLs exist, each lane-stamped; degradation is logged, not silent.

### 3. Extraction routing
Route each page per [`references/connector-matrix.md`]. Emit raw image records (source page,
canonical image URL, dimensions, discovered-via lane).
- **Done when:** each surviving candidate has a raw record or a logged skip reason.

### 4. Rights gate (fail-closed)
Classify every record per [`references/rights-classes.md`]: licence class + evidence URL + robots
verdict. Check robots/terms BEFORE extraction; `disallow` → skip + log. Unknown rights →
`quarantine/`, never a board.
- **Done when:** every record carries a licence class and robots verdict; unknowns are quarantined.

### 5. Curate
`scripts/dedup.mjs` (canonical URL → sha256 → pHash Hamming ≤ 8), `scripts/quality.mjs`, taxonomy
tag, then a gap/diversity check against the §1 facet grid.
- **Done when:** duplicates collapsed, quality scored, tags applied, coverage gaps named.

### 6. Board + handoff
`scripts/board.mjs` renders `board.html` (only non-`unknown`, non-quarantined records). Write
`style-token.md` in faceless-video Stage-0b format for the downstream image-generation skill.
- **Done when:** the board renders with 0 protected/unknown images and every image has a record.

## Record schema, licence classes, connector routing, eval
- Record fields: [`references/record-schema.md`].
- Licence classes + robots gate: [`references/rights-classes.md`].
- Connector routing matrix: [`references/connector-matrix.md`].
- Facet-grid method: [`references/ontology-method.md`].
- Acceptance bar + how to run the eval: [`references/eval-harness.md`]
  (`node scripts/eval.mjs` — offline, no network; dedup F1 ≥ 0.9, licence accuracy ≥ 0.95).

## Agents (parallel-safe; unique output filenames — parallel-collision rule)
Orchestrator plans the facet grid, then dispatches: **query-planner** (cheap) → **discovery
scouts** (one per facet batch, Exa-first, write `scout-<facet>.jsonl`) → **extractors** (per the
matrix) → **rights classifier** (serial gate) → **curator** (serial gate) → **board builder**.
Scouts/extractors run parallel; classifier and curator are serial gates (rights before curation,
curation before board). Declare the cost ceiling up front; paid Apify actors only via the adopted
card's explicit-cost approval gate.

## Blockers (report, never guess)
`APIFY_API_TOKEN` absent → Apify lane emits a `blocked` record (safe). Firecrawl unwired →
`Firecrawl-absent` stamp, degrade to WebFetch/crawl4ai. Exa down → lane-stamped degrade (never
silent). Rights ambiguity → quarantine, never a permissive guess.
