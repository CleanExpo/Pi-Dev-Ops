---
name: cto
description: Daily platform-health visibility across the 11 portfolio repos. Computes the DORA quartet (deploy frequency, lead time, MTTR, change-failure rate) plus p99 latency, uptime, and cost-per-request from GitHub Actions + Vercel observability feeds. Drafts a 1-page CTO snippet into the daily 6-pager. Gates production PR merges through draft_review HITL. Closes Wave 4 A3 of the senior-agent slate (RA-1861).
owner_role: CTO
status: wave-4
---

# cto

Bottles 15+ years of CTO expertise — CAP-theorem trade-offs lived not read, catastrophic database-migration war stories, knowing which Vercel/AWS abstractions to trust — into a deterministic daily brief + an event-triggered alert stream.

## Why this exists

Eleven repos shipping continuously with autonomous PR creation. The founder needs DORA + p99 + uptime + cost-per-request in one glance every morning, plus a hard gate on every production merge. Everything else flows into the daily 6-pager (`daily-6-pager` skill, RA-1863).

## Decision rights — quick reference

| Action class | Autonomous | Threshold | HITL gate |
|---|---|---|---|
| DORA snapshots | ✅ | Every cycle | None |
| PR review draft | ✅ | Always | qa-lead gate before merge |
| Feature/dev infra PR merge | ✅ | Non-prod only | None |
| Production PR merge | ❌ | NEVER autonomous | Always HITL (founder for portfolio core) |
| Critical alert fire | ✅ | On 🔴 only (silent-on-clean) | None |
| Halt-ship on CFR > 30% | ✅ | Auto-fires (reversible) | None |
| AWS / Vercel / Supabase scaling | ❌ | NEVER autonomous | Always HITL |
| DB migrations on production | ❌ | NEVER autonomous | Always HITL |

## Decision rights — detail

Autonomous:
- Compute + emit platform metrics every cycle
- Draft daily platform brief (routes through pii-redactor + draft_review)
- Alert on threshold breaches (also through draft_review)
- Approve PR merges to feature branches and dev infra

HITL (dual-key gate):
- PR merge to production (`is_production=True` from `.harness/projects.json`)
- AWS / Vercel / Supabase scaling moves
- Database migrations on production
- Platform consolidation decisions (region, provider switch)

## Metrics owned (DORA + ops)

| Metric | Floor / target | Alert | Critical |
|---|---|---|---|
| Deploy frequency (per week) | ≥ 7 (elite) | < 2 | — |
| Lead time hours p50 | < 1h (elite) | > 24h | — |
| MTTR hours | < 1h (elite) | > 4h | > 24h |
| Change failure rate | < 15% | > 15% | > 30% |
| p99 latency (ms) | < 500ms | > 1000ms | — |
| Uptime % | > 99.95% | < 99.5% | < 99.0% |
| Cost per request (USD) | < $0.001 | > $0.005 | — |

DORA bands derived from Google's State of DevOps benchmarks: elite > high > medium > low.

## Cadence

| Trigger | Action |
|---|---|
| Daily 06:00 UTC (configurable) | Assemble daily brief → pii-redact → draft_review post |
| Per-cycle (5 min) | Recompute metrics; alert on breach |
| Per PR merge request | Dual-key gate when is_production=True |

## Pipeline

```
read_platform_provider()              ← pluggable (GH Actions + Vercel + Datadog
                                        in production; synthetic in tests)
  → compute_metrics(raw)              ← pure-Python; deterministic; classifies DORA band
    → detect_breaches(metrics, last)  ← compares to prior cycle snapshot
      → if breach: emit cto_alert + draft_review.post_draft (severity-gated)
      → if daily-fire window: assemble_brief + post to draft_review
      → emit cto_metric_snapshot to .harness/swarm/cto_state.jsonl
```

## PR-merge approval flow

