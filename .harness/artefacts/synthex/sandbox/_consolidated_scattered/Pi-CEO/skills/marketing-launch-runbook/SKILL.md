---
name: marketing-launch-runbook
description: Builds a T-30 to T+30 product-launch runbook with a per-day timeline, owners, asset dependencies, gate checks, contingencies, and post-launch attribution. Use when a brief mentions "launch", "GTM", "go-to-market", "ship a product", "release campaign", "launch playbook". Reads campaign-plan + positioning + channel-plan + all content artifacts; calls remotion-orchestrator for launch-day video assets. Outputs the single source of truth that orchestrates every other skill on the calendar.
automation: automatic
intents: launch, launch-plan, launch-runbook, go-to-market, gtm, release-campaign, product-launch, launch-playbook
---

# marketing-launch-runbook

Owns "the calendar that ships the launch". Not strategy (campaign-planner), not copy (copywriter) — the orchestration layer that aligns owners + dependencies + gates.

## Triggers

- Brief contains "launch", "GTM", "go-to-market", "release campaign", "launch playbook", "ship the product".
- Or invoked by `marketing-orchestrator` when `campaignType === 'product-launch'`.
- Or by `marketing-campaign-planner` after campaign objectives are set for a launch-class campaign.

## Inputs

Mandatory upstream:
- `campaign-plan.json` from `marketing-campaign-planner`
- `positioning.md` from `marketing-positioning`
- `icp/{slug}-{date}.md` from `marketing-icp-research`
- `channel-plan.json` from `marketing-channel-strategist`

Per-job:
- `launchDate` — T-0 absolute date (ISO).
- `team` — owners by role (founder, marketing, eng, design, support, sales).
- `tier` — `soft` (community + email only) | `standard` (+ social + PR) | `headline` (+ paid + partner orchestration + press tour).

## Method

### Phase windows
- **T-30 → T-15: Build phase**. Positioning frozen. Asset production in flight. ICP research validated.
- **T-15 → T-7: Polish phase**. All content drafts ready for review. Email lists segmented. Tracking + UTM in place.
- **T-7 → T-1: Pre-launch phase**. Soft sneak-peek to inner circle. Bug-bash. Final asset QA.
- **T-0: Launch day**. Sequenced drops across channels at named hours. War-room mode.
- **T+1 → T+7: Amplification phase**. Re-share, follow-ups, customer-quote roundups.
- **T+7 → T+30: Measurement phase**. Attribution, retro, next-cycle ticket creation.

### Per-day cells
For every day in the window, set:
- **Drops** — content slots from `channel-plan.sequencing` referenced by id.
- **Owner** — single name (no shared ownership).
- **Dependencies** — assets / approvals this day waits on.
- **Gate check** — pass criteria; if it doesn't pass, fall to contingency.
- **Contingency** — explicit fallback (e.g. "if video render fails T-2, ship still-image carousel + reschedule video to T+1").

### Cross-pack dispatch
Every video deliverable on the calendar gets a `remotion-orchestrator` sub-job at production time, with the channel + duration + composition pulled from `channel-plan`.

### War-room protocol (T-0)
- Hour-by-hour drop schedule.
- Pre-staged Telegram + Linear status surfaces.
- Designated approver for in-flight changes.
- Kill criteria (when to pause launch — e.g. critical bug discovered, PR crisis).

## Output

`<calling-project>/.marketing/launch/{jobId}/runbook.md` + `runbook.json`:

```jsonc
{
  "jobId": "synthex-launch-2026-04-28",
  "brand": "synthex",
  "launchDate": "2026-05-15",
  "tier": "standard",
  "phases": {
    "build":       { "start": "2026-04-15", "end": "2026-04-30" },
    "polish":      { "start": "2026-05-01", "end": "2026-05-08" },
    "preLaunch":   { "start": "2026-05-08", "end": "2026-05-14" },
    "launchDay":   { "date": "2026-05-15" },
    "amplify":     { "start": "2026-05-16", "end": "2026-05-22" },
    "measure":     { "start": "2026-05-22", "end": "2026-06-15" }
  },
  "calendar": [
    {
      "date": "2026-05-15",
      "phase": "launchDay",
      "drops": [
        { "time": "09:00 AEST", "channel": "blog", "asset": "launch-pillar-post", "owner": "founder" },
        { "time": "09:30 AEST", "channel": "linkedin", "asset": "linkedin-post-launch", "owner": "marketing" },
        { "time": "10:00 AEST", "channel": "email", "asset": "email-1-launch", "owner": "marketing" },
        { "time": "11:00 AEST", "channel": "linkedin", "asset": "explainer-video-60s", "owner": "marketing", "remotionJobId": "..." }
      ],
      "gateCheck": "All assets approved by founder T-1 17:00. Press-release embargo lifts 09:00 sharp.",
      "contingency": "If embargo broken early: skip blog drop, lead with LinkedIn post + email."
    }
  ],
  "warRoom": { "telegramChat": "...", "linearProject": "...", "killCriteria": ["critical bug in trial flow", "PR crisis"] }
}
```

## Boundaries

- Never set a calendar without a single named owner per drop.
- Never schedule a launch-day drop without an upstream gate check that has a pass-criterion.
- Never plan T-0 to T-7 without a contingency for at least 2 of the most fragile dependencies (typically: video render, third-party press coverage, paid ad approval).
- Never confuse phases: build is asset production, polish is QA, pre-launch is rehearsal, launch is execution. Mixing causes thrash.

## Hands off to

- `remotion-orchestrator` (every video drop)
- `marketing-analytics-attribution` (UTM scheme + dashboard before T-7)
- Linear (auto-creates a ticket per drop in the brand's project per `.harness/projects.json`)
- Telegram (war-room channel pinned)

## Per-project keys

- `LINEAR_API_KEY` — auto-creates per-drop tickets. Missing → emits markdown checklist only.
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — pins war-room status. Missing → skip pin.
- `GOOGLE_CALENDAR_API_KEY` (future v1.1) — drops onto founder's calendar. v1 emits an `.ics` file in outputs.
