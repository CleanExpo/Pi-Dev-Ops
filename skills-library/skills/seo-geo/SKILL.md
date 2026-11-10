---
name: seo-geo
description: Optimize content for AI Overviews (formerly SGE), ChatGPT web search, Perplexity, and other AI-powered search experiences. Generative Engine Optimization (GEO) analysis including brand mention signals, AI crawler accessibility, llms.txt compliance, passage-level citability scoring, and platform-specific optimization. Use when user says "AI Overviews", "SGE", "GEO", "AI search", "LLM optimization", "Perplexity", "AI citations", "ChatGPT search", or "AI visibility".
---

# AI Search / GEO Optimization

## Key Statistics

| Metric | Value | Source |
|--------|-------|--------|
| AI Overviews reach | 1.5 billion users/month across 200+ countries | Google |
| AI Overviews query coverage | 50%+ of all queries | Industry data |
| AI-referred sessions growth | 527% (Jan-May 2025) | SparkToro |
| ChatGPT weekly active users | 900 million | OpenAI |
| Perplexity monthly queries | 500+ million | Perplexity |

## Critical Insight: Brand Mentions > Backlinks

**Brand mentions correlate 3× more strongly with AI visibility than backlinks.**
(Ahrefs December 2025 study of 75,000 brands)

| Signal | Correlation with AI Citations |
|--------|------------------------------|
| YouTube mentions | ~0.737 (strongest) |
| Reddit mentions | High |
| Wikipedia presence | High |
| LinkedIn presence | Moderate |
| Domain Rating (backlinks) | ~0.266 (weak) |

**Only 11% of domains** are cited by both ChatGPT and Google AI Overviews for the same query — platform-specific optimization is essential.

---

## GEO Analysis Criteria

Score five weighted areas: Citability (25%), Structural Readability (20%), Multi-Modal Content (15%), Authority & Brand Signals (20%), Technical Accessibility (20%). AI crawlers do not execute JavaScript, so server-side rendering is critical.

Read [references/criteria.md](references/criteria.md) when scoring a page: strong and weak signals per area, optimal passage length (134-167 words) and citation-source statistics.

## Crawlers and Standards

Read [references/crawlers-and-standards.md](references/crawlers-and-standards.md) when checking robots.txt for AI crawlers (GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot, CCBot and others), or when checking, writing or recommending `/llms.txt` and RSL 1.0 licensing terms.

---

## Platform-Specific Optimization

| Platform | Key Citation Sources | Optimization Focus |
|----------|---------------------|-------------------|
| **Google AI Overviews** | Top-10 ranking pages (92%) | Traditional SEO + passage optimization |
| **ChatGPT** | Wikipedia (47.9%), Reddit (11.3%) | Entity presence, authoritative sources |
| **Perplexity** | Reddit (46.7%), Wikipedia | Community validation, discussions |
| **Bing Copilot** | Bing index, authoritative sites | Bing SEO, IndexNow |

---

## Output

Generate `GEO-ANALYSIS.md` with:

1. **GEO Readiness Score: XX/100**
2. **Platform breakdown** (Google AIO, ChatGPT, Perplexity scores)
3. **AI Crawler Access Status** (which crawlers allowed/blocked)
4. **llms.txt Status** (present, missing, recommendations)
5. **Brand Mention Analysis** (presence on Wikipedia, Reddit, YouTube, LinkedIn)
6. **Passage-Level Citability** (optimal 134-167 word blocks identified)
7. **Server-Side Rendering Check** (JavaScript dependency analysis)
8. **Top 5 Highest-Impact Changes**
9. **Schema Recommendations** (for AI discoverability)
10. **Content Reformatting Suggestions** (specific passages to rewrite)

---

## Quick Wins

1. Add "What is [topic]?" definition in first 60 words
2. Create 134-167 word self-contained answer blocks
3. Add question-based H2/H3 headings
4. Include specific statistics with sources
5. Add publication/update dates
6. Implement Person schema for authors
7. Allow key AI crawlers in robots.txt

## Medium Effort

1. Create `/llms.txt` file
2. Add author bio with credentials + Wikipedia/LinkedIn links
3. Ensure server-side rendering for key content
4. Build entity presence on Reddit, YouTube
5. Add comparison tables with data
6. Implement FAQ sections (structured, not schema for commercial sites)

## High Impact

1. Create original research/surveys (unique citability)
2. Build Wikipedia presence for brand/key people
3. Establish YouTube channel with content mentions
4. Implement comprehensive entity linking (sameAs across platforms)
5. Develop unique tools or calculators

## Ship gate (Prove mode)

When this skill changes something that already exists in a way a person would judge (wording, behaviour,
design, a model or prompt, a cost line), the change ships only after it beats the current version. Call the
Skill tool with "gauntlet-loop" and follow its Prove mode. Mechanical fixes that a hard check proves (a
broken link repaired, a failing test made to pass) do not need it.
