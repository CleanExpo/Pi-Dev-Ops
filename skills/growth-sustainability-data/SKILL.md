---
name: growth-sustainability-data
description: Method for collecting and gathering data for growth and sustainability across the 11-business portfolio. Defines the two-layer stack — Analyst (direction + analysis) commands collector skills (CMO, CFO, CTO, CS, Margot, wiki, Scout, marketing) — and the handoff contract between them. Use when framing executive visibility, research sprints, board prep, or any question about whether the business can grow and endure.
owner_role: CoS
status: wave-5
---

# Method — Collecting and Gathering Data for Growth and Sustainability

Growth = can revenue and distribution compound? Sustainability = can cash, margin, retention, and
ops survive the compounding? This skill defines **how data is collected**; the Analyst skill
defines **how it is directed, graded, and turned into decisions**.

---

## Two-layer architecture

| Layer | Role | Skill | Does |
|---|---|---|---|
| **Direction + analysis** | Frames questions, tasks collectors, grades evidence, synthesises, states kill-switches | [`analyst`](../analyst/SKILL.md) | Intelligence cycle (FRAME → GAP-SCAN) |
| **Collection** | Acquires raw signals in specified form | This skill's routing table (below) | Fetch, scrape, poll, ledger-write |

The Analyst **commands** collectors; it does not passively receive their output. Every collection
run starts with an Analyst FRAME (decision, primary question, sub-questions, confidence threshold).
Every collection run ends with Analyst EVALUATE + SYNTHESISE before anything reaches the founder.

---

## What "growth" and "sustainability" mean here

| Dimension | Primary metrics | Collector owner | Ledger |
|---|---|---|---|
| **Growth** | LTV:CAC, blended CPA, channel HHI, attribution decay, pipeline velocity | `cmo-growth` | `.harness/swarm/cmo_state.jsonl` |
| **Financial sustainability** | Burn multiple, NRR, runway, gross margin, model-spend ratio | `cfo` | `.harness/swarm/cfo_state.jsonl` |
| **Technical sustainability** | DORA quartet, p99, uptime, cost-per-request | `cto` | `.harness/swarm/cto_state.jsonl` |
| **Customer sustainability** | NPS, FCR, GRR, first-response, churn threats | `cs-tier1` | `.harness/swarm/cs_state.jsonl` |
| **Outcome feedback** | Post-ship positive/negative/stale signals | `analyzing-customer-patterns` | `.harness/lessons.jsonl` |
| **Portfolio health** | Security scores, scan regressions | `pi-seo-health-monitor` | `.harness/scan-results/` |
| **External intelligence** | Market/competitor/tooling signals | Scout, `margot-bridge` | Linear `[SCOUT]` issues, `.harness/margot/` |
| **Accumulated context** | Founder wiki, prior research | `wiki-query` → `wiki-ingest` | `~/2nd Brain/2nd Brain/Wiki/` |

---

## Collection cycle (operational)

Run this stack for every growth/sustainability question. The Analyst owns steps 1–2 and 5–7;
collectors own 3–4.

```
1. ANALYST FRAME
   decision · primary question · sub-questions · confidence threshold

2. ANALYST DECOMPOSE
   load-bearing assumptions → priority collection targets

3. TASK COLLECTORS (parallel where independent)
   per sub-question: skill + exact data shape + source + minimum grade (B2 default)

4. COLLECTORS RETURN
   structured payloads only — no prose summaries without raw numbers/sources

5. ANALYST EVALUATE
   NATO/Admiralty grade each claim; reject/down-weight weak evidence explicitly

6. ANALYST SYNTHESISE
   §11 output format (question, answer, evidence, alternative, unknowns, kill-switch, next collection)

7. COMPOUND
   if durable → wiki-ingest; if action-shaped → margot-sandcastle-bridge; if daily metric → senior-agent ledger
```

Loop steps 2→7 until confidence threshold met **or** marginal collection cost exceeds value.
The Analyst must state which stop condition fired.

---

## Collector routing table

Dispatch collectors by sub-question type. Multiple collectors may run in parallel when file/skill
ownership does not overlap.

