---
name: cs-tier1
description: "Tier-1 customer support across the 11 portfolio brands. Computes NPS, First Contact Resolution (FCR), Gross Retention Rate (GRR) and avg first-response time, drafts replies through telegram-draft-for-review, and drafts every refund for Phill's approval through draft_review HITL; it never approves a refund itself, at any amount (Wave 4 A4, RA-1862; founder ruling 21/10/2026). Use for inbound support on any portfolio brand: ticket replies, drafting a refund for Phill's approval, escalation, the daily CS brief, NPS/FCR/GRR metrics, enterprise churn threats."
owner_role: CS
status: wave-4
---

# cs-tier1

Bottles 15+ years of CS leadership — de-escalating enterprise churn calls, the "Mom test" for feedback (recognising polite lies), recognising the difference between a complaint and a churn signal — into a deterministic daily brief + a refund dual-key gate.

## Why this exists

Customer support across 11 brands cannot wait for the founder's morning cycle. The CS-tier1 bot handles inbound triage, drafts replies for review, escalates enterprise churn threats, and surfaces NPS / FCR / GRR slips before they become a board concern.

## Decision rights

Autonomous:
- Compute + emit CS metrics every cycle
- Draft daily CS brief (routes through pii-redactor + draft_review)
- Draft replies for inbound tickets (routes through telegram-draft-for-review — Scribe gate)
- Alert on threshold breaches

HITL (dual-key gate):
- Any refund, at any amount (founder ruling 21/10/2026: every amount waits for Phill)
- Public apology / postmortem
- Any service credit, at any amount, including credits within standard SLA terms (founder ruling 21/10/2026)
- Enterprise churn-save offer (any concession to a flagged customer)

## Metrics owned

| Metric | Formula | Floor / target | Alert | Critical |
|---|---|---|---|---|
| NPS | (% promoters) − (% detractors) × 100 | ≥ 50 | < 30 | — |
| FCR (First Contact Resolution) | resolved_first_contact / total_tickets | ≥ 0.75 | < 0.65 | — |
| GRR (Gross Retention Rate) | 1 − (churn / start_count) | ≥ 0.95 | < 0.90 | < 0.85 |
| Avg first-response (minutes) | mean over window | < 30m | > 60m | > 240m |
| Open enterprise churn threats | count of flagged accounts | 0 | > 0 (any) | ≥ 3 |

## Cadence

| Trigger | Action |
|---|---|
| Daily 06:00 UTC | Assemble brief → pii-redact → draft_review post |
| Per inbound ticket | Draft reply → Scribe gate via telegram-draft-for-review |
| Per refund request | Draft for Phill via draft_review; emit `cs_refund_blocked`; `pending`, and blocked unless Phill approves |

## Refund approval flow

```
incoming refund request {amount_usd, customer_id, business_id, justification}
  → every amount, no ceiling:
       draft_review.post_draft(reversibility="high",
         draft_text="💬 Refund approval — ${amount} to {customer} ({biz})",
         destination_chat_id=REVIEW_CHAT_ID, drafted_by_role="CS")
       emit cs_refund_blocked (queued, awaiting reaction)
       return pending
```

## Contract

**Daily brief output**:

```markdown
💬 CS daily — {date}

Avg NPS: 47 | Avg FCR: 78% | Avg GRR: 96% | 3 alerts (1 critical) | 1 enterprise threat

🚨 Alerts:
🔴 [synthex] grr_pct: 84% < 85% — churn investigation required.
🟡 [restoreassist] nps: 22 < 30 — detractors outpacing promoters.

Per-business (worst NPS first):
- synthex: NPS 12 | FCR 71% | GRR 84% | first-response 92m
- ...

📥 2 refund approvals queued
```

**Metric snapshot row** (per cycle, written to `.harness/swarm/cs_state.jsonl`):

```json
{
  "ts": "ISO-8601",
  "business_id": "restoreassist",
  "nps": 47.0,
  "fcr_pct": 0.78,
  "grr_pct": 0.96,
  "avg_first_response_minutes": 22.0,
  "open_enterprise_churn_threats": 0
}
```

## Safety bindings

- **All outbound replies route through telegram-draft-for-review (Scribe gate).** No autonomous send.
- **Every refund waits for the founder.** Every amount goes through draft_review at reversibility "high" (a "low" draft would send by itself). No env var changes this.
- **Every service credit waits for the founder** (founder ruling 21/10/2026), including credits within standard SLA terms. There is no separate credit path: a credit is drafted for Phill as a refund request through `approve_refund` / draft_review, `cs_refund_blocked` is recorded, and it stays pending until he approves.
- **PII-redactor in front of every draft** — customer names, emails, ticket IDs go through pii-redactor at strictness=standard.
- **Enterprise churn threats are critical the moment they're opened** — escalates to founder via daily brief.
- **Kill-switch aware.** On `TAO_SWARM_ENABLED=0`, the daily brief is queued (not sent).

## When NOT to use

- Tier-2 / engineering-escalation tickets — those route to CTO bot via flow_engine
- Compliance / data-deletion requests (GDPR / CCPA) — those route to GC + CCO bots (Phase B)
- Marketing-driven outreach (NPS surveys, feedback campaigns) — that's CMO bot

## Verification (Wave 4 A4)

1. Synthetic data → NPS / FCR / GRR computed correctly
2. GRR < 85% → critical alert fires
3. First response > 240m → critical alert fires
4. Open enterprise threats >= 3 → critical alert fires
5. $50 refund → routes through draft_review, status `pending`
6. $200 refund without draft_review → blocked
7. $200 refund with draft_review → pending, no real refund issued
8. Daily brief assembles cleanly with all 11 businesses

## References

- Blueprint: `~/Pi-CEO/Senior-Agent-Operations-Blueprint-2026-05-02.md` §Role 17 Customer Success
- Parent ticket: <issue id="RA-1862">RA-1862</issue> (epic <issue id="RA-1858">RA-1858</issue>)
- Outbound substrate: `skills/telegram-draft-for-review/SKILL.md` (Scribe gate)
- HITL gate substrate: `swarm/draft_review.py`
- Multi-agent debate scaffold: `swarm/debate_runner.py` (RA-1867)
