---
name: marketing-orchestrator
description: ENTRY POINT for the Marketing Skills Package. Use the moment a brief mentions "marketing skills package", "marketing package", "use marketing", "campaign", "launch", "positioning", "go-to-market", "GTM", "marketing strategy", "marketing plan", or asks to produce marketing assets (landing page, ad creative, blog post, email sequence, launch runbook, social content) for one of the portfolio brands (DR, NRPG, RestoreAssist/RA, CARSI, CCW, Synthex, Unite) or any customer brand. Globally available at ~/.claude/skills/marketing-* (symlinked to /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/skills/marketing-*). Reads the brief, classifies (campaign type, brand, audience, channel mix, budget, timeline), emits a wave-plan JSON, dispatches sub-skills in topological order. Composes with the Remotion Skills Package — calls remotion-orchestrator for any video output.
automation: automatic
intents: marketing, campaign, launch, gtm, go-to-market, positioning, value-prop, icp, target-audience, channel-strategy, content-strategy, ad-copy, landing-page, email-sequence, blog-post, seo, attribution, marketing-skills-package
---

# marketing-orchestrator — Marketing Skills Package entry point

Single entry point for the Marketing Skills Package — 10 sibling skills (`marketing-orchestrator`, `marketing-campaign-planner`, `marketing-positioning`, `marketing-icp-research`, `marketing-channel-strategist`, `marketing-copywriter`, `marketing-seo-researcher`, `marketing-social-content`, `marketing-launch-runbook`, `marketing-analytics-attribution`) installed globally at `~/.claude/skills/marketing-*` (symlinked to `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/skills/marketing-*`). Available in every project, not just Pi-Dev-Ops.

## Discovery brief gate (turn 1, mandatory)

Adopted from `nexu-io/open-design` (Apache-2.0). Before *any* sub-skill is dispatched, the orchestrator emits a structured brief and refuses to proceed until every required field is filled. No "I'll work it out as I go" — the brief locks scope and prevents downstream skills from inventing audience, tone, or channel mid-stream.

### Required fields

| Field | Type | Notes |
|---|---|---|
| `brand` | `BrandSlug` | Must resolve in `remotion-studio/src/brands/`. Unknown brand → dispatch `remotion-brand-research` first; do not guess. |
| `surface` | `landing` \| `email` \| `social` \| `video` \| `blog` \| `ad` \| `mixed` | The artifact type. |
| `audience` | string | One sentence describing who reads this. Vagueness ("decision-makers") is rejected — must name role + context. |
| `tone` | array | Subset of brand's `voice.tone`. Cannot include any tone outside the brand's allowed set. |
| `channels` | array | Subset of `linkedin` / `youtube` / `instagram` / `tiktok` / `x` / `email` / `web`. |
| `scale` | `single` \| `batch` \| `launch` | Drives wave-count discipline (≤3 / ≤5 / ≤8 waves respectively). |
| `outcome` | string | One sentence on the campaign's measurable goal. "Awareness" alone is rejected — must say "+X% to Y over Z weeks" or equivalent. |

Optional but recommended: `topic`, `competitors`, `forbiddenAngles`, `linearTicket`.

### Hard stop conditions

- Any required field missing or vague → orchestrator returns the brief with `blocked: true` and a per-field reason. Founder fills in, re-runs.
- `tone` includes a value outside the brand's `voice.tone` → block.
- `outcome` is unfalsifiable ("be impactful") → block.

This is the single most reliable lever to keep downstream wave plans short and sub-skills focused. Do not relax it.

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

## 5-D critique gate (mandatory before final wave emission)

Adopted from `nexu-io/open-design` (Apache-2.0). After the final wave's deliverables land in `<calling-project>/.marketing/{job_id}/`, spawn an Opus 4.7 subagent via `opus-adversary` to score the campaign across five dimensions, each 0–10 with cited evidence:

1. **Philosophy consistency** — does the campaign carry one positioning thesis through every artifact (landing page hook, email sequence opening line, social hook, video script)? Cite the thesis from `marketing-positioning` output and check each artifact echoes it.
2. **Visual hierarchy** — across artifacts, does the eye land on the same hero stat/promise first? Cite which artifact breaks the order.
3. **Detail execution** — UTMs present and parameterised, no broken anchors, no AI-filler words leaked through, no "We/Our/I/Us/My" lead-ins (per Pi-CEO content rule).
4. **Functionality** — does the channel mix actually serve the audience surfaced by `marketing-icp-research`? Email cadence within sustainable bounds set by `marketing-channel-strategist`?
5. **Innovation** — one campaign move that earns memory (specific stat, contrarian framing, unusual CTA), or generic-launch median?

### Pass / fail

- **Pass**: every dimension ≥ 6 AND mean ≥ 7 → wave plan emits, Linear ticket opens.
- **Fail**: any ≤ 5 OR mean < 7 → loop back: assign Fix list to the responsible sub-skill (positioning / copywriter / channel-strategist / social-content) and re-run that wave only.
- **Override**: founder may force-pass via explicit message. Logged to `marketing-studio/.research/wave-plans/{job_id}.critique.json`.

Use `opus-adversary` for the spawn — do not write a parallel harness. The critique JSON sits beside the wave plan; the founder reviews before any external dispatch (paid ads, scheduled email blast, Linear publication).