| Sub-question signal | Collector skill(s) | Typical data shape |
|---|---|---|
| Channel mix, ad spend, CAC, LTV | `cmo-growth`, `marketing-analytics-attribution` | Metrics row per business_id |
| SEO demand, keyword opportunity | `marketing-seo-researcher`, `pi-seo-scanner` | Keyword cluster JSON + difficulty |
| ICP, positioning, market size | `marketing-icp-research`, `marketing-positioning` | ICP canvas + cited sources |
| Burn, runway, margin, NRR | `cfo` | Metrics snapshot per business |
| Deploy reliability, latency, CI health | `cto` | DORA + p99 row |
| Support load, churn, NPS | `cs-tier1` | Ticket metrics + breach list |
| Shipped feature outcomes | `analyzing-customer-patterns` | Pattern JSON + outcome lessons |
| ZTE / pipeline maturity | `leverage-audit`, `zte-maturity` | Scorecard + dimension gaps |
| Fast-moving external topic | `wiki-query` then `margot-bridge` if go_external | Wiki answer + research body |
| AI/tooling landscape | Scout (`python -m app.server.agents.scout`) | Scored findings → Linear |
| Campaign / launch artefacts | `marketing-orchestrator` wave plan | Wave-plan JSON |

**Wiki-first rule:** Before any external research call, run `wiki-query`. Inject wiki context into
the Analyst FRAME; do not duplicate collection the wiki already answers at high confidence.

---

## Minimum collection quality bar

Collectors return **graded evidence**, not vibes:

- Every numeric claim carries `source`, `as_of` date, and NATO/Admiralty grade (Analyst assigns if collector cannot).
- Proxy metrics must state the proxy, the target, and known failure modes.
- Synthetic provider data (senior-agent default) is tagged `provider: synthetic` — Analyst downgrades to `C3` until real wire confirmed.
- Two outlets repeating one origin = one source (Analyst dedupes before counting corroboration).

Default actionable floor: **B2** (usually-reliable source, probably-true claim). Below that → gap, not conclusion.

---

## Daily composition path

The 06:00 UTC executive brief (`daily-6-pager`) is the **downstream consumer** of this method:

1. Senior agents write per-cycle ledger rows (collection layer, unattended).
2. Analyst-style synthesis is embedded in each agent's `assemble_daily_brief()` (deterministic).
3. Non-trivial strategic questions bypass the daily brief and run the full Analyst cycle explicitly.

When a daily brief section shows a breach, the Analyst loop may be invoked for root-cause — not
just the metric snapshot.

---

## Analyst doctrine (direction layer)

The full Research & Intelligence Doctrine — identity, prime directives, collection cycle,
evidence grading, gap engine, acquisition pathways, ACH, scenario planning, domain lenses,
self-audit, and §11 output format — lives in [`analyst/SKILL.md`](../analyst/SKILL.md).

**Non-negotiable:** No growth/sustainability conclusion ships to the founder without Analyst §11
items 4–6 (leading alternative, critical unknowns, kill-switch). A number without a kill-switch
is a dashboard widget, not intelligence.

---

## Triggers

| When | Action |
|---|---|
| Founder asks "can we afford X" / "should we scale Y" | Full Analyst cycle + targeted collector tasks |
| Daily 06:00 UTC | Senior-agent ledgers → `daily-6-pager` (collection unattended) |
| Board meeting prep | Analyst FRAME on board brief → parallel collector fan-out |
| Margot research complete | Analyst EVALUATE before `wiki-ingest` or `margot-sandcastle-bridge` |
| Scout weekly run | Analyst triages top findings; rest archived |

---

## Safety bindings

- **PII:** All founder-facing output through `pii-redactor` before `draft_review`.
- **HITL:** Spend/refund/production gates stay with senior-agent dual-key ceilings — Analyst recommends; agents gate.
- **Kill-switch:** `TAO_SWARM_ENABLED=0` stops new collection tasks; in-flight Analyst evaluations complete and queue.

---

## Verification

1. Analyst FRAME on a test question ("Should we raise CMO ad-spend on Synthex?") produces sub-questions + confidence threshold before any collector runs.
2. Collector returns include source + date; Analyst grades each claim.
3. Final deliverable includes items 4–6 from Analyst §11.
4. `wiki-query` runs before `margot-bridge` on repeat topics.
5. Daily brief still assembles when Analyst loop skipped (metric-only path).

---

## References

- Analyst doctrine: [`analyst/SKILL.md`](../analyst/SKILL.md)
- Senior agents: `cfo`, `cmo-growth`, `cto`, `cs-tier1`
- Daily brief: `daily-6-pager`
- Wiki flywheel: `wiki-query`, `wiki-ingest`
- External research: `margot-bridge`, Scout (`app/server/agents/scout.py`)
