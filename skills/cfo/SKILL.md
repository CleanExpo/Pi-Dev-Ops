---
name: cfo
description: Daily financial visibility across the 11 Unite-Group businesses. Computes burn multiple, NRR, CAC payback, gross margin from Stripe + Xero feeds. Drafts a 1-page financial brief into the daily 6-pager. Gates spend approvals >$1K through draft_review HITL. Closes Wave 4.1 of the senior-agent slate (RA-1850).
owner_role: CFO
status: wave-4
---

# cfo

Bottles 15+ years of CFO expertise — SVB-style bank-run navigation, GAAP↔non-GAAP bridging, the skeleton-in-the-closet adjustments that surface in IPO diligence — into a deterministic daily brief + an event-triggered alert stream.

## Why this exists

The founder of an 11-business umbrella cannot read 11 P&Ls every morning. The CFO bot reads them, computes the canonical SaaS metrics, and surfaces only what's actionable: burn breaches, NRR drift, gross-margin compression, runway reduction. Everything else flows into the daily 6-pager (`daily-6pager` skill, RA-1854).

## Decision rights

Autonomous:
- Compute + emit financial metrics every cycle
- Draft daily financial brief (routes through pii-redactor + draft_review)
- Alert on threshold breaches (also through draft_review)

HITL (dual-key gate):
- Approve invoice/spend over $1,000 (configurable per business)
- Authorise a debt instrument or capital raise
- Approve a one-time GAAP adjustment

## Metrics owned

| Metric | Formula | Floor / target | Alert threshold |
|---|---|---|---|
| Burn multiple | Net Burn / Net New ARR | <1.0x (AI-native: <0.5x) | >1.5x for 2 weeks → alert |
| CAC payback | CAC / (ARPU × gross margin %) | <12 months | >18 months → alert |
| NRR (B2B) | (start_MRR + expansion − churn − contraction) / start_MRR | 120% | <110% → alert |
| NRR (prosumer) | same | 100% | <90% → alert |
| Gross margin | (revenue − COGS) / revenue | 85% | <75% → alert |
| Runway | cash / monthly burn | >18 months | <12 months → alert |
| Model spend ratio | inference cost / MRR | <5% | >7% → alert |

## Cadence

| Trigger | Action |
|---|---|
| Daily 06:00 user-local | Assemble daily brief → pii-redact → draft_review post to REVIEW_CHAT_ID |
| Per-cycle (5 min) | Recompute metrics; alert on breach |
| Per spend request | Dual-key gate; emit `cfo_invoice_approved` or `cfo_spend_blocked` |
| Weekly Monday 08:00 | Burn-multiple trend + 12-week runway projection |

## Pipeline

```
read_metrics_provider()              ← thin abstraction (Stripe + Xero MCP, or synthetic in tests)
  → compute_metrics(raw)             ← pure-Python; deterministic
    → detect_breaches(metrics, last) ← compares to last-cycle snapshot
      → if breach: emit cfo_alert + draft_review.post_draft (severity-gated)
      → if daily-fire window: assemble_brief(metrics, breaches) + post to draft_review
      → emit cfo_metric_snapshot row to .harness/swarm/cfo_state.jsonl
```

## Spend approval flow

```
incoming spend request {amount_usd, vendor, business_id, justification}
  → if amount_usd <= cfo.AUTONOMOUS_SPEND_CEILING:
       emit cfo_invoice_approved → return approved
  → else:
       draft_review.post_draft(
         draft_text="🧾 Spend approval — ${amount} to {vendor} ({business_id})\n{justification}",
         destination_chat_id=REVIEW_CHAT_ID,
         drafted_by_role="CFO")
       emit cfo_spend_blocked (queued, awaiting reaction)
       return pending
```

## Contract

**Daily brief output** (passes to draft_review):

```markdown
💰 CFO daily — {date}

Portfolio runway: {months}m | Total MRR: ${mrr_total} | Burn multiple: {bm}x
{N} alerts triggered overnight: ...

Per-business (only those with movement):
- restoreassist: NRR {x}% | GM {y}% | runway {z}m
- ccw-crm:      ...

Action requests today:
- {n} spend approvals queued in review chat (above the $1K ceiling)
- {n} threshold breaches awaiting acknowledgement
```

**Metric snapshot row** (per cycle, written to `.harness/swarm/cfo_state.jsonl`):

```json
{
  "ts": "ISO-8601",
  "business_id": "restoreassist",
  "mrr": 12500.00,
  "net_new_arr": 1500.00,
  "net_burn": 800.00,
  "burn_multiple": 0.53,
  "nrr_30d": 1.18,
  "gross_margin": 0.87,
  "cac_payback_months": 9.5,
  "runway_months": 22.4,
  "model_spend_ratio": 0.034
}
```

## Safety bindings

- **Read-mostly.** CFO bot calls Stripe + Xero in *read* scope only. No invoice creation, refund, or payment-method change without HITL.
- **Spend ceiling persisted** (`AUTONOMOUS_SPEND_CEILING`, default $1000). Editing requires user approval, audit-trailed.
- **PII-redactor in front of every draft** — invoice descriptions / vendor names / customer names go through pii-redactor at strictness=standard before reaching the review chat.
- **Hash-based deduplication** — alert for the same breach won't re-fire within 24h (uses last-snapshot diff).
- **Kill-switch aware.** On `TAO_SWARM_ENABLED=0`, the daily brief is queued (not sent) until resume.

## When NOT to use

- Real-time treasury moves (wire transfers, FX hedging) — these need a human hand on the wheel; CFO bot escalates.
- IPO/buyout-stage SOX controls — that's the CCO bot's job (Wave 4 Phase B).
- Cap-table changes — that's Head of IR (Wave 4 Phase B).

## Verification (Wave 4.1)

1. Synthetic 7-day Stripe data → burn multiple computed correctly (within ±0.01x of hand-calc)
2. Burn multiple drops 0.4 → 1.6 between cycles → alert fires + draft posted to review chat
3. $500 spend request → auto-approves, audit row written
4. $5000 spend request → routes through draft_review, status `pending`, NO real send
5. Daily brief assembles in <30s with all 11 businesses' metrics
6. Brief posts through pii-redactor — no raw vendor names if flagged
7. `cfo` module compiles + imports clean alongside existing `swarm/*`

## Out of scope (Wave 4.1)

- Real Stripe + Xero wire-up — engine ships against a pluggable `metrics_provider` callable; production wire is Wave 4.1b
- 12-week burn projection ML — uses linear extrapolation in v1
- Multi-currency consolidation — assumes USD; flagged for Wave 4.2 if non-USD businesses surface

## References

- Blueprint: `/Users/phill-mac/Pi-CEO/Senior-Agent-Operations-Blueprint-2026-05-02.md` §Role 2 CFO
- Parent ticket: <issue id="RA-1850">RA-1850</issue> (epic <issue id="RA-1849">RA-1849</issue>)
- Margot research (2026-05-02): "burn multiple <1.0x; AI-native target <0.5x; gross margin floor 85%; NRR 120% B2B"
- HITL gate substrate: `swarm/draft_review.py` (RA-1839, pii-redactor wired RA-1839 today)
