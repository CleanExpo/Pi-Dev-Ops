# Connector routing matrix

Route each discovered page to the cheapest connector that can extract it cleanly, then fall back
in order. Every extraction is lane-stamped in the record (`discoveredVia`). Paid lanes (Apify)
only fire behind the adopted `apify-research-connector` card's explicit-cost gate.

| Job | Primary | Fallback | Rights note |
|---|---|---|---|
| Broad web image discovery | Exa (`web_search_exa`) | WebSearch whitelist → WebFetch | Exa returns source **pages**, not images — extract the image per row |
| Structured site / marketplace extraction | Apify official actor (adopted card) | Firecrawl (when wired) → crawl4ai | Apify = paid; explicit-cost gate before any run |
| JS-heavy / anti-bot page | Firecrawl (when wired) | `browser-routing` (browser-harness) | robots/terms checked before extraction |
| Single known page → clean content | Firecrawl | WebFetch | fastest clean-content path |
| Licence-native sources (Openverse / Wikimedia) | WebFetch / their API | — | preferred: rights are explicit, so start here |

## Ordering rule
Prefer **licence-native sources first** (Openverse, Wikimedia Commons, Flickr Commons, government
media libraries). Their rights are explicit, so they clear the rights gate deterministically and
seed the board with zero-risk references before any ambiguous lane runs.

## Lane availability (check at runtime, degrade honestly)
- **Exa** — deferred connector; load with
  `ToolSearch "select:mcp__claude_ai_Exa__web_search_exa,mcp__claude_ai_Exa__web_fetch_exa"`.
  Absent (headless/cron) → stamp `Exa-absent`, drop to WebSearch. See the `source-ingest` tiered ladder.
- **Apify** — needs `APIFY_API_TOKEN`. Absent → the lane emits a `blocked` record and the run
  continues on the free lanes; never silently skip.
- **Firecrawl** — needs `FIRECRAWL_API_KEY` or a Composio link. Unwired → `Firecrawl-absent`
  stamp, degrade to WebFetch / crawl4ai.
- **Browser** — the `browser-routing` skill owns the exact-`src` download rule for Artlist-class
  galleries; use only when robots/terms allow.

Completion criterion for this step: every candidate page has an extraction lane assigned, or a
logged skip reason (robots disallow, all lanes absent, or already-captured).
