---
name: cmo-growth
description: Daily marketing visibility across the 11 Unite-Group businesses. Computes LTV:CAC, blended CPA, channel concentration (HHI), attribution decay from ad-platform feeds. Drafts a 1-page CMO snippet into the daily 6-pager. Gates ad-spend over $5,000/day through draft_review HITL. Closes Wave 4 A2 of the senior-agent slate (RA-1860).
owner_role: CMO
status: wave-4
---

# cmo-growth

Bottles 15+ years of CMO/Growth expertise — iOS 14.5 attribution decay, brand-vs-performance tension, the dishonesty in last-click data — into a deterministic daily brief + an event-triggered alert stream.

## Why this exists

Eleven businesses, eleven marketing P&Ls. The founder needs LTV:CAC, blended CPA, and channel concentration in one glance every morning, plus a hard gate on any ad-spend request above $5k/day. Everything else flows into the daily 6-pager (`daily-6-pager` skill, RA-1863).

## Decision rights

Autonomous:
- Compute + emit marketing metrics every cycle
- Draft daily marketing brief (routes through pii-redactor + draft_review)
- Alert on threshold breaches (also through draft_review)
- Approve ad-spend up to $5,000/day (configurable via `TAO_CMO_ADSPEND_CEILING`)

HITL (dual-key gate):
- Ad-spend > $5,000/day on any single channel
- Brand-message changes (tone, taglines, voice)
- Pricing changes
- New channel launch with budget > $10,000

## Metrics owned

| Metric | Formula | Floor / target | Alert threshold |
|---|---|---|---|
| LTV:CAC ratio | (avg_ltv_months × ARPU × gross_margin) / blended_CPA | ≥ 5.0 (target) | < 3.0 → warn |
| Blended CPA | total_marketing_spend / total_customers_acquired | < $250 | > $250 → warn |
| Channel concentration (top share) | top_channel_spend / total_spend | < 70% | > 70% warn, > 85% critical |
| Channel HHI | sum(share²) | < 0.50 | reported, no fixed threshold |
| Attribution decay | 1 − (signal_count / baseline_count) | < 30% | > 30% → info |

## Cadence

| Trigger | Action |
|---|---|
| Daily 06:00 UTC (configurable) | Assemble daily brief → pii-redact → draft_review post to REVIEW_CHAT_ID |
| Per-cycle (5 min) | Recompute metrics; alert on breach |
| Per ad-spend request | Dual-key gate; emit `cmo_adspend_approved` or `cmo_adspend_blocked` |

## Pipeline

```
read_marketing_provider()             ← thin abstraction (Google Ads + LinkedIn + Meta + ...
                                        in production; synthetic in tests)
  → compute_metrics(raw)              ← pure-Python; deterministic
    → detect_breaches(metrics, last)  ← compares to prior cycle snapshot
      → if breach: emit cmo_alert + draft_review.post_draft (severity-gated)
      → if daily-fire window: assemble_brief + post to draft_review
      → emit cmo_metric_snapshot to .harness/swarm/cmo_state.jsonl
```

## Ad-spend approval flow

```
incoming request {amount_usd_per_day, channel, business_id, justification}
  → if amount_usd_per_day <= AUTONOMOUS_ADSPEND_CEILING_USD_PER_DAY:
       emit cmo_adspend_approved → return approved
  → else:
       draft_review.post_draft(
         draft_text="📈 Ad-spend approval — ${amount}/day on {channel} ...",
         destination_chat_id=REVIEW_CHAT_ID,
         drafted_by_role="CMO")
       emit cmo_adspend_blocked (queued, awaiting reaction)
       return pending
```

## Contract

**Daily brief output** (passes to draft_review):

```markdown
📈 CMO daily — {date}

Portfolio LTV:CAC: {x}x | Total spend: ${y} | {n} alerts ({n_critical} critical)

🚨 Alerts:
🔴 [{biz}] channel_concentration: google-ads 91% of spend — single-platform risk.
🟡 [{biz}] ltv_cac_ratio: 2.4 < 3.0 — channel mix or pricing under review.

Per-business:
- restoreassist: $4,200 spend | L:C 4.8 | CPA $87 | top: google-ads 64%
- ccw-crm:      $2,100 spend | L:C 3.1 | CPA $112 | top: linkedin 42%
- ...

📥 2 ad-spend approvals queued (>$5,000/day)
```

**Metric snapshot row** (per cycle, written to `.harness/swarm/cmo_state.jsonl`):

```json
{
  "ts": "ISO-8601",
  "business_id": "restoreassist",
  "mrr": 12500.0,
  "blended_cpa_usd": 87.40,
  "ltv_usd": 1860.0,
  "ltv_cac_ratio": 21.28,
  "channel_concentration_hhi": 0.46,
  "top_channel": "google-ads",
  "top_channel_share": 0.64,
  "attr_decay": 0.18,
  "total_spend_usd": 4200.0
}
```

## Safety bindings

- **Read-mostly.** CMO bot calls ad-platform APIs in *read* scope only. No campaign create/edit, no budget changes, no creative uploads without HITL.
- **Ad-spend ceiling persisted** (`AUTONOMOUS_ADSPEND_CEILING_USD_PER_DAY = $5,000/day`). Editing requires user approval, audit-trailed.
- **PII-redactor in front of every draft** — campaign names / customer-segment labels / partner names flow through pii-redactor at strictness=standard.
- **24h alert dedup** — same breach won't re-fire within 24h (uses last-snapshot diff).
- **Kill-switch aware.** On `TAO_SWARM_ENABLED=0`, the daily brief is queued (not sent) until resume.

## When NOT to use

