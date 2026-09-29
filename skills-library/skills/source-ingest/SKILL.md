---
name: source-ingest
description: Capture real, credible data from authoritative sites into the 2nd-Brain vault Sources/ library so it can be cited by any FACT/non-fiction content (faceless-video FACT mode, marketing copy, SEO articles, client deliverables). Tiered research substrate (margot deep_research -> credibility-whitelisted WebSearch -> WebFetch -> crawl4ai headless deep-crawl -> browser-harness -> Bright Data escalation), credibility-rated, citation-preserving, reuse-before-rescrape. Use when the user says "research X", "find real data on", "scrape credible sources", "build my source library", "ingest sources", or whenever a FACT script/article needs verifiable claims. NOT for fiction (story mode invents).
---

# Source Ingest — credible-data library for the vault

Turns one-off research into a reusable, citable corpus. Every fact used in FACT content must trace to a stored source here. Vault: `~/2nd Brain/2nd Brain/Sources/`.

## Credibility tiers (cite only Tier 1–2 as fact)
- **Tier 1 — primary/official:** government (.gov), official statistics bodies (ABS, WHO, OECD, BLS), peer-reviewed journals (nature.com, nih.gov/pubmed, doi.org), standards bodies (IICRC, ISO), regulator filings. The only sources strong enough to anchor a hard claim.
- **Tier 2 — reputable secondary:** established news of record, industry associations, major institutions, vendor docs for their own product. Usable with attribution.
- **Tier 3 — tertiary:** blogs, wikis, forums, AI summaries. Context/lead-generation ONLY — never the citation for a stated fact. Trace Tier 3 claims back to their Tier 1–2 origin before use.

## Step 1 — Reuse before re-scrape
Grep the existing library first: `grep -ril "<topic terms>" ~/2nd\ Brain/2nd\ Brain/Sources/`. If a source exists and is fresh enough (check `captured:` date vs how fast the data changes), cite it — do not re-scrape. 385+ sources already exist; the library compounds.

## Step 2 — Research (tiered substrate, cheapest/cleanest first)
1. **`mcp__margot__deep_research(topic, use_corpus=…)`** — Gemini 3.1 Pro cited synthesis. Primary for "what does the credible literature say about X." Set `use_corpus=True` to anchor against the Unite-Group corpus.
2. **`WebSearch(query, allowed_domains=[…])`** — set `allowed_domains` to a credibility whitelist (e.g. `["who.int","nih.gov","abs.gov.au","nature.com","oecd.org",".gov",".edu"]`) so results ARE Tier 1–2. This is the "credible sites" lever.
3. **`WebFetch(url, prompt)`** — pull the specific stat/quote + its context from each chosen URL. Capture the exact figure, date, and surrounding sentence for honest citation.
4. **`crawl4ai` (unattended headless JS fetch + whole-site deep-crawl → clean Markdown)** — for JS-rendered credible pages a static `WebFetch` can't read, and for bulk multi-page crawls, WITHOUT driving the user's live Chrome. **Local only** (headless Chromium — never the Railway always-on backend); check out on first use: `pip install crawl4ai && crawl4ai-setup`. Use `AsyncWebCrawler` and take `result.markdown`/`fit_markdown` straight into Step 3. Prefer this over `browser-harness` for any unattended/cron ingest. It is a fetcher only — do NOT use it for research-synthesis (that's margot #1) or SERP/keyword data (that's the `seo`/DataForSEO skill, "not scraping"). Escalate up to #5 for auth-walls, #6 for anti-bot.
5. **`browser-harness`** — for auth/login-walled credible sources on the user's real Chrome profile that headless `crawl4ai` can't reach (see the `browser-harness` skill).
6. **Bright Data (PAID ESCALATION — only when 1–5 fail):** anti-bot / dataset / geo-locked credible sources. Not wired by default; see `connections.md` "Image/media + research" + Bright Data setup. Escalate to this only when a Tier 1–2 source actively blocks all cheaper routes, and log the spend.

**Document (PDF/DOCX) sources:** convert to Markdown with **Docling** (`pip install docling` — MIT, unrestricted) before capture. Do NOT use `marker` for any client-facing/commercial path: its model weights are OpenRAIL-M "free only under $2M revenue/funding", a licence landmine at Unite-Group scale — Docling is the safe default.

## Step 3 — Capture to the library
Write `~/2nd Brain/2nd Brain/Sources/<topic-slug>-<YYYY-MM-DD>.md` with frontmatter matching the vault convention, extended with credibility:
```yaml
---
title: "<source title>"
source: "<canonical URL>"
captured: "YYYY-MM-DD"
credibility: tier-1 | tier-2          # tier-3 is context only, usually not stored as a citable source
publisher: "<org>"
topic_tags: [..]
tags: [clippings, source-ingest]
---
```
Body: the **extracted facts as a bulleted list, each with its exact figure + inline citation** (publisher, year, URL), then a short verbatim quote block for the key claim. Keep the raw evidence — don't paraphrase away the number. Read-only after import (vault rule).

## Step 4 — Index + log
Append one line to `~/2nd Brain/2nd Brain/Sources/SOURCE-LIBRARY.md` (create if absent): `- [<title>](<file>) — Tier N — <topic> — captured YYYY-MM-DD`. Append an ingest line to `Wiki/log.md`.

## Step 5 — Hand back
Return the stored file path(s) + the citable facts. For FACT-mode `faceless-video`, the script writer pulls claims from these files and accuracy-gates against them — every stat in the script must point to a stored Tier 1–2 source. NEVER let a Tier 3 or unsourced claim into a FACT script.

## Adversarial check (before a claim ships)
For any load-bearing statistic: confirm it appears in ≥1 Tier-1 source OR ≥2 independent Tier-2 sources. If only one weak source supports it, mark it "unverified" in the script notes and soften or drop the claim. Cross-check figures that look surprising.
