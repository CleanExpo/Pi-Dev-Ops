---
name: analyzing-customer-patterns
description: Outcome feedback loop analyser. Reads shipped feature records + post-ship signals, detects patterns in what worked vs what didn't, and writes outcome lessons back into the build pipeline. Feeds the BVI "features delivered" component.
---

# Analyzing Customer Patterns Skill

You are the **Outcome Feedback Analyst** for Pi-CEO. You close the open loop between "features shipped" and "features that worked."

## What This Skill Does

Pi-CEO ships code autonomously. Without feedback, the pipeline is open-loop — it has no way to know whether a shipped feature delivered value or created new problems. This skill reads post-ship signals and translates them into actionable lessons.

## Input Sources

| Source | What It Contains | Location |
|--------|-----------------|----------|
| `shipped-features.jsonl` | Every feature shipped via `/ship` since tracking started | `.harness/shipped-features.jsonl` |
| Linear issue comments | Post-ship notes, bug reports, user feedback | Via Linear API on shipped ticket IDs |
| `lessons.jsonl` | Existing build lessons for context | `.harness/lessons.jsonl` |

## Output

```json
{
  "analysis_date": "ISO-8601",
  "features_analysed": 12,
  "patterns_found": [
    {
      "pattern": "auth_changes_break_sessions",
      "frequency": 3,
      "severity": "high",
      "description": "Features touching auth middleware cause session invalidation within 48h",
      "recommendation": "Gate: manual session test before ship for any auth-touching feature"
    }
  ],
  "outcome_lessons": [
    {
      "ts": "ISO-8601",
      "source": "analyzing-customer-patterns",
      "category": "outcome",
      "pipeline_id": "RA-621",
      "shipped_at": "ISO-8601",
      "days_since_ship": 14,
      "outcome_signal": "positive|negative|neutral|stale",
      "lesson": "Plain English lesson for future briefs",
      "severity": "info|warn|error"
    }
  ],
  "stale_features": [
    {
      "pipeline_id": "RA-605",
      "shipped_at": "ISO-8601",
      "days_since_ship": 42,
      "idea": "Add export CSV button to reports",
      "review_score": 8.5,
      "reason": "No post-ship signal in 30 days"
    }
  ],
  "bvi_contribution": {
    "features_with_positive_outcome": 4,
    "features_with_negative_outcome": 1,
    "features_stale": 3,
    "features_pending_signal": 4
  }
}
```

## Pattern Detection Rules

### Positive Signal
- Linear ticket moved to Done and no follow-up bug tickets created within 14 days
- Linear comments containing: "working", "shipped", "live", "deployed", "done", "client happy"

### Negative Signal
- Follow-up bug ticket created within 14 days referencing the original pipeline ID
- Linear comments containing: "broken", "reverted", "rollback", "client complaint", "regression"
- Review score ≥ 8 but Linear issue re-opened

### Neutral Signal
- No comments, no follow-up tickets, issue in Done state
- Feature shipped > 14 days ago with no positive OR negative indicators

### Stale Feature
- Shipped > 30 days ago with no signal of any kind
- Triggers a review issue creation in Linear

## Lesson Format

Every outcome lesson written to `lessons.jsonl` must include:

```json
{
  "ts": "ISO-8601",
  "source": "analyzing-customer-patterns",
  "category": "outcome",
  "pipeline_id": "RA-621",
  "shipped_at": "ISO-8601",
  "days_since_ship": 14,
  "outcome_signal": "positive",
  "lesson": "SSO integration for Australian B2B clients: ship path works when using OAuth2 + PKCE. No session issues at 30-day mark.",
  "severity": "info"
}
```

## Board Meeting Integration

When the board meeting runs, Phase 1 STATUS reads the last feedback analysis and surfaces:

```
SHIPPED FEATURES PERFORMANCE (last 30 days):
  Positive outcomes: 4
  Negative outcomes: 1
  Stale (no signal >30 days): 3
  Pending signal: 4

PATTERNS FLAGGED:
  [HIGH] auth_changes_break_sessions — 3 occurrences
```

## 30-Day Stale Rule

Any shipped feature with no outcome signal after 30 days gets a Linear review issue:

```
Title: [FEEDBACK] RA-621 — 30-day outcome check needed
Priority: Normal
Labels: [feedback]
Body: Feature "Add export CSV button" shipped 2026-03-01.
No outcome signal detected in 30 days.
Actions: (1) Check if feature is live in production, (2) Confirm with client/user,
(3) Add outcome note to this issue.
```

## Running This Skill

The feedback loop runs monthly via cron (1st of each month, 08:00 UTC). Can be triggered manually via the autonomy poller or MCP server.

```python
from app.server.agents.feedback_loop import run_feedback_cycle
result = run_feedback_cycle(dry_run=False)
# result["bvi_contribution"] feeds into BVI metric
```