```
incoming request {repo, pr_number, target_branch, title, is_production}
  → if not is_production:
       emit cto_pr_merge_approved → return approved
  → else:
       draft_review.post_draft(
         draft_text="⚙️ PR merge to production — {repo}#{pr_number} → {target}",
         destination_chat_id=REVIEW_CHAT_ID,
         drafted_by_role="CTO")
       emit cto_pr_merge_blocked (queued, awaiting reaction)
       return pending
```

## Contract

**Daily brief output** (passes to draft_review):

```markdown
⚙️ CTO daily — {date}

DORA distribution: elite:3 · high:5 · medium:2 · low:1 | Avg uptime: 99.92% | 4 alerts (1 critical)

🚨 Alerts:
🔴 [synthex] mttr_hours: 28.0h > 24h — incident-response broken.
🟡 [ccw-crm] change_failure_rate: 18% > 15% — test gate review.
🟡 [restoreassist] deploy_freq_per_week: 1.0/wk < 2/wk — shipping cadence stalling.

Per-repo:
- pi-dev-ops: elite | deploys 9.0/wk | lead 0.4h | MTTR 0.5h | CFR 8% | p99 240ms | uptime 99.99%
- restoreassist: high | deploys 1.0/wk | lead 6.0h | MTTR 2.0h | CFR 12% | p99 380ms | uptime 99.95%
- ...

📥 1 production PR merge queued in review chat
```

**Metric snapshot row** (per cycle, written to `.harness/swarm/cto_state.jsonl`):

```json
{
  "ts": "ISO-8601",
  "business_id": "pi-dev-ops",
  "deploy_freq_per_week": 9.0,
  "lead_time_hours_p50": 0.4,
  "mttr_hours": 0.5,
  "change_failure_rate": 0.08,
  "p99_latency_ms": 240.0,
  "uptime_pct": 0.9999,
  "cost_per_request_usd": 0.0012,
  "dora_band": "elite"
}
```

## Safety bindings

- **Read-mostly.** CTO bot reads GitHub Actions + Vercel + Datadog APIs in *read* scope only. No deploy / rollback / scaling action without HITL.
- **Production PR-merge gate persisted** — every merge with `is_production=True` HITL-gated, no env override.
- **PII-redactor in front of every draft** — repo names + secret references go through pii-redactor at strictness=standard.
- **24h alert dedup** — same breach won't re-fire within 24h.
- **Kill-switch aware.** On `TAO_SWARM_ENABLED=0`, the daily brief is queued (not sent) until resume.

## When NOT to use

- Code generation / PR creation — that's the existing `pipeline.py` + `tier-orchestrator` + `ship-chain`
- Scanner findings → tickets — that's the existing `pi-seo-scanner` skill family
- Code review on PRs — that's the existing `agentic-review` + `simplify` skills

## Verification (Wave 4 A3)

1. Synthetic data → DORA quartet + classifier returns expected band
2. MTTR > 24h → critical alert fires
3. CFR > 30% → critical alert fires
4. Uptime < 99.0% → critical alert fires
5. Feature-branch PR (is_production=False) → auto-approves
6. Production PR (is_production=True) without draft_review → blocked
7. Production PR (is_production=True) with draft_review → pending, no real merge

## Out of scope (Wave 4 A3)

- Real GitHub Actions / Vercel / Datadog wire-up — engine ships against pluggable provider; connector is a follow-up
- Autonomous rollback on red metrics — proposes only; humans pull the trigger
- Region / provider failover dry-runs — that's the Platform-Risk agent (Wave 4 Phase B)

## References

- Blueprint: `/Users/phill-mac/Pi-CEO/Senior-Agent-Operations-Blueprint-2026-05-02.md` §Role 3 CTO
- Parent ticket: <issue id="RA-1861">RA-1861</issue> (epic <issue id="RA-1858">RA-1858</issue>)
- DORA benchmarks: Google State of DevOps Report 2024
- HITL gate substrate: `swarm/draft_review.py`
- Multi-agent debate scaffold: `swarm/debate_runner.py` (RA-1867)
