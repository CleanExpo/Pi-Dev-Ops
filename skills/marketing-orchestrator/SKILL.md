---
name: marketing-orchestrator
description: ENTRY POINT for the Marketing Skills Package. Use the moment a brief mentions "marketing skills package", "marketing package", "use marketing", "campaign", "launch", "positioning", "go-to-market", "GTM", "marketing strategy", "marketing plan", or asks to produce marketing assets (landing page, ad creative, blog post, email sequence, launch runbook, social content) for one of the portfolio brands (DR, NRPG, RestoreAssist/RA, CARSI, CCW, Synthex, Unite) or any customer brand. Globally available at ~/.claude/skills/marketing-* (symlinked to /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/skills/marketing-*). Reads the brief, classifies (campaign type, brand, audience, channel mix, budget, timeline), emits a wave-plan JSON, dispatches sub-skills in topological order. Composes with the Remotion Skills Package — calls remotion-orchestrator for any video output.
automation: automatic
intents: marketing, campaign, launch, gtm, go-to-market, positioning, value-prop, icp, target-audience, channel-strategy, content-strategy, ad-copy, landing-page, email-sequence, blog-post, seo, attribution, marketing-skills-package
---

# marketing-orchestrator — Marketing Skills Package entry point

Single entry point for the Marketing Skills Package — 10 sibling skills (`marketing-orchestrator`, `marketing-campaign-planner`, `marketing-positioning`, `marketing-icp-research`, `marketing-channel-strategist`, `marketing-copywriter`, `marketing-seo-researcher`, `marketing-social-content`, `marketing-launch-runbook`, `marketing-analytics-attribution`) installed globally at `~/.claude/skills/marketing-*` (symlinked to `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/skills/marketing-*`). Available in every project, not just Pi-Dev-Ops.

## Invocation

The user can invoke the package by:
- Saying any of: **"use the Marketing Skills Package"**, **"marketing package"**, **"use marketing"**.
- Naming any individual skill (e.g. *"use marketing-copywriter for the landing page"*).
- Submitting a brief that names a marketing artifact: `"campaign for X"`, `"launch plan for Y"`, `"GTM strategy for Z"`, `"landing page for ..."`, `"email sequence for ..."`.

## The marketing substrate

Templates, frameworks, and per-job artifacts live at:

```
/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/marketing-studio/
├── templates/         — campaign-brief, launch-runbook, email-sequence, landing-spec, …
├── frameworks/        — JTBD canvas, positioning canvas, ICP canvas, AIDA, PAS
├── scripts/           — UTM builder, attribution helpers
├── .research/         — per-job artifacts (campaigns/, icp/, seo/, wave-plans/)
└── outputs/           — fallback when calling project has no .marketing/ dir
```

Brand voice / forbidden words / audience / tagline read from the **shared** `BrandConfig` files at `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/remotion-studio/src/brands/{slug}.ts` — single source of truth across both packs. No duplication.

## Output

A wave plan JSON written to `marketing-studio/.research/wave-plans/{job_id}.json`:

```jsonc
{
  "jobId": "synthex-launch-2026-04-28T15-30-00",
  "brand": "synthex",
  "campaignType": "product-launch",
  "audience": "ML engineers and platform teams",
  "channels": ["linkedin", "youtube", "email"],
  "durationDays": 30,
  "deliverables": ["positioning-doc", "icp-research", "landing-spec", "email-sequence", "launch-runbook", "video-assets"],
  "linear": { "teamId": "...", "projectId": "..." },
  "outputDir": "/Users/phill-mac/Pi-CEO/Synthex/.marketing/",
  "waves": [
    { "id": 1, "parallel": [
      { "skill": "marketing-positioning" },
      { "skill": "marketing-icp-research" }
    ]},
    { "id": 2, "parallel": [
      { "skill": "marketing-channel-strategist" },
      { "skill": "marketing-seo-researcher" }
    ]},
    { "id": 3, "parallel": [
      { "skill": "marketing-copywriter", "args": { "artifact": "landing-spec" } },
      { "skill": "marketing-copywriter", "args": { "artifact": "email-sequence" } },
      { "skill": "marketing-social-content", "args": { "channels": ["linkedin", "x"] } }
    ]},
    { "id": 4, "parallel": [
      { "skill": "remotion-orchestrator", "args": { "composition": "Explainer", "channel": "linkedin", "durationSec": 60 } },
      { "skill": "marketing-launch-runbook" },
      { "skill": "marketing-analytics-attribution" }
    ]}
  ]
}
```

## Wave-count discipline

- ≤3 waves for a single artifact (one blog post, one ad).
- ≤5 waves for a content batch (3-5 artifacts, no launch).
- ≤8 waves for a full launch (positioning → research → content → assets → runbook → attribution).

## Campaign type routing (brief → campaignType)

| Brief signal | campaignType |
|---|---|
| "launch", "go-to-market", "GTM", "ship a feature" | `product-launch` |
| "awareness", "thought leadership", "category" | `awareness` |
| "lead-gen", "demand-gen", "sales pipeline" | `demand-gen` |
| "onboarding", "activation", "trial conversion" | `lifecycle` |
| "ad", "creative", "social cut" | `paid-ads` |
| "blog post", "article", "long-form" | `content` |
| "email sequence", "drip", "nurture" | `email` |
| "landing page", "site copy" | `landing` |

## Brand resolution

Same slug map as Remotion: `dr` / `nrpg` / `ra` / `carsi` / `ccw` / `synthex` / `unite`. If the brand is unknown, dispatch `remotion-brand-research` (cross-pack call) before any marketing work — voice and forbidden-words must exist before copy gets written.

## Composition with Remotion Skills Package

When the wave plan includes any video deliverable, `marketing-orchestrator` does NOT author video itself. It calls `remotion-orchestrator` with a fully-formed sub-brief: `{brand, composition, channel, durationSec, topic}`. The Remotion pack handles storyboard / motion / render. Marketing pack handles strategy / copy / non-video.

## Per-project usage model

The package is shared infrastructure; each calling project supplies its own runtime config and API keys.

| Concern | Where it lives |
|---|---|
| Skill definitions | `~/.claude/skills/marketing-*` (symlinked → `Pi-Dev-Ops/skills/marketing-*`) — globally available |
| Substrate (templates, frameworks) | `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/marketing-studio/` |
| Brand configs | `Pi-Dev-Ops/remotion-studio/src/brands/{slug}.ts` — shared with Remotion pack |
| API keys | The **calling project's** `.env` / `.env.local` |
| Output | `<calling-project>/.marketing/` by default; falls back to `marketing-studio/outputs/{job-id}/` |

Per-project env keys (graceful degradation when absent):
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — copy + research LLM calls.
- `PERPLEXITY_API_KEY` — ICP + SEO + competitor research (skip with warning if missing).
- `RESEND_API_KEY` / `MAILCHIMP_API_KEY` — actual email send (skip; produce drafts only).
- `LINEAR_API_KEY` — campaign tickets.
- `GOOGLE_ANALYTICS_PROPERTY_ID` / `POSTHOG_API_KEY` — attribution dashboards.

## What this skill does NOT do

- Does not author copy — that's `marketing-copywriter`.
- Does not run keyword research — that's `marketing-seo-researcher`.
- Does not render video — that's `remotion-orchestrator` (cross-pack call).

It only plans + delegates.

## Adding a new campaign type

1. Add a row to the routing table above.
2. Define the wave plan template for that type (which skills, in what order).
3. Document in `PACKAGE.md`.
