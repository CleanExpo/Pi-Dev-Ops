---
name: marketing-seo-researcher
description: Performs keyword research, search-intent classification, SERP analysis, and content-gap discovery for a brand or topic cluster. Use when a brief asks for "SEO", "keywords", "search intent", "SERP", "content gap", "ranking strategy", or upstream of any blog / landing-page work that targets organic search. Outputs a structured SEO brief consumed by copywriter and channel-strategist.
automation: automatic
intents: seo, keyword-research, search-intent, serp-analysis, content-gap, ranking-strategy, organic-search
---

# marketing-seo-researcher

Owns "what people search, what they expect to find, and where the brand can rank". Foundation for every SEO-driven content asset.

## Triggers

- Brief contains "SEO", "keywords", "search intent", "ranking", "SERP", "content gap", "organic", "rank for".
- Or invoked by `marketing-orchestrator` / `marketing-channel-strategist` when channel mix includes organic search.
- Or by `marketing-copywriter` before any blog / landing artifact targeted at search.

## Inputs

- `brand` slug
- `topicCluster` — the seed (e.g. "synthetic data for ML training")
- `competitorDomains` (optional) — explicit competitors; otherwise derived from positioning's competitive map
- `geoTarget` (optional) — country / region restriction (default: AU+US for Pi-CEO portfolio)
- `intentFilter` (optional) — `informational` | `commercial` | `transactional` | `navigational` (default: all)

## Method

1. **Seed expansion**. Take topicCluster + ICP vocabulary phrases as seeds. Expand via:
   - Google autocomplete (lateral expansion).
   - "People also ask" + related searches (intent expansion).
   - Reddit / forum question titles (long-tail, conversational).
   - Competitor blog/page titles (gap reference).
2. **Classify each keyword**:
   - **Intent**: informational / commercial / transactional / navigational.
   - **Funnel stage**: TOFU / MOFU / BOFU.
   - **Difficulty proxy**: domain authority of top 10 results (use Perplexity / public SEO tools if `PERPLEXITY_API_KEY` available).
   - **Volume estimate**: bucket (high / medium / low / unknown).
3. **SERP feature check** per keyword: does the SERP have featured snippet, video carousel, "people also ask", knowledge panel, sitelinks, shopping? Determines content format requirements.
4. **Content-gap analysis**: pull top 3-5 ranking URLs per keyword. Tag what they cover, what they miss. The gap is the brief.
5. **Cluster pyramid**:
   - **Pillar page** — the highest-volume, broadest keyword (1 per cluster).
   - **Cluster pages** — 5-15 supporting pieces, each targeting a long-tail variant.
   - Internal linking spec (every cluster page links back to the pillar; pillar links out to all cluster pages).
6. **Quick-win shortlist**: 3-5 keywords where the brand can plausibly rank top 10 within 90 days based on current domain strength + content gap.

## Output

`<calling-project>/.marketing/seo/{topicCluster-slug}.md` + `.json`:

```jsonc
{
  "brand": "synthex",
  "topicCluster": "synthetic data for ML training",
  "geoTarget": ["US", "AU"],
  "pillar": {
    "keyword": "synthetic data for machine learning",
    "intent": "informational",
    "funnel": "TOFU",
    "difficulty": "high",
    "volume": "high",
    "serpFeatures": ["people-also-ask", "video-carousel"],
    "topRankers": ["competitorA.com/...", "competitorB.com/..."],
    "gap": "None of the top 5 cover regulated-industry use cases (healthcare, finance) with code examples"
  },
  "clusterPages": [
    { "keyword": "synthetic data healthcare HIPAA", "intent": "commercial", "funnel": "MOFU", "difficulty": "medium", "volume": "low", "format": "case-study + checklist", "internalLinkTarget": "pillar" },
    ...
  ],
  "quickWins": [
    { "keyword": "...", "estimatedRankIn90Days": "top-10", "rationale": "..." }
  ],
  "internalLinkingSpec": [
    { "from": "cluster-1", "to": "pillar", "anchor": "..." }
  ]
}
```

## Boundaries

- Never publish keyword lists with no intent classification — it's the difference between a useful brief and a blob.
- Never recommend keywords with difficulty far above current domain authority unless the gap analysis is exceptional. Be honest about timeline.
- Never invent volume / difficulty numbers. If `PERPLEXITY_API_KEY` is missing, use bucketed estimates ("high / medium / low") and flag the absence.
- Never produce SEO briefs that ignore the brand's `forbiddenWords` (e.g. CCW must not target "cheapest carpet cleaner" even if it ranks well).

## Hands off to

- `marketing-copywriter` (each cluster page → blog post brief)
- `marketing-channel-strategist` (validates SEO budget vs. paid budget split)
- `marketing-analytics-attribution` (organic search KPIs in dashboard)

## Per-project keys

- `PERPLEXITY_API_KEY` — SERP scraping, autocomplete expansion, competitor page extraction. Missing → returns seed-only list with "needs SERP data" placeholders.
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` — intent classification + gap analysis. Missing → returns raw keyword list, no classification.
