---
name: seo-page-fix
description: On-Page SEO audit + concrete fix list for a single URL. Closes the data-rich, implementation-poor gap our DataForSEO suite leaves — produces an itemised "fix this, then this, then this" PDF a client can hand to a developer (or the swarm can execute autonomously on a Unite-Group-managed site). Use when the user says "page audit", "fix this page", "on-page SEO for {url}", or runs this as the first deliverable for any new client engagement.
---

# On-Page SEO Page-Fix

The Synthex flagship deliverable. Every other SEO skill in the stack is data-out — this one is fix-out: a developer (or the swarm) can read the output top-to-bottom and ship the changes in one PR.

## When to invoke

- "audit this page" with a URL
- "fix the SEO on {url}"
- "on-page audit for {brand}"
- First deliverable after a new client kickoff (`client-portal-provision` complete)
- Test target for Prompt #14: **CCW `/carpet-cleaning-melbourne`** while Toby's on holiday — zero-disruption ship window

## What it does

Given a single URL + the target query (the keyword the page should rank for):

1. **Crawl the URL** via DataForSEO On-Page (or fall back to direct fetch + parse).
2. **Audit the 18 critical on-page signals** in priority order:
   - Title tag (length 30-60 chars, primary keyword in first 30 chars, brand suffix)
   - H1 (single, matches title intent, contains primary keyword)
   - Meta description (140-160 chars, CTA, primary keyword, no duplication)
   - URL slug (lowercase, hyphens, keyword-first, ≤ 5 segments)
   - Canonical tag (self-referential unless intentional)
   - Heading hierarchy (H2/H3 logical, no skipped levels)
   - Word count (≥ target competitors' median, capped at 2,000 unless query is long-form)
   - Internal links (≥ 3, descriptive anchors, NOT "click here")
   - Outbound authority links (≥ 1 to .gov / .edu / a Wikipedia-tier authority)
   - Image alt text (every <img>, descriptive)
   - Schema markup (LocalBusiness / Service / FAQPage as appropriate)
   - Open Graph tags (og:title, og:description, og:image)
   - Twitter Card (summary_large_image)
   - LCP / CLS / INP (Web Vitals — flag if poor)
   - Mobile viewport meta + responsive breakpoints
   - HTTPS + canonical https
   - Robots meta (index, follow unless intentional)
   - Hreflang (only if multi-locale)
3. **Compare against the top 3 ranking pages** for the target query — surface gaps (their word count, their schema, their internal-link depth).
4. **Emit a fix list:**
   - `~/2nd Brain/2nd Brain/Wiki/seo-page-fix-{slug}-{YYYY-MM-DD}.md`
   - One Linear issue per P0 / P1 fix
   - PDF (Gun Metal + Candy Red brand tokens) if `--pdf` requested
   - Optional: `.harness/seo-page-fixes/{slug}.diff` — actual file diff the swarm can apply

## Steps

```
1. Fetch the URL via DataForSEO On-Page (caches the parsed DOM + headers).
2. Parse the 18 signals into a structured audit JSON.
3. Pull top-3 ranking pages for the target query (seo-rankings skill).
4. Build the gap analysis: their median vs target.
5. Sort fixes by impact × ease (P0 = high impact, low effort).
6. Render Markdown audit + optional PDF.
7. File Linear issues per P0/P1.
8. If the target URL is on a Unite-Group-managed Next.js site, write a `.diff` the swarm's PR-triggered Proof Video pipeline can pick up.
```

## Constraints

- **Never** invent client copy. Suggest edits with rationale; let `marketing-copywriter` produce final words.
- **Never** silently change canonical, robots, or hreflang — those carry ranking weight; surface them as decisions.
- AU-specific: schema `LocalBusiness` MUST include AU postcode + suburb when applicable.
- Respect `[[design-preferences]]` — no Lucide icons in the PDF; Gun Metal + Candy Red only.
- Respect `[[no-slack]]` — never recommend Slack-based collaboration in fix steps.
- Skip social-media schema unless the page IS a social-share target.

## Output

End with explicit recommendation per `[[always-recommend]]`. Example:

> ✅ Audit complete for **CCW /carpet-cleaning-melbourne** — 4 P0 fixes (title tag truncated, missing FAQPage schema, no internal link to /quote, LCP 4.2s), 7 P1 fixes. Estimated 6-12 position lift in 30 days. PR draft at `seo-page-fixes/carpet-cleaning-melbourne.diff` ready to ship. Next move: I open the PR against `cleanexpo/ccw-crm` and tag Toby for review when he's back 26 May — zero-disruption window.

## Related

- Companion: `[[seo-gbp-audit]]` (Prompt #2 — local map-pack lever)
- Companion: `[[seo-gbp-posting]]` (Prompt #7 — recurring posting plan)
- Underlying: existing `seo` skill pack (DataForSEO On-Page, SERP, Backlinks)
- Source: `[[research-22-claude-seo-prompts-2026-05-14]]` Prompt #14 (highest-leverage prompt of the 22)
