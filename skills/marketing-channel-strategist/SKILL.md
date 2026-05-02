---
name: marketing-channel-strategist
description: Selects the channel mix and per-channel cadence for a campaign — LinkedIn, YouTube, X, email, paid ads, SEO, partnerships, podcasts, communities. Use when a brief asks "what channel", "where should we post", "channel strategy", "cadence", or upstream of any content production. Reads BrandConfig.defaultChannel and ICP watering-holes; outputs a per-channel spec consumed by copywriter, social-content, copywriter, and remotion-orchestrator (channel sets aspect ratio / duration).
automation: automatic
intents: channel-strategy, channel-mix, cadence, distribution-strategy, where-to-post, content-calendar
---

# marketing-channel-strategist

Owns "where this content runs and how often". Bridges strategy (campaign-planner) and production (copywriter / social-content / remotion).

## Triggers

- Brief contains "channel", "where", "distribution", "cadence", "calendar", "frequency".
- Or invoked by `marketing-orchestrator` / `marketing-campaign-planner` after positioning + ICP exist.

## Inputs

- `brand` slug
- `campaignType` — from campaign-planner (`product-launch` | `awareness` | `demand-gen` | `lifecycle` | `paid-ads` | `content` | `email` | `landing`)
- `audience` / `ICP` — from `marketing-icp-research`
- `budgetUSD` (optional) — for paid channels
- `durationDays` — campaign window

## Method

1. **Read the constitution**. `BrandConfig.defaultChannel` is the safe-default starting channel. Override only with explicit reason in the output.
2. **Match channels to ICP watering-holes**. If ICP says "follows {newsletter X}", that newsletter / its host platform / its sponsor inventory is in the shortlist. Don't propose channels with no ICP signal.
3. **Apply campaignType matrix**:
   - `product-launch` → owned (blog + email) + earned (PR + community) + paid (LinkedIn + retargeting). 4-6 channels.
   - `awareness` → organic content (LinkedIn / X / YouTube long) + SEO. 3-4 channels.
   - `demand-gen` → paid ads + landing-page funnel + email nurture. 2-3 channels.
   - `lifecycle` → email sequences + in-product. 1-2 channels.
   - `content` → primary owned channel + 1-2 syndication. 2-3.
4. **Per-channel spec** — for each channel, set:
   - **Asset type** (post / thread / long-form / short-form video / ad / email / page)
   - **Frequency** (per week or per campaign)
   - **Cadence pattern** (front-loaded / steady / climax-on-launch-day)
   - **Format** (text / carousel / video / live)
   - **CTA per post type**
   - **For video channels** — pass through to `remotion-orchestrator` with explicit aspectRatio + durationSec (LinkedIn 1920×1080, IG/TikTok 1080×1920, YouTube long 1920×1080).
5. **Kill list**. Channels deliberately NOT used and why (cost, mismatch with ICP, brand voice clash, regulatory).
6. **Cross-channel sequencing** — which content drops first, what pulls forward to other channels (e.g. blog post → 3 LinkedIn posts → 1 email → 1 video).

## Output

`marketing-studio/.research/campaigns/{jobId}/channel-plan.md` + JSON:

```jsonc
{
  "primaryChannel": "linkedin",
  "channels": [
    {
      "channel": "linkedin",
      "assetTypes": ["text-post", "carousel", "video"],
      "frequency": { "perWeek": 3, "totalCampaign": 12 },
      "cadence": "steady-with-launch-day-spike",
      "videoSpec": { "aspectRatio": "1920x1080", "durationSec": 60, "composition": "Explainer" },
      "cta": "demo-booking-form"
    },
    { "channel": "email", "assetTypes": ["sequence"], "frequency": { "totalCampaign": 5 }, ... },
    { "channel": "youtube-long", ... }
  ],
  "killList": [
    { "channel": "tiktok", "reason": "ICP for Synthex shows zero TikTok signal; brand voice mismatch (technical/expert)" }
  ],
  "sequencing": [
    { "day": 0, "drops": ["positioning-blog-post"] },
    { "day": 2, "drops": ["linkedin-post-1", "email-1"] },
    { "day": 7, "drops": ["explainer-video", "linkedin-post-2"] }
  ]
}
```

## Boundaries

- Never recommend a channel without a watering-hole or budget signal. "LinkedIn always works" is not analysis.
- Never set frequency above sustainable (e.g. 7 LinkedIn posts/week from a brand with no posting history).
- Never assign a video deliverable without naming the Remotion composition + aspect ratio.
- Never silently swap brand `defaultChannel` — flag override + reason.

## Hands off to

- `marketing-copywriter` (per-asset copy for each channel slot)
- `marketing-social-content` (short-form posts)
- `remotion-orchestrator` (video assets — pass channel + aspectRatio + durationSec)
- `marketing-launch-runbook` (sequencing becomes the runbook timeline)
- `marketing-analytics-attribution` (UTM scheme per channel)

## Per-project keys

- `PERPLEXITY_API_KEY` — community / newsletter discovery. Missing → falls back to ICP watering-holes only.
