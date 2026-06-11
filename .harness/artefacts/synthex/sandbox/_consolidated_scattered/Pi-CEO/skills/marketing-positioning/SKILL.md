---
name: marketing-positioning
description: Develops value proposition, competitive positioning, and Jobs-to-be-Done articulation for a brand or feature. Use when a brief asks for "positioning", "value prop", "messaging", "JTBD", "competitive analysis", "category creation", or before any landing page or campaign starts. Reads the brand's existing voice and audience from BrandConfig; produces positioning artifacts every downstream copywriter / strategist skill consumes.
automation: automatic
intents: positioning, value-prop, value-proposition, messaging, jtbd, jobs-to-be-done, competitive-analysis, category-creation, differentiation
---

# marketing-positioning

Owns "what this brand stands for and why it wins". Not channel (channel-strategist), not copy (copywriter) — the prior decision both depend on.

## Triggers

- Brief contains "positioning", "value prop", "messaging", "JTBD", "competitive analysis", "differentiate", "stand out", "category".
- Or invoked by `marketing-orchestrator` / `marketing-campaign-planner` upstream of copy work.
- Or `BrandConfig.tagline` is missing / generic / older than 6 months.

## Inputs

- `brand` slug
- `feature` (optional) — if positioning a specific feature within the brand, not the whole brand
- `competitorList` (optional) — explicit competitor URLs / names; otherwise derived
- `targetCustomer` (optional) — if narrower than `BrandConfig.audience.primary`

## Method

1. **Read the constitution**. Load `BrandConfig` for the brand. Existing `tagline`, `voice.tone`, `doNot` are inviolable.
2. **Apply the April Dunford framework**:
   - Competitive alternatives (what the customer would do otherwise — including doing nothing)
   - Unique attributes (capabilities only this brand has)
   - Value (the BENEFIT customers extract from those attributes)
   - Best fit customer characteristics (the segment where the value is highest)
   - Market category (the frame of reference for evaluation)
3. **JTBD canvas** at `marketing-studio/frameworks/jtbd-canvas.md` template:
   - Functional job, emotional job, social job
   - Trigger (what causes the customer to look)
   - Anxiety / inertia (what stops them)
   - Push / pull forces (Christensen forces of progress)
4. **Value proposition statement** in this exact shape:
   *"For [target customer] who [need / pain], [brand/feature] is a [category] that [unique value]. Unlike [competitive alternative], [brand/feature] [primary differentiator]."*
5. **Messaging hierarchy** (3 levels):
   - Tier 1: One-line tagline (≤7 words). May reuse `BrandConfig.tagline` if still strong.
   - Tier 2: Three pillars (≤10 words each).
   - Tier 3: Proof points per pillar (numbers, customer quotes, case study refs).
6. **Anti-positioning**. Explicitly list 3 things the brand is NOT, and what it does NOT promise. Prevents copywriters from drifting.
7. **Competitive map**. 2x2 matrix on the two most decision-critical axes (e.g. for Synthex: "data realism" × "platform integration depth"). Plot competitors.

## Output

`marketing-studio/.research/campaigns/{jobId}/positioning.md`:

```markdown
# Positioning — {brand}{ - feature?}

## Value Proposition
For {targetCustomer} who {pain}, {brand/feature} is a {category} that {value}. Unlike {alternative}, {brand/feature} {differentiator}.

## JTBD
- Functional: …
- Emotional: …
- Social: …

## Messaging hierarchy
- Tier 1 (tagline): …
- Tier 2 (pillars): 1. … 2. … 3. …
- Tier 3 (proof points): …

## Anti-positioning
- NOT a {generic alternative}
- Does NOT promise {overreach}
- Does NOT serve {wrong segment}

## Competitive map (2×2)
Axes: {axis1} × {axis2}
- {brand}: high/high
- {competitor 1}: …
- {competitor 2}: …
```

Plus a structured JSON sibling with the same fields for downstream skills.

## Boundaries

- Never change `BrandConfig.tagline` from this skill — propose via `remotion-brand-codify` PR.
- Never claim "category creation" without naming the category and the prior frame customers will arrive with.
- Never ship a value prop that hides the price-point segment (premium / mid / budget) — copywriter needs to know.
- Never copy a competitor's positioning verbatim. Reference it; differentiate from it.

## Hands off to

- `marketing-copywriter` (every long-form asset reads this doc first)
- `marketing-social-content` (taglines + pillars become post hooks)
- `marketing-launch-runbook` (positioning is the launch announcement skeleton)

## Per-project keys

`PERPLEXITY_API_KEY` for competitor scraping. Missing → returns a "needs-input" placeholder for the competitive map and continues the rest.
