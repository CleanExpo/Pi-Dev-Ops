---
name: marketing-icp-research
description: Builds an Ideal Customer Profile (ICP) — firmographics, role, pains, triggers, vocabulary, watering holes, decision process — for a brand or feature. Use when a brief asks for "ICP", "target audience", "buyer persona", "customer research", "user research", or before any campaign / copy / channel work. Reads BrandConfig.audience as the seed; outputs structured ICP consumed by copywriter, channel-strategist, seo-researcher.
automation: automatic
intents: icp, ideal-customer-profile, target-audience, buyer-persona, customer-research, user-research, audience-research
---

# marketing-icp-research

Owns "who exactly buys, what they call the problem, where they hang out, who else they listen to". Foundation for copy + channel + SEO.

## Triggers

- Brief contains "ICP", "target audience", "buyer persona", "customer research", "audience".
- Or invoked by `marketing-orchestrator` / `marketing-campaign-planner` early in a campaign.
- Or no ICP doc exists for the brand under `marketing-studio/.research/icp/{slug}-{date}.md`, or the latest is >180 days old.

## Inputs

- `brand` slug
- `feature` (optional) — if researching for a specific feature's adopter segment
- `seed` (optional) — known customers / quotes / interview transcripts
- `competitorReviews` (optional) — G2 / Capterra review URLs to mine for vocabulary

## Method

1. **Seed from BrandConfig**. `audience.primary` and `audience.secondary` are the starting hypothesis; this skill validates and deepens them.
2. **Firmographic / demographic block**:
   - B2B: industry, company size (employees, revenue), funding stage, tech stack, geography.
   - B2C: age, income, life-stage, geography, behaviour cohort.
3. **Role block** (B2B only):
   - Decision maker (signs the cheque) vs. champion (drives the project) vs. user (touches the tool) vs. blocker (legal / security / procurement).
   - Each role: title variants, seniority, KPIs they're measured on.
4. **Pain hierarchy** — list 5-10 pains, then RANK by:
   - Frequency (daily / weekly / monthly / annual)
   - Severity (cost of not solving, in money or time)
   - Awareness (does the customer already articulate this pain or only realise it after?)
5. **Trigger events** — concrete moments that move someone from "aware of pain" to "actively shopping". E.g. for Synthex: "model accuracy regression in prod", "auditor flags PII in training set", "new compliance regime announced".
6. **Vocabulary mining** — exact phrases the customer uses, not the seller's terms. Pull from review sites, Reddit, Slack communities, sales-call transcripts. Tag each with frequency.
7. **Watering holes** — places this ICP gathers, in priority order. Newsletters, podcasts, conferences, Slack/Discord communities, sub-Reddits, LinkedIn creators they follow.
8. **Buying process** — step-by-step from trigger to signed contract. Average length, gates, common objections, deal-breakers.
9. **Anti-ICP** — who LOOKS like a fit but is wrong. Saves wasted ad spend.

## Output

`marketing-studio/.research/icp/{slug}-{YYYY-MM-DD}.md` (template at `marketing-studio/frameworks/icp-canvas.md`):

```markdown
# ICP — {brand}{ - feature?}
Date: 2026-04-28

## Firmographics / demographics
…

## Roles
- Decision maker: …
- Champion: …
- User: …
- Blocker: …

## Pain hierarchy
1. {pain} — frequency / severity / awareness
2. …

## Trigger events
- …

## Vocabulary (exact phrases)
| Phrase | Frequency | Source |
| --- | --- | --- |
| "model drift in prod" | high | r/MachineLearning, G2 reviews |
| … | … | … |

## Watering holes
1. {newsletter / podcast / community} — why
2. …

## Buying process
1. Trigger → …
2. Awareness → …
3. Evaluation → …
4. Decision → …
5. Procurement → …

## Anti-ICP
- {segment} — looks similar but {why wrong}
```

Plus structured JSON sibling.

## Boundaries

- Never invent customer quotes. If sources are thin, label fields "needs primary research" and propose 5 customer interviews.
- Never use `BrandConfig.audience` as the final answer — it's the seed, this skill is the validation.
- Never mix B2B and B2C frameworks in the same doc.
- Never publish an ICP without an Anti-ICP section.

## Hands off to

- `marketing-copywriter` (uses vocabulary + pains for hooks and headlines)
- `marketing-channel-strategist` (uses watering holes for channel selection)
- `marketing-seo-researcher` (uses vocabulary as keyword seed)
- `marketing-positioning` (refines value prop with the validated pain hierarchy)

## Per-project keys

- `PERPLEXITY_API_KEY` — review-site scraping, community mining. Missing → produces seed-only doc with explicit "fill via interviews" placeholders.
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` — vocabulary clustering, pain ranking. Missing → returns raw extracts.