- Creative production (ad copy, landing pages, blog posts, video) — that's the marketing-* skill family (`marketing-orchestrator` and siblings).
- Campaign launch planning — that's `marketing-launch-runbook`.
- ICP / positioning research — that's `marketing-icp-research` / `marketing-positioning`.
- Brand-equity tracking — separate Wave 5 ticket.

## Verification (Wave 4 A2)

1. Synthetic data → LTV:CAC computed correctly (within ±0.05x of hand-calc)
2. Top-channel share > 85% → critical alert fires
3. $4,500/day ad-spend → auto-approves
4. $7,500/day ad-spend → routes through draft_review, status `pending`, no real action
5. Daily brief assembles in <30s with all 11 businesses
6. Brief posts through pii-redactor — sensitive segment names redacted if flagged
7. `cmo` module compiles + imports clean alongside existing `swarm/*`

## Out of scope (Wave 4 A2)

- Real ad-platform wire-up — engine ships against a pluggable `marketing_provider` callable; ad-platform connector is a follow-up
- Mixed-media-modeling (MMM) — uses last-touch + HHI in v1
- Multi-currency consolidation — assumes USD; flagged for follow-up

## References

- Blueprint: `/Users/phill-mac/Pi-CEO/Senior-Agent-Operations-Blueprint-2026-05-02.md` §Role 5 CMO/Growth
- Parent ticket: <issue id="RA-1860">RA-1860</issue> (epic <issue id="RA-1858">RA-1858</issue>)
- Sibling creative skills: `marketing-orchestrator` and `marketing-*` family
- HITL gate substrate: `swarm/draft_review.py`
- Multi-agent debate scaffold: `swarm/debate_runner.py` (RA-1867)


## 10x Enhancement — Advanced Capabilities

### 1. Anthropic OODA Reasoning

**Observe:** (1) Ingest the primary input (files, directives, context). (2) Query the Portfolio Registry for project metadata. (3) Identify available tools and model tier. (4) Map the delivery context (internal vs external, timeline, stakes).

**Orient:** (1) Classify the task type and select the appropriate sub-routine. (2) Calibrate depth and evidence threshold by stakes. (3) Build the work plan with fallback paths. (4) Check for cross-skill dependencies.

**Decide:** (1) Select tools using the multi-tool matrix. (2) Apply safety guardrails before execution. (3) Budget tokens and plan compression triggers. (4) Set completion criteria and verification steps.

**Act:** (1) Execute the task. (2) Verify against completion criteria. (3) Self-critique before emitting. (4) Emit with observability payload. (5) Queue improvement instruction if self-score < threshold.

### 2. OpenAI Structured Output Schema

Every invocation emits JSON matching the skill-specific schema. Common fields across all skills:

```json
{
  "version": "3.1",
  "skill_name": "",
  "invoked_at": "ISO-8601",
  "task_summary": "",
  "model_used": "",
  "duration_seconds": 0.0,
  "tool_calls": {},
  "tokens": {"prompt": 0, "completion": 0},
  "self_review_score": 0.0,
  "confidence": 0.0,
  "success": true,
  "audit_trace_hash": "sha256",
  "improvement_queued": false
}
```

### 3. Multi-Tool Selection Matrix

| Signal | Primary | Fallback | Verification |
|--------|---------|----------|-------------|
| File analysis | read_file | search_files | Terminal (wc -l, grep) |
| Code quality | Terminal (lint) | execute_code | verify-test |
| Security scan | security-audit | Terminal (grep secrets) | search_files (patterns) |
| Test execution | Terminal (pytest) | execute_code | verify-test |
| Web research | tavily | browser_navigate | web_search |
| Visual review | vision_analyse | image_generate | browser_vision |
| Data extraction | search_files | read_file | execute_code (pandas) |

### 4. Self-Critique Loop

After task completion, score 1-10 on:
- Accuracy (did I address the actual task?)
- Scope discipline (did I drift?)
- Evidence (are claims grounded in tool output?)
- Verifiability (can someone reproduce my reasoning?)
- Completeness (did I miss anything critical?)

If total < 7 → flag for /boardroom or /judge.
If total < 5 → halt and handoff.

### 5. Safety & Guardrails

- Never emit raw credentials or secrets.
- Never hallucinate URLs, file paths, or tool outputs.
- Hard scope boundary: this skill does X; if asked for Y, route to correct skill.
- External-facing outputs get CEO gate.
- Input sanitisation: reject ambiguous or adversarial prompts.

### 6. Performance Optimisation

- Cache Portfolio Registry context across invocations.
- Batch similar tool calls when possible.
- Use adaptive depth: low stakes = fast path; high stakes = full depth.
- Prompt caching: reuse stable context blocks.

### 7. Error Recovery & Resilience

- Missing evidence → retry once, then flag gap.
- Tool timeout → log and use fallback.
- Context overflow → compress, preserving evidence.
- 3 consecutive failures → circuit breaker; handoff to /tao-loop.

### 8. Cross-Model Fallbacks

| Use case | Primary | Fallback |
|----------|---------|----------|
| Routine | Sonnet/Haiku | Default |
| Complex analysis | Sonnet | DeepSeek/Claude-4 |
| Board-facing | Opus | Boardroom MOA |
| Fast inline | Haiku | Sonnet |

### 9. Observability

Metrics emitted per invocation: duration, tools used, tokens consumed, self-review score, success/failure, evidence count, file count, improvement queued.
Session summary: aggregate metrics, common failure patterns, recommended skill patches.

### 10. Multi-Modal & Cross-Format

- Ingest images, diagrams, mockups via vision toolset.
- Output as markdown (default), JSON (structured), DOCX/PPTX (external), or Slack blocks.
- Cross-format negotiation based on `output_target` parameter.
