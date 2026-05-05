---
name: marketing-campaign-planner
description: Designs an end-to-end marketing campaign — objectives, audience, channels, creative concept, timeline, budget, success metrics — for any portfolio or customer brand. Use when a brief asks for a "campaign", "marketing plan", "promo", "GTM motion", or "launch plan" beyond a single artifact. Triggered by marketing-orchestrator wave 1 or directly by name. Produces a structured Campaign Plan markdown + JSON consumed by every downstream marketing skill.
automation: automatic
intents: campaign, marketing-plan, promo-campaign, marketing-strategy, marketing-budget, success-metrics
---

# marketing-campaign-planner

Translates a fuzzy ambition ("we need to grow Synthex on LinkedIn") into a structured campaign with measurable goals, defined audience, channel mix, creative pillars, calendar, budget, and KPIs.

## Triggers

- Brief contains "campaign", "marketing plan", "promo", "GTM motion", "launch plan", "growth motion".
- Or invoked by `marketing-orchestrator` for any non-single-artifact job.

## Inputs

- `brand` — slug from the shared `BrandConfig` (DR / NRPG / RA / CARSI / CCW / Synthex / Unite / customer).
- `goal` — primary objective in plain English.
- `constraints` (optional) — budget ceiling, deadline, team size, prohibited tactics.
- `priorOutputs` (optional) — last 3 campaigns' attribution data if available.

## Method

1. **Read the brand**. Load `BrandConfig` from `Synthex/packages/brand-config/src/brands/{slug}.ts` (migrated from `Pi-Dev-Ops/remotion-studio/src/brands/` per RA-1985). Treat `voice`, `audience`, `forbiddenWords`, `tagline`, `defaultChannel` as the constitution — never violate.
2. **Convert goal → objectives**. Apply OKR shape: Objective is qualitative, 3-5 Key Results are measurable + time-bound. Reject any KR without a unit and a date.
3. **Audience layering**. Primary audience inherits from `BrandConfig.audience.primary`. Layer in: campaign-specific persona, JTBD, current vs. target perception. Defer deep work to `marketing-icp-research`.
4. **Channel mix**. Defer to `marketing-channel-strategist` for the cadence and per-channel spec — this skill only sets the channel SHORTLIST and budget split.
5. **Creative concept**. One-sentence positioning hook + one campaign tagline + 3-5 creative pillars. Defer to `marketing-positioning` for upstream value-prop work.
6. **Calendar**. Map deliverables onto a week-by-week (campaign <30d) or sprint-by-sprint (campaign >30d) timeline. Mark dependencies.
7. **Budget**. If a budget is provided, allocate by channel based on expected CAC. If not, propose three tiers (lean / target / aggressive) with rationale.
8. **KPIs + measurement plan**. Defer to `marketing-analytics-attribution` for UTM + attribution; this skill names the KPIs.

## Output

Two artifacts (templates at `marketing-studio/templates/campaign-brief.md`):

1. `marketing-studio/.research/campaigns/{jobId}/campaign-plan.md` — human-readable.
2. `marketing-studio/.research/campaigns/{jobId}/campaign-plan.json` — structured:

```jsonc
{
  "jobId": "synthex-launch-...",
  "brand": "synthex",
  "objective": "Establish Synthex as the default synthetic-data infrastructure for ML platform teams",
  "keyResults": [
    { "metric": "qualified demos booked", "target": 25, "by": "2026-06-01" },
    { "metric": "LinkedIn impressions on launch posts", "target": 250000, "by": "2026-05-15" },
    { "metric": "trial sign-ups", "target": 100, "by": "2026-06-01" }
  ],
  "audience": { "primary": "...", "secondary": "...", "JTBD": "..." },
  "channelShortlist": ["linkedin", "youtube", "email", "partnerships"],
  "creativeConcept": { "hook": "...", "tagline": "...", "pillars": ["...", "...", "...", "..."] },
  "calendar": [{ "week": 1, "deliverables": ["positioning-doc", "icp-research"] }, ...],
  "budget": { "tier": "target", "allocation": { "linkedin": 0.4, "youtube": 0.3, "email": 0.1, "partnerships": 0.2 }, "totalUSD": 15000 },
  "kpis": ["demos-booked", "trial-signups", "linkedin-CTR", "email-open-rate"]
}
```

## Boundaries

- Never set KRs without a numeric target and a date.
- Never propose channels the brand has no presence on without flagging it as a stretch + the cost of building presence.
- Never invent budgets — if user gave none, return three tiers, not one assumed number.
- Never overwrite `BrandConfig` voice or audience — propose changes via `remotion-brand-codify`.

## Hands off to

- `marketing-positioning` (refines hook + tagline)
- `marketing-icp-research` (deepens audience)
- `marketing-channel-strategist` (channel cadence + per-channel spec)
- `marketing-seo-researcher` (if any organic-search channel is in shortlist)
- `marketing-copywriter` / `marketing-social-content` (content creation)
- `marketing-launch-runbook` (if campaignType is `product-launch`)
- `remotion-orchestrator` (cross-pack: any video deliverable)
- `marketing-analytics-attribution` (UTM + dashboard before launch)

## Per-project keys

Reads `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` from calling project's env for any LLM-driven KR refinement. No keys → emits a manual-fill template.
