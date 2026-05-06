# RA-2026 — HERMES Deployment & Brand Resonance Engine

**Lead Systems Architect blueprint** · 2026-05-06 · v1 (post-Phase-1)

> "World Best IPO/Publicly Listed Business" operational standards through autonomous, proactive intelligence + brand consistency + content automation.

## Status of this document

* **Phase 1 (foundation) is shipped** — PR #198 merged as `770e78c` on 2026-05-06.
  - `app/server/discovery.py` four-protocol pipeline (SCAN/GAP/PROPOSAL/ESCALATE) with pluggable hooks
  - `swarm/margot_tools.propose_idea(originator="discovery_loop")` with dual-label application
  - `app/server/cron_triggers.py` `discovery` trigger type
  - `.harness/projects.json` `business_charter` field added for 7 portfolio personas
  - `~/.hermes/business-charters/restoreassist.md` proof-of-pattern charter
  - 35 new tests passing; full suite 1101 green
* **Phases 2-5 are scoped here**, ready for implementation as sub-issues.

The expanded brief (operator 2026-05-06 evening) extends the previous 4-phase blueprint to include **Brand Resonance Agents** and **Remotion video automation**, and adds a **Phase 5 Execution Roadmap**. The pluggable hook architecture in Phase 1's `discovery.py` was deliberately designed to admit these without re-architecting the foundation.

## Critical insights (load-bearing)

1. **Hermes is the FACE, Pi-CEO is the BRAIN.** Hermes daemon stays single-tenant (Margot-only); 13+ portfolio personas live in Pi-CEO Railway. New personas extend `swarm/` + emit findings via Margot's existing bridge — never spawn new Hermes daemons. Documented in Phase 1's PR body.
2. **Gemma 4 SCAN-only.** `~/.hermes/config.yaml` documents Gemma 4 26B was demoted on 2026-05-03 because it dropped 0/6 mandatory tool-calls. It works for *summarisation over already-fetched text* — that's the SCAN protocol's scope. GAP/PROPOSAL/ESCALATE use Llama 3.3 70B (OpenRouter open-source, ~$0.001/day) per RA-1099. Anthropic Sonnet/Opus reserved for Senior PM + Board only.
3. **Brand Resonance is a post-PROPOSAL gate, not a parallel pipeline.** Audit fires after the Proposal protocol drafts a Linear ticket; if the proposal violates the persona's brand-essence adjective set, Brand Resonance Agent rewrites the proposal voice (not the substance) before Linear creation. Minimal latency overhead (~1-2s extra Llama call), no architectural duplication.
4. **Remotion is a downstream consumer, not a Discovery protocol.** When a sev≥6 PROPOSAL has a content-generation gap class (marketing, market, competitive), the existing `remotion-orchestrator` skill is invoked as a follow-on dispatch. Discovery loop emits a `remotion_brief` payload onto the existing Linear ticket as an attachment; remotion-orchestrator picks it up off a separate cron + queue.
5. **Linear is the kanban + the source-of-truth + the destination.** Operator clarification 2026-05-06: "operational across all businesses constantly". The existing autonomy loop (RA-1289) already polls every portfolio project for autonomous-labeled Todos. Discovery adds findings ingestion alongside.

## Phase 1: Persona-Agent Mapping Matrix (with Brand Essence)

Each persona maps to: location (Hermes daemon vs Pi-CEO backend), model assignment, MCP tool surface, input/output channels, and **Brand Essence adjective set** (the new dimension from the expanded brief).

The Brand Essence adjective set is what every output is audited against — three to five adjectives that capture the persona's psychological consistency. These are charter-driven (extracted from the `## Brand Essence` section of each business charter file).

