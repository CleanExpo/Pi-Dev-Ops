---
name: marketing-analytics-attribution
description: Designs the UTM scheme, attribution model, and KPI dashboard for a campaign — before launch, not after. Use when a brief asks for "UTM", "tracking", "attribution", "analytics", "dashboard", "KPI", "ROI", "measurement plan". Outputs a UTM-builder spec, an attribution-model decision, a per-channel KPI dashboard structure, and a retro template. Composes with marketing-channel-strategist (per-channel UTM tags) and marketing-launch-runbook (gate at T-7).
automation: automatic
intents: analytics, attribution, utm, tracking, dashboard, kpi, roi, measurement-plan, marketing-analytics, post-launch-retro
---

# marketing-analytics-attribution

Owns "did this work, how did we know, where did the credit go". Always upstream of any launch — instrumenting after the fact loses the data.

## Triggers

- Brief contains "UTM", "tracking", "attribution", "analytics", "dashboard", "KPI", "ROI", "measurement", "what worked".
- Or invoked by `marketing-orchestrator` / `marketing-launch-runbook` at the T-7 gate.
- Or `marketing-campaign-planner` requests measurement plan for the named KPIs.

## Inputs

- `campaign-plan.json` (KPIs)
- `channel-plan.json` (channels needing UTM)
- `brand` slug — used as the `utm_source` namespace prefix (e.g. `synthex-li`)

## Method

### 1. UTM scheme
Single canonical pattern for the whole campaign:

| param | value pattern | example |
|---|---|---|
| `utm_source` | `{brand-slug}-{channel}` | `synthex-linkedin` |
| `utm_medium` | platform-native medium | `social-organic` / `social-paid` / `email` / `cpc` / `referral` |
| `utm_campaign` | `{jobId}` | `synthex-launch-2026-04-28` |
| `utm_content` | `{asset-slot-id}` | `lp-1` / `email-3` / `explainer-60s` |
| `utm_term` | (paid only) keyword id | `synthetic-data-mlops` |

A small Node helper at `marketing-studio/scripts/utm-builder.ts` produces the URL given any combination — calling project imports it or pastes the generated URL.

### 2. Attribution model
Pick one for the campaign + document why:

- **First-touch** — credit the first channel that brought the user. Use for awareness campaigns.
- **Last-touch** — credit the last channel before conversion. Use for direct-response.
- **Linear / time-decay** — distribute credit. Use for long sales cycles.
- **Position-based (40-20-40)** — first + middle + last. Use for product launches with multi-touch journeys (default for portfolio launches).

Document the decision + tradeoffs in the attribution doc. No silent defaults.

### 3. KPI dashboard structure
For each campaign KPI from `campaign-plan.keyResults`, define:
- Metric source (GA4 / PostHog / LinkedIn ads / Resend / Stripe / manual).
- Refresh cadence (real-time / daily / weekly).
- Owner (who watches it).
- Threshold for alert (e.g. "demo-booking rate falls below 1% during launch week").

Output a dashboard SPEC (which tiles, which queries, which sources) — not the dashboard itself. The user wires it in their tool of choice (PostHog Insights, Looker Studio, GA4 explorations).

### 4. Pre-launch instrumentation checklist (T-7 gate)
Hard-stop checks the launch-runbook gate consults:
- Every channel UTM-tagged.
- Every landing page has GA4 + PostHog snippet.
- Every email sequence has UTM-tagged links.
- Every paid ad has utm_term set per keyword.
- Every video CTA has a UTM-tagged URL (passed to `remotion-screen-storyteller` / `remotion-composition-builder`).

If any check fails, runbook gate blocks launch.

### 5. Post-launch retro template
At T+30, emit a retro doc with:
- KR vs target (numbers).
- Channel ROI ranking.
- Attribution-credited revenue / pipeline.
- 3 surprises (positive + negative).
- 3 things to do differently next campaign.

## Output

`<calling-project>/.marketing/analytics/{jobId}/`:
- `utm-scheme.md` — the canonical pattern + 1 worked example per channel.
- `attribution-model.md` — chosen model + rationale.
- `dashboard-spec.json` — tile-by-tile spec.
- `prelaunch-checklist.md` — used by runbook gate.
- `retro-template.md` — for T+30.

## Boundaries

- Never default-pick an attribution model silently — make the user/agent confirm.
- Never produce a dashboard with metrics not tied to the campaign's stated KRs.
- Never UTM-tag an internal-only or test URL in production tracking — pollutes the data.
- Never recommend tracking pixels that conflict with the brand's stated privacy posture (e.g. never recommend Meta Pixel for a brand whose `BrandConfig.doNot` includes PII concerns).

## Hands off to

- `marketing-launch-runbook` (T-7 gate consults the prelaunch checklist)
- `marketing-copywriter` (every CTA URL passes through utm-builder)
- `marketing-social-content` (every social post link wraps in utm)
- `remotion-orchestrator` (every CTA URL on a video is utm-tagged)

## Per-project keys

- `GOOGLE_ANALYTICS_PROPERTY_ID` — for dashboard wiring spec. Missing → produces tool-agnostic spec.
- `POSTHOG_API_KEY` / `POSTHOG_HOST` — same. Missing → produces spec without IDs.
- `STRIPE_API_KEY` — for revenue attribution tile. Missing → revenue tile flagged "needs Stripe".
- No keys block the design output — the spec is always emitted; only the auto-wire helpers degrade.
