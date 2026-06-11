# ADR: Synthex AI Marketing Advisor

**Status:** Proposed — awaiting Phill sign-off before Sprint 4 ends
**Date:** 2026-03-31
**Linear:** SYN-585 / SYN-582
**Author:** Claude Code (Board Session 12)

---

## Context

Synthex accumulates 6 live data streams per user (post performance, calendar scheduling, review sentiment, seasonal signals, autopilot runs, authority trajectory). In Sprint 3 and 4, these streams grow independently with no cross-stream synthesis visible to clients.

The AI Marketing Advisor is the Sprint 5 flagship: a nightly inference engine that reads all 6 streams and produces exactly 3 personalised recommended actions per user — delivered as a dashboard card and Monday morning email. The Advisor is **not a chatbot**. Intelligence is pre-computed nightly; the client sees a static brief until the following Monday.

This ADR is a design deliverable. Build happens in Sprint 5 after 6–8 weeks of production data accumulation.

---

## Decision

### 1. Data Contract

The nightly inference job queries 6 data streams per user:

```typescript
// posts — last 8 weeks: platform, content_type, engagement, predicted_engagement (SYN-583)
// calendar_posts — pending + last 14 days published
// gbp_reviews — last 30 days: sentiment, response_rate, avg_rating
// seasonal_signals — next 4 opportunity windows (industry + state)
// autopilot_runs — last 30 days: run outcomes, failure modes, manual overrides
// authority_scores — last 3 monthly: component breakdown, trajectory
```

**Minimum viable inference:** ≥ 2 populated streams required.
- If fewer: skip user, log `skip_reason = 'insufficient_data'`, do not insert row.
- `streams_available` column records how many streams had ≥ 1 row.

### 2. Inference Architecture

```
Nightly cron: Monday 06:00 AEST (20:00 UTC Sunday — 0 20 * * 0)
  For each active user:
    1. Query all 6 stream tables (parallel, service role)
    2. Count available streams → skip if < 2
    3. Build structured JSON summary (~500 tokens)
    4. Call Claude claude-haiku-4-5-20251001
       - system: see below
       - temperature: 0.3
       - max_tokens: 800
    5. Parse + validate 3-action JSON response
    6. Insert to recommended_actions
    7. trackPipelineCost('ai_advisor_inference', cost_usd, user_id)
    8. If cost > AI_ADVISOR_COST_CEILING_PER_CLIENT: skip + alert
```

**System prompt:**
```
You are the Synthex AI Marketing Advisor. A nightly inference engine for Australian SMB marketing.

Given performance data for a client, generate exactly 3 specific, actionable weekly recommendations.
Each recommendation must:
- Be grounded in actual data from the provided streams
- Have a headline of ≤ 12 words
- Have a detail of ≤ 30 words
- Assign a confidence level: High (≥4 weeks data), Medium (2-4 weeks), Exploratory (<2 weeks or cross-client only)
- Name the data source in plain English
- Optionally specify a one-tap action: "approve_post", "send_review_response", "view_calendar", or null

Output ONLY valid JSON matching the schema:
[
  { "headline": string, "detail": string, "confidence": "High"|"Medium"|"Exploratory",
    "data_source": string, "tap_action": string|null, "tap_payload": object|null },
  ...
]
```

### 3. `recommended_actions` Table Schema

See `supabase/migrations/20260331180001_recommended_actions.sql`.

Key decisions:
- Actions stored as flat columns (action_1_*, action_2_*, action_3_*) not JSONB array — enables direct SELECT without JSON parsing, typed queries, and Supabase generated types
- Uses `user_id` (not `client_id`) — matches live production schema pattern
- `week_of` is the Monday date — one row per user per week
- `inference_cost_usd` tracked for billing audit

### 4. Cost Ceiling

