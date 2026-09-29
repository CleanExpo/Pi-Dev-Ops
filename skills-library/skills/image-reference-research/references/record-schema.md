# Image record schema

One JSON object per image, appended to `.research/imgrefs/<run>/manifest.jsonl`. `id` is
`sha256(canonicalImageUrl)` so re-discovery is idempotent (reuse-before-rescrape keys on it).

```json
{
  "id": "sha256(canonicalImageUrl)",
  "runId": "",
  "facet": "",
  "sourcePageUrl": "",
  "canonicalImageUrl": "",
  "discoveredVia": "exa|websearch|webfetch|apify|firecrawl|browser",
  "sha256": "",
  "phash": "",
  "width": 0,
  "height": 0,
  "format": "",
  "creator": "",
  "sourceAttribution": "",
  "captureDate": "",
  "licenceClass": "publicly-reproducible|nominative-reference-only|licensed-internal|protected-do-not-republish|unknown-rights-quarantine",
  "licenceEvidenceUrl": "",
  "robotsVerdict": "allow|disallow|unknown",
  "qualityScore": 0.0,
  "taxonomyTags": [],
  "diversityFlags": [],
  "usage": "reference-only",
  "quarantined": false,
  "recheckTrigger": ""
}
```

## Field notes
- `sha256` — of the image bytes; exact-duplicate key. `phash` — perceptual hash (see `dedup.mjs`);
  near-duplicate key at Hamming ≤ 8.
- `taxonomyTags` — facet-grid tags from §1 (subject/scene/angle/condition), used for the coverage
  and diversity reports.
- `diversityFlags` — notes where a facet is over-represented or a demographic/condition axis is
  thin, feeding the §5 diversity check.
- `usage` — always `reference-only` for this skill. `quarantined` — true routes the record to
  `quarantine/` and out of every board.
- `recheckTrigger` — optional condition to re-verify rights later (e.g. a licence page that 404'd,
  a robots verdict of `unknown`).

Completion criterion: every emitted record validates against this shape; no board-bound record has
an empty `licenceEvidenceUrl` or a `quarantined: true`.