| # | Persona | Location | Model (SCAN / GAP+PROPOSAL / ESCALATE) | Brand Essence adjectives | Input | Output |
|---|---|---|---|---|---|---|
| 1 | Margot (CoS) | Hermes daemon `~/.hermes/config.yaml` channel_prompts | Llama 3.3 70B (existing) | Direct, brief, loyal, decisive | Telegram 8792816988 | Telegram founder; bridges Pi-CEO |
| 2 | CEO Board (9-persona) | Pi-CEO `skills/ceo-board/SKILL.md` | Opus 4.7 (RA-1099 planner only) | Strategic, contrarian-tested, principled | Margot `[BOARD-TRIGGER]` ≥7 + Discovery sev≥7 | Board minutes → Obsidian → Telegram |
| 3 | CFO | Pi-CEO `swarm/cfo.py` | Llama 3.3 70B (Sonnet on $1K) | Disciplined, conservative, evidence-based, runway-aware | Cron + `[CFO]` | Linear (RA), morning-intel/ |
| 4 | CMO | Pi-CEO `swarm/cmo.py` | Llama 3.3 70B (Sonnet on $5K adspend) | Bold, measurable, channel-disciplined, attribution-honest | Cron + `[CMO]` + Discovery (market gaps) | Linear, marketing-studio, **Remotion brief** |
| 5 | CTO | Pi-CEO `swarm/cto.py` | Llama 3.3 70B (Sonnet on autopr) | Surgical, secure-by-default, no-surface-treatment (RA-1109), compounding | Autonomy loop + `[CTO]` | Linear, autopr, GitHub |
| 6 | CS | Pi-CEO `swarm/cs.py` | Haiku 4.5 (Sonnet on $100 refund) | Empathetic, accountable, fast-resolution, never-defensive | CCW Linear tickets | Linear, CCW handoff, Telegram |
| 7 | RestoreAssist | NEW `swarm/personas/restoreassist.py` (Phase 2) | Gemma 4 / Llama 3.3 70B / Sonnet | **Authoritative, compliance-first, field-grounded, IICRC-defensible** | Discovery `0 0/6 * * *` | RA Linear, Telegram digest, Remotion (training shorts) |
| 8 | Disaster-Recovery | NEW `swarm/personas/disaster_recovery.py` | Gemma 4 / Llama 3.3 70B / Sonnet | **Rapid-response, calm-under-pressure, accreditation-anchored** | Discovery `0 1/6 * * *` | DR Linear, Telegram, Remotion (case studies) |
| 9 | DR-NRPG | NEW `swarm/personas/dr_nrpg.py` | Gemma 4 / Llama 3.3 70B / Sonnet | **Standards-driven, contractor-empowering, audit-ready** | Discovery `0 2/6 * * *` | DR-NRPG Linear, Telegram |
| 10 | Synthex | NEW `swarm/personas/synthex.py` | Gemma 4 / Llama 3.3 70B / Sonnet | **Automation-native, attribution-proven, marketing-disciplined** | Discovery `0 3/6 * * *` | SYN Linear, Telegram, Remotion (product demos) |
| 11 | Unite-Group (CRM/portfolio infra) | NEW `swarm/personas/unite_group.py` | Gemma 4 / Llama 3.3 70B / Sonnet | **Integration-first, interoperable, portfolio-coherent** | Discovery `0 4/6 * * *` | UNI Linear, dashboard-unite-group |
| 12 | CARSI | NEW `swarm/personas/carsi.py` | Gemma 4 / Llama 3.3 70B / Sonnet | **Vertically-precise, client-outcome-driven, delivery-disciplined** | Discovery `0 5/6 * * *` | CARSI Linear, Telegram |
| 13 | ccw-crm (SaaS product) | NEW `swarm/personas/ccw_crm.py` | Gemma 4 / Llama 3.3 70B / Sonnet | **Customer-success-led, restoration-vertical, AI-native, dogfood-validated** | Discovery `0 0 * * *` | ccw-crm Linear, Telegram |
| 14 | CCW Client (read-only persona, external customer) | NEW `swarm/personas/ccw_client.py` | Haiku 4.5 ONLY | **Privacy-first, accountable, never-outbound** | CS escalations from ccw-crm | CS team only — NEVER outbound |

**Brand Essence enforcement:** Phase 3's Brand Resonance Agent reads each persona's adjective set + the proposed output (ticket title + body), scores adherence on each adjective (0.0-1.0), and either passes the output unchanged (all scores ≥0.7), rewrites the voice while preserving substance (any score 0.4-0.7), or rejects + flags for human review (any score <0.4). Rewrite is a single Llama 3.3 70B call with a brand-resonance prompt template that takes the offending output + the adjective set + the persona's charter as input.

## Phase 2: Autonomous Intelligence Workflow (extended)

Building on Phase 1's four-protocol pipeline, Phase 2 adds:

### Consumer Demand identification (the explicit ask in the operator brief)

Each persona's charter has a new `## Consumer Demand Signals` section listing 5-10 [REALTIME] or [RESEARCH] queries that surface demand-side movement:

* **Direct demand signals** — search-trend deltas (Google Trends, Perplexity), seasonal spike anticipation, regulatory-change-driven demand
* **Indirect demand signals** — competitor traffic spikes, adjacent-vertical regulator changes, partner platform pricing changes
* **Consumer language signals** — review-mining (G2, Capterra, Trustpilot for the persona's vertical), Reddit/forum sentiment shifts, podcast-mention frequency

The SCAN protocol fires both watch-list (strategic) and consumer-demand (tactical) queries every cycle. Findings are tagged with `signal_class: strategic | demand` so GAP analysis can apply different severity rubrics.

### GAP analysis extension — demand-gap identification

A new `gap_class: demand` joins the existing 6 classes. Demand-class findings score severity by:

* **Demand magnitude** — search volume / mention count vs 90-day baseline
* **Capability gap** — does any persona currently serve this demand? (cross-portfolio search via Linear closed tickets + active product surface)
* **Time-criticality** — seasonal / regulatory deadline proximity
* **Brand-fit** — does the persona's Brand Essence adjective set align with the surfaced demand language?

Demand-class findings with sev≥6 trigger the new **Brand Resonance Agent** + **Remotion brief generator** (Phase 3) before reaching PROPOSAL.

### PROPOSAL extension — Remotion-augmented tickets

When a demand-class proposal lands in Linear, the ticket body includes an additional `## Remotion Brief` section with:

* Suggested format (LinkedIn 30s / YouTube 60s / Reel / Internal training)
* Suggested motion-language style (matched to the persona's charter via existing `skills/remotion-motion-language/SKILL.md`)
* Suggested CTA + audience anchor
* Direct invocation prompt for `remotion-orchestrator` skill

The remotion-orchestrator polls Linear (or is invoked manually by the curator) for tickets bearing the `discovery-loop` + `remotion-brief` label combo, and runs the existing Remotion render pipeline (`skills/remotion-render-pipeline/SKILL.md` shipped in Wave 4 brand work).

## Phase 3: Brand & Content Integration Schema

### Brand Resonance Agent — architecture

A new module `app/server/brand_resonance.py` (Phase 3 sub-issue) implements:

```
audit_proposal(persona_id, title, description) -> AuditResult
  AuditResult {
    overall_score: float          # 0.0-1.0
    per_adjective_scores: dict    # {"authoritative": 0.85, ...}
    verdict: "pass" | "rewrite" | "reject"
    rewritten_title: str | None   # populated on "rewrite"
    rewritten_description: str | None
    violations: list[str]         # human-readable explanations
  }
```

**Audit rules:**

1. Pass (all scores ≥0.7): proposal goes through unchanged.
2. Rewrite (any score 0.4-0.7): single Llama 3.3 70B call with brand-resonance prompt; preserves substance, adjusts voice. Bounded to 2 retry rewrites max — if neither passes, escalate to reject.
3. Reject (any score <0.4): flag the proposal in Linear with a `brand-resonance-fail` label; notify the persona owner via Telegram with the failing adjective + the failing fragment. Don't auto-close — human triage.

**Wiring point:** `discovery.py::_propose()` calls `brand_resonance.audit_proposal()` between drafting and `margot_tools.propose_idea()`. Pluggable hook same pattern as the existing four protocols — `discovery.set_brand_resonance_auditor(fn)` so tests / phased rollouts can opt in/out per persona.

### Remotion integration — workflow

Existing skills in scope (already shipped):

* `remotion-brand-research` — produces BrandResearch dossier
* `remotion-brand-codify` — converts dossier → typed BrandConfig TS file
* `remotion-orchestrator` — entry point for the package
* `remotion-marketing-strategist` — channel + format tuning
* `remotion-screen-storyteller` — scene-by-scene script
* `remotion-composition-builder` — actual TSX builder (Sonnet 4.7 worker)
* `remotion-designer` — visual design QA
* `remotion-motion-language` — per-brand motion vocabulary
* `remotion-colour-family` — palette generator
* `remotion-render-pipeline` — voice synth + render + Telegram delivery + Linear ticket
* `marketing-orchestrator` — brand-aware copy + channel + SEO orchestrator

**The Discovery → Remotion bridge:**

1. Discovery PROPOSAL identifies a demand-class finding requiring content (sev≥6, gap_class ∈ {demand, market, competitive})
2. Brand Resonance Agent passes the proposal
3. Proposal drafter adds a `## Remotion Brief` section to the Linear ticket body with structured fields (format, audience, motion-language hint, CTA)
4. The Linear ticket carries labels `discovery-loop` + `margot-idea` + new `remotion-brief`
5. A new cron entry `remotion-brief-poller` (every 30 min) calls `remotion-orchestrator` for any open ticket with the `remotion-brief` label and no `remotion-rendered` label yet
6. `remotion-orchestrator` runs the full Remotion pipeline (research → codify → strategist → storyteller → designer → motion-language → composition-builder → render-pipeline)
7. On render success: `remotion-render-pipeline` adds `remotion-rendered` label, attaches the MP4 to the Linear ticket, and pings Telegram with the asset URL

### Channel-specific output formats

Per the operator brief (Social, YouTube, Podcasts, Web), Remotion produces:

* **LinkedIn** — 30s vertical (1080×1920) with text-on-screen captions
* **YouTube** — 60s landscape (1920×1080) with voice-over
* **Instagram Reel / TikTok** — 30s vertical, music + captions
* **Podcast cover-art motion** — 15s loop for Spotify Canvas / Apple Podcasts artwork
* **Web hero** — 8s autoplay loop, no audio

`remotion-marketing-strategist` already handles channel selection. Demand-class proposals carry a `target_channels` field that the strategist consumes.

## Phase 4: Communication & Escalation Layer

The existing escalation surfaces stay intact:

* **Board** (sev≥7 + strategic/regulatory): `swarm/board.py` (existing) consumes `[BOARD-TRIGGER]` events identical to Margot-emitted today. 9-persona deliberation kernel runs unchanged.
* **Telegram** (sev≥7 + time-critical): synthetic Margot-voiced outbound via existing `chief_of_staff` path. No new outbound channels (operator confirmed 2026-05-06: Telegram-only).

**New escalation paths from Phase 3:**

* **Brand Resonance failure** (any persona output flagged `brand-resonance-fail`): Telegram nudge to founder with the failing fragment + adjective + Linear deep-link. Bounded by per-persona daily rate limit (3/day) so the founder isn't spammed if a persona's voice drifts systemically.
* **Remotion render success** (any `discovery-loop` + `remotion-rendered` ticket): Telegram nudge with the MP4 URL + 1-line caption. Folded into the daily Margot digest by default (not interrupt-priority).
* **Cross-portfolio demand convergence** (≥3 personas surface the same demand-class finding within 24h): Sonnet 4.6 routing decision routes to Board (strategic) AND Telegram (time-critical). New `[DEMAND-CONVERGENCE]` internal sentinel to track the pattern.

**Rate limits (IPO-grade governance):**

* Board: max 2 deliberations/day, queue overflow until next UTC day
* Telegram interrupts: max 5 sev≥7 nudges/day across all personas
* Brand Resonance fails: max 3 nudges/persona/day
* Remotion render notifications: max 10/day total, batched into the daily 6-pager when over

## Phase 5: Execution Roadmap

Honest framing: Phase 1 is shipped. The remaining work is meaningful but non-trivial. Honest sequencing below — durations are eng-day estimates assuming the autonomy mandate keeps the loop tight (no waiting for review between phases).

### Wave 1 — Phase 2 sub-issues (week of 2026-05-06)

1. **RA-2027** — Author 6 remaining business charters (`disaster-recovery`, `dr-nrpg`, `synthex`, `unite-group`, `carsi`, `ccw-crm`, `ccw-client`) in `~/.hermes/business-charters/`. Charters can be machine-drafted from existing Linear cycle metadata + project descriptions, then operator-reviewed in 30 min batches. Add `## Brand Essence` section to each (3-5 adjectives) + `## Consumer Demand Signals` section (5-10 queries). Estimate: 0.5d
2. **RA-2028** — Author 7 persona modules in `swarm/personas/<id>.py` (~80 LOC each, all delegate to `discovery.run_persona_cycle`). Estimate: 0.5d (parallel-delegate across 4 sub-agents)
3. **RA-2029** — Wire production Perplexity hook in `discovery.py` (`set_perplexity_hook` registered in `app_factory.py` startup with a real `mcp__pi-ceo__perplexity_research` caller). Estimate: 0.5d
4. **RA-2030** — Wire production GAP classifier (Llama 3.3 70B prompt + JSON-output enforcement). Estimate: 0.5d
5. **RA-2031** — Wire production PROPOSAL drafter (Llama 3.3 70B prompt for ticket title + body composition). Estimate: 0.5d
6. **RA-2032** — Add 6 staggered Discovery cron entries to `cron-triggers.json` (one per persona); leave `enabled: false`. Estimate: 0.25d

**Wave 1 deliverable:** Discovery loop fires for all 7 personas in dry-run mode, writes ScanReports to `~/.hermes/discovery/<persona>/*.jsonl`, makes no Linear writes. 48h soak before flipping any persona to enabled.

### Wave 2 — Phase 3 (week of 2026-05-13)

1. **RA-2033** — Build `app/server/brand_resonance.py` with the audit/rewrite/reject pipeline. Estimate: 1d
2. **RA-2034** — Wire Brand Resonance into `discovery.py::_propose()` as a hook between drafting and Linear creation. Estimate: 0.25d
3. **RA-2035** — Add `## Remotion Brief` section to PROPOSAL drafter output for demand-class findings. Estimate: 0.25d
4. **RA-2036** — Build `remotion-brief-poller` cron entry + handler that invokes existing `remotion-orchestrator` skill. Estimate: 0.5d
5. **RA-2037** — Wire `[BRAND-RESONANCE-FAIL]` Telegram escalation path. Estimate: 0.25d

**Wave 2 deliverable:** Brand-resonance-audited proposals + Remotion-briefed demand findings. End-to-end smoke: a synthetic demand finding → Discovery → Brand audit → Linear ticket with Remotion brief → orchestrator picks up → MP4 delivered to Telegram.

### Wave 3 — Phase 4 (week of 2026-05-20)

1. **RA-2038** — Sonnet 4.6 ESCALATION router with rubric (strategic vs time-critical vs both). Estimate: 0.5d
2. **RA-2039** — Cross-portfolio demand-convergence detector + `[DEMAND-CONVERGENCE]` sentinel. Estimate: 0.5d
3. **RA-2040** — Rate-limit gates (Board ≤2/day, Telegram ≤5 interrupts/day, Brand-fail ≤3/persona/day). Estimate: 0.25d
4. **RA-2041** — Daily Remotion-rendered batch into the existing 6-pager (`swarm/six_pager.py`). Estimate: 0.25d

**Wave 3 deliverable:** IPO-grade governance: rate-limited, escalation-rubric'd, cross-portfolio-aware Discovery output. Founder receives ≤6 Telegram interrupts/day across all personas; everything else batches into the morning 6-pager.

### Wave 4 — Phase 5 IPO instrumentation (weeks of 2026-05-27 / 2026-06-03)

1. **RA-2042** — Discovery dashboard at `dashboard/app/discovery/page.tsx` with: per-persona scan-throughput, gap-class distribution, proposal→merged conversion, mean time to triage, escalation rate, brand-resonance pass rate, Remotion render conversion. Estimate: 2d
2. **RA-2043** — HMAC-signed audit trail to `~/.hermes/audit/discovery.jsonl`. Estimate: 0.5d
3. **RA-2044** — 90-day charter-refresh routine in `swarm/meta_curator.py`. Estimate: 0.5d
4. **RA-2045** — Per-persona loop-coverage SLA: alert when zero sev≥4 findings in 30 days. Estimate: 0.25d
5. **RA-2046** — Quarterly Brand Essence drift report (compare current persona output adjective scores vs charter). Estimate: 1d

**Wave 4 deliverable:** "World Best IPO" instrumentation. Every Discovery decision has a signed audit trail; every persona's loop-coverage is observable; brand drift is measurable quarterly.

### Wave 5 — Operational hardening (week of 2026-06-10)

1. **RA-2047** — Cost cap policy for Perplexity (~196 calls/day across 7 personas) — daily budget cap + overage policy. Estimate: 0.5d
2. **RA-2048** — Linear ticket auto-archive policy for stale unactioned sev-4-5 proposals (close after 14 days). Estimate: 0.5d
3. **RA-2049** — NotebookLM corpus weekly-refresh ownership clarification + curator routine. Estimate: 0.5d
4. **RA-2050** — CCW-Client persona privacy invariant — code-level enforcement (Haiku-only + zero outbound MCP tools). Estimate: 0.5d

**Wave 5 deliverable:** No silent unbounded resource consumption. CCW privacy boundary is code-enforced not policy-only.

### Total budget (Waves 1-5)

* **~10 engineering days** spread across 5 waves over 5 weeks
* Each wave ships independently; failure of one wave does not block others (Phase 1's hook architecture is the load-bearing decision that keeps later phases composable)
* Anthropic spend: bounded by RA-1099 — Sonnet only on routing/rewrite, Opus only on Board. Estimated <$10/day at full deployment (vs $0 today).
* Per-persona OpenRouter spend: ~$0.001/day (existing AkashML rate)
* Local Gemma 4 spend: $0

## Risks & open questions

These need operator decisions before Wave 2 begins:

1. **Perplexity ceiling.** 7 personas × 7 watch-list queries × 4 cycles/day = 196 calls/day. What's the monthly budget cap?
2. **NotebookLM corpus refresh ownership.** Discovery's GAP quality decays as corpus drifts. Weekly refresh — manual or automated?
3. **CCW-Client persona privacy.** Code invariant or policy-only? Recommend code (Haiku-only + zero outbound MCP tools enforced in module __init__).
4. **Linear ticket volume.** ~196 findings/day × 7 boards risks Linear quota exhaustion within 30 days. Auto-archive policy for stale unactioned sev-4-5 proposals (Wave 5 RA-2048)?
5. **Board deliberation cost.** Sev≥7 escalations could fire multiple Boards/day at Sonnet rates. Cap at 2/day with queue overflow (Wave 3 RA-2040)?
6. **Brand-resonance prompt tuning.** Each persona's adjective set needs a ground-truth set of pass/rewrite/reject examples to tune the audit prompt. Operator-supplied or machine-drafted from existing Margot output?
7. **Remotion render cost.** Existing Wave 4 brand work used ElevenLabs + Remotion in pipeline. Per-render cost? Daily cap?

## Critical files / paths

**Phase 1 (shipped, sha 770e78c):**

* `app/server/discovery.py` — four-protocol pipeline + hooks
* `swarm/margot_tools.py` — `propose_idea(originator)` + dual labels
* `app/server/cron_triggers.py` — `discovery` trigger type
* `.harness/projects.json` — `business_charter` field
* `.harness/cron-triggers.json` — proof-of-pattern entry
* `~/.hermes/business-charters/restoreassist.md` — proof-of-pattern charter
* `tests/test_discovery.py` — 35 tests

**Phase 2 (Wave 1 sub-issues):**

* `~/.hermes/business-charters/<persona>.md` × 7 — author each with `## Brand Essence` + `## Consumer Demand Signals`
* `swarm/personas/<persona>.py` × 7 — thin delegators
* Production hooks in `app/server/app_factory.py` startup or a new `app/server/discovery_wiring.py`
* `.harness/cron-triggers.json` — 6 staggered cron entries

**Phase 3 (Wave 2 sub-issues):**

* `app/server/brand_resonance.py` — NEW
* Hook registration in `discovery.py`
* `remotion-brief` poller in `cron_triggers.py`

**Phase 4 (Wave 3 sub-issues):**

* `app/server/escalation_router.py` — NEW (Sonnet rubric)
* `app/server/demand_convergence.py` — NEW (cross-portfolio aggregator)
* Rate-limit gates wired into discovery + Telegram + Board

**Phase 5 (Wave 4-5 sub-issues):**

* `dashboard/app/discovery/page.tsx` — Next.js
* `~/.hermes/audit/discovery.jsonl` — signed audit log
* Curator routines in `swarm/meta_curator.py`

## References

* RA-2002 — Margot ideas bridge (the propose_idea foundation we extended)
* RA-2003 — Corpus grounding env wiring
* RA-2022 — `use_corpus=True` fix (corpus actually queried)
* RA-1289 — Autonomy loop portfolio span
* RA-2016 — Cron catch-up scope expansion
* RA-1099 — Model policy (Opus reservation)
* RA-1109 — Surface treatment prohibition
* RA-1888 — Portfolio Pulse foundation
* Margot's Wave 5.1 — handle_turn pipeline + sentinel surface
* Wave 4.1 — CFO/CMO/CTO/CS senior bot engines
* Wave 4 brand work — Remotion skills (10 skills shipped, ready for Phase 3 integration)