```typescript
const AI_ADVISOR_COST_CEILING_PER_CLIENT =
  parseFloat(process.env.AI_ADVISOR_COST_CEILING_PER_CLIENT ?? '0.50')

// AUD conversion: cost_usd * 1.55 (approximate)
// Per monthly cycle: if cumulative spend for user_id > ceiling this month, skip
// At ceiling: insert row with skip_reason = 'cost_ceiling_reached', no inference call
```

Target: < $0.50 AUD/user/month. At 500 users = $250/month.

**Weekly estimate per user:**
- Input tokens: ~500 (6 stream summaries)
- Output tokens: ~200 (3 actions)
- claude-haiku-4-5 pricing: ~$0.001 per call
- Monthly (4 calls): ~$0.004 USD (~$0.006 AUD) — well within $0.50 ceiling

### 5. UX Spec — Dashboard Card

**Component:** `src/components/dashboard/AIAdvisorCard.tsx`

```
┌─────────────────────────────────────────────┐
│ 📋 Your 3 priorities this week              │
│    Week of [date]                           │
├─────────────────────────────────────────────┤
│ 1. [action_1_headline]                      │
│    [action_1_detail]                        │
│    [High ●] Based on [action_1_data_source] │
│    [Approve post →]                         │
├─────────────────────────────────────────────┤
│ 2. [action_2_headline]                      │
│    ...                                      │
├─────────────────────────────────────────────┤
│ 3. [action_3_headline]                      │
│    ...                                      │
├─────────────────────────────────────────────┤
│ Powered by Synthex AI · Updated Mondays     │
│ [Remind me Friday]                          │
└─────────────────────────────────────────────┘
```

**Confidence badges:**
- High → green dot
- Medium → amber dot
- Exploratory → grey dot + tooltip "Fewer than 4 weeks of data"

**One-tap actions:**
- `approve_post` → opens calendar post approval flow
- `send_review_response` → opens GBP review response modal (pre-populated)
- `view_calendar` → navigates to calendar view
- `null` → no CTA button

**Empty state:** "Your first brief arrives Monday — we're learning your marketing patterns."

### 6. Email Digest Template

**Send schedule:** Monday 07:00 AEST (21:00 UTC Sunday)
**Subject:** `Your 3 priorities this week, [business_name]`
**From:** `weekly@synthex.app`

```html
<!-- Responsive HTML template -->
<h2>Good morning [first_name].</h2>
<p>Here's your Synthex brief for the week of [week_date].</p>

<ol>
  <li>
    <strong>[action_1_headline]</strong><br>
    [action_1_detail]<br>
    <em>[action_1_confidence] confidence · [action_1_data_source]</em>
  </li>
  <!-- action 2, 3 -->
</ol>

<a href="[dashboard_url]">View your dashboard →</a>

<hr>
<small>Synthex Weekly Brief · <a href="[unsubscribe_url]">Unsubscribe</a></small>
```

Plain text fallback: same structure without HTML.

---

## Consequences

### Positive
- Personalised AI output at <$0.006 AUD/user/week — negligible marginal cost
- Pre-computed means zero latency on dashboard load
- 3 actions is a firm constraint — prevents recommendation overload
- `Exploratory` label maintains honest signalling when data is sparse
- Flat column schema enables type-safe queries and Supabase generated types

### Negative / Trade-offs
- Requires SYN-583 ML metadata columns to be live before Sprint 5 runs
- One row per user per week means stale recommendations if user checks mid-week
- Sprint 5 build only starts once 6-8 weeks of stream data accumulated (this is the right call — don't pre-compute on empty tables)

### Out of scope (Sprint 5+)
- Real-time recommendation refresh
- User feedback loop ("Was this helpful?")
- Cross-client benchmarking in recommendations
- Multi-language support

---

## Related

- SYN-582 — parent sprint epic
- SYN-583 — ML metadata columns (prerequisite)
- SYN-584 — GEO Citation Monitor (feeds seasonal_signals stream)
- SYN-518 — trackPipelineCost (cost tracking pattern)
- `supabase/migrations/20260331180001_recommended_actions.sql`
