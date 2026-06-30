# Board Meeting Minutes — Cycle 0 (2026-06-11)

## Business Velocity Index (RA-696)
**BVI: 1** (-49 from prior cycle)
- CRITICALs resolved: 1
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 50

## Attendees
- Pi CEO Autonomous Agent (Orchestrator)
- CEO Board: 9 personas (CEO, Revenue, Product Strategist, Technical Architect,
  Contrarian, Compounder, Custom Oracle, Market Strategist, Moonshot)
- Gap Audit Agent

## Phase 1 — STATUS
- ZTE Score (v1): 85/100
- ZTE Score (v2): 83/100 [Zero Touch] (v1 base 75 + Section C 8/25)
- Urgent Issues: 10
- Cron Health: unknown

## Phase 2 — LINEAR REVIEW
- Urgent: 5 | High: 25
- Stale: None
- Unassigned: RA-6500, RA-6485, RA-6499, RA-6484, RA-6486, RA-6489, RA-6462, RA-6490, RA-6498, RA-6497, RA-6496, RA-6495, RA-6470, RA-6475, RA-6491, RA-6483, RA-6482, RA-6481, RA-6461, RA-6464, RA-6471, RA-6472, RA-6469, RA-5713, RA-5968, RA-5725, RA-5724, RA-5723

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 165.9s)

**Finding #1** [HIGH] — _What are the exact pricing changes Anthropic is implementing for Claude API on or around 22 June 2026 that would affect the Mythos-as-planner strategy?_
  No pricing changes specifically dated 22 June 2026 appear in any primary source. The materially relevant cluster is: (1) June 9 — Claude Mythos 5 launched at $10/$50 per MTok input/output (limited availability, Project Glasswing only), with a new tokenizer that produces ~30% more tokens for the same text versus pre-Opus-4.7 models — an effective cost increase even at unchanged per-token rates; (2) June 15 — Claude Sonnet 4 and Claude Opus 4 retired on the API; (3) June 15 — subscription Agent SDK credit split takes effect, moving programmatic claude-agent-sdk calls to a separate monthly credit pool ($20/$100/$200 for Pro/Max-5x/Max-20x, no rollover). Additionally, Mythos 5 hard-blocks temperature/top_p/top_k non-default values and thinking:{type:"disabled"} with a 400 error, and requires 30-day data retention (ZDR not available).
  - [Pricing - Claude API Docs](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-06-11)
  - [Claude Platform Release Notes](https://platform.claude.com/docs/en/release-notes/overview) (fetched 2026-06-11)
  - [Anthropic's June 15 Billing Change: What Every Claude Code & Agent SDK User Must Do](https://codersera.com/blog/anthropic-june-2026-billing-change-claude-code/) (fetched 2026-06-11)
**Finding #2** [HIGH] — _Are there any known breaking changes or deprecations in the Claude Agent SDK released in the last 30 days that could affect the Pi-CEO orchestrator pipeline?_
  Three hard breaking changes in the last 30 days affect any pipeline targeting Opus 4.8 (May 28) or Fable 5/Mythos 5 (June 9): setting temperature, top_p, or top_k to non-default values now returns a 400 error on all three models; thinking:{type:"disabled"} and assistant prefill return 400 on Fable 5/Mythos 5; and the new tokenizer (Opus 4.7 lineage) adds ~30% more tokens per prompt, bloating planning calls. Separately, the June 15 billing split moves Agent SDK calls to a separate metered credit — a financial break, not a code break. Claude Opus 4.1 was deprecated June 5 with retirement August 5; Sonnet 4 and Opus 4 retired June 15.
  - [Claude Platform Release Notes](https://platform.claude.com/docs/en/release-notes/overview) (fetched 2026-06-11)
  - [Anthropic June 15 Double Hit: Agent SDK Leaves Your Subscription, Claude 4 Retires](https://usagebox.com/articles/anthropic-june-15-agent-sdk-credit-split-claude-4-retirement) (fetched 2026-06-11)
  - [Claude Agent SDK Changes June 15 2026: Migration Playbook](https://theplanettools.ai/blog/claude-agent-sdk-billing-model-deprecation-june-15-2026-migration-playbook) (fetched 2026-06-11)
**Finding #3** [HIGH] — _What is the current status of Telegram Bot API getUpdates long-polling vs webhook conflicts — has Telegram published any guidance or rate-limit changes affecting concurrent pollers in 2026?_
  No new 2026 guidance or rate-limit changes have been published. The official API docs maintain the existing mutual-exclusion rule: getUpdates will not work while a webhook is set (and vice versa), returning a 409 Conflict for concurrent use. The May 2026 Bot API 10.0 release addressed guest mode, chat management, polls, and live photos — no changes to update-delivery policy or getUpdates rate limits. The only documented conflict mechanism remains the 409 error on simultaneous polling from the same token.
  - [Telegram Bot API](https://core.telegram.org/bots/api) (fetched 2026-06-11)
  - [OpenClaw Telegram 409 Conflict Fix — 2026 Checklist](https://kuoo.uk/en/blog/openclaw-telegram-409-conflict-getupdates-fix-2026/) (fetched 2026-06-11)
  - [Long Polling vs Webhook — How Telegram Bots Receive Updates](https://gramio.dev/updates/webhook) (fetched 2026-06-11)

**Open questions** (research could not resolve):
  - No primary source documents any pricing or API change specifically dated 22 June 2026 — the question premise may reference an internal calendar note or rumour not yet publicly announced; confirm whether a specific Anthropic communication triggered this date.
  - Whether Pi-CEO's existing Mythos-as-planner calls set temperature/top_p/top_k (would hard-break on Mythos 5 today) or use thinking:{type:"disabled"} — not determinable from public sources alone.
  - Whether Pi-CEO's Project Glasswing access is confirmed for Mythos 5 (limited availability gating) — not verifiable externally.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)
**CEO:** The June 15 billing cliff (#1, #2) is not a calendar note — it's a hard forcing function that hits in four days, and with 10 urgent issues open and ZTE v2 regressing from 85→83, the system is drifting while the deadline approaches. Mythos-as-planner (RA-6469) and the Agent SDK credit split need to resolve this week; everything else queues behind those two or it doesn't matter. Ruthless cut: fix Telegram foundation (RA-6462/6486), validate Mythos access and model-call safety, then ship RestoreAssist — in that order.

**Revenue:** RestoreAssist's organic launch (RA-5036) is live today via Synthex and the delivery channel is broken (RA-6462) — that's a campaign with a perishable window firing into a dead socket. The June 15 Agent SDK billing split (#1) means any cost model we've quoted clients for orchestration-backed features is already wrong and needs repricing before invoices go out. Every day Telegram stays broken is direct revenue leakage from a campaign we're already paying for.

**Product Strategist:** The silent auto-promote bug (RA-4863) is a correctness defect, not a polish item — in a restoration workflow, a record showing COMPLETED without SP-A close will generate support noise at the exact moment RestoreAssist is scaling from the organic campaign. The WCAG 1.4.4 fail (RA-4864) compounds this: we're asking clients in a regulated industry to trust a product that fails basic accessibility compliance on every page. Both of these need gates before client volume increases, not after.

**Technical Architect:** Finding #2 is a silent landmine — if any Pi-CEO planning call passes non-default temperature, top_p, or top_k to Mythos 5 or Opus 4.8, it returns a 400 today, not a graceful degradation. The ~30% token inflation from the new tokenizer will silently blow every planning timeout and cost budget that was calibrated against pre-Opus-4.7 models without triggering any error signal. Before RA-6469 is called "operational," every model call in the orchestrator pipeline needs an explicit parameter audit against the new constraint set.

**Contrarian:** The Technical Architect's call to "audit every model call" before June 22 assumes Project Glasswing access is confirmed for Mythos 5 — Finding #1 explicitly flags this as *unverifiable externally*, making RA-6469's deadline structurally premature (confidence: low). The CEO's framing of "fix Telegram, then ship" also understates blast radius: RA-6462 and RA-6486 are not independent — a duplicate poller means any fix to one can re-break the other if deployed without coordinated cutover, and we have no evidence the current architecture cleanly separates the two paths.

**Compounder:** The fleet comms channel (RA-6499, RA-6500) is the most undervalued item on this board — without reliable Mac Mini connectivity, every autonomous overnight session is unmonitorable and the 10x autonomous-operator vision is a fiction running on a single machine. Fixing it once compounds across every future session; not fixing it means manually babysitting each run indefinitely. The Telegram duplication fix (RA-6486) is the same pattern: foundation rot that taxes every future delivery, not a one-off incident.

**Custom Oracle:** The RA-4863 silent auto-promote is a regulatory liability in an insurance-linked restoration environment — a COMPLETED record without SP-A close creates an audit trail gap that exposes clients to claim disputes, and in this industry that is a termination event, not a support ticket. The 30-day data retention requirement on Mythos 5 (#1, ZDR not available) also needs a formal risk assessment before any client data flows through a Mythos-backed planner, given the sensitivity of restoration job data. Do not scale RestoreAssist until both of these have documented mitigations.

**Market Strategist:** Mythos 5 launching at $10/$50/MTok (#1) with ~30% token inflation means every competitor with Project Glasswing access is also paying a premium for the same capability ceiling — the differentiation window is narrow and cost-disadvantaged from day one. The June 15 Sonnet 4/Opus 4 retirements (#1) are an external forcing function that competitors face equally, but the ones who completed their model-call audits *before* the deadline will gain velocity while others firefight. Being first to a clean Mythos integration is a positioning move, not just an operational task.

**Moonshot:** If the fleet channel (RA-6499, RA-6500) fully closes and Mythos-as-planner (#1) proves stable at $10/$50/MTok, the ceiling is a self-healing, cross-machine autonomous operator that reasons at frontier level without human babysitting — that's not a task queue, that's a founder OS. The 30% token inflation from the new tokenizer (#2) is expensive friction today but it's the price of buying into a reasoning layer that can plan multi-week campaigns, not just execute steps. The real 10x question is whether we architect Mythos as a dumb planner swap or as the cognitive core the whole system routes through.

---

**CEO SYNTHESIS:** The June 15 cliff (#1, #2) lands in four days — Mythos access confirmation, parameter audit, and billing repricing are this week's non-negotiables, not June 22 aspirations. Telegram and fleet connectivity are the infrastructure failures making every other fix unreliable; the Contrarian is right that RA-6462 and RA-6486 require coordinated cutover, not sequential patches. Hold the line at *operationally sound before scaled*: RestoreAssist goes wide only after Telegram is clean, RA-4863 is gated, and Mythos model calls are confirmed parameter-safe.

## Phase 3 — SWOT


## Phase 4 — SPRINT RECOMMENDATIONS
PRIORITY 1: **RA-6486** — Stop the duplicate Telegram poller — the broken comms channel (RA-6462) is a force-multiplier failure: every autonomous alert, mesh status update, and TAO notification is silently dropped until this is resolved, making all other fleet work effectively blind.
**Estimate: XS (<1h) — Impact: Restores real-time ops visibility across the entire fleet; unblocks RA-6462 and RA-6499 which are currently stalled behind it.**

---

PRIORITY 2: **RA-6500** — Enable Remote Login on Mac Mini — this is the single hard prerequisite blocking the entire Mac Mini onboarding sequence (RA-6484 → 6485 → 6486 all depend on SSH access), meaning the Nexus Mesh fleet cannot activate until this one config change is made.
**Estimate: XS (<1h) — Impact: Unblocks 4 downstream tickets and puts RA-6474/6475 (Nexus Mesh activation) within striking distance this sprint.**

---

PRIORITY 3: **RA-6496** — Synthex product demo 60s — with three near-duplicate Synthex content tickets open (6481–6483, 6496–6498), the 60s demo is the highest-funnel asset and the dependency that unlocks the AEO explainer and onboarding walkthrough; shipping it collapses all six tickets into one deliverable.
**Estimate: M (2–4h) — Impact: Direct ZTE commercial contribution; activates Synthex top-of-funnel and clears a cluster of six backlog tickets simultaneously.**

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 3
- Low: 5
- Tickets created: RA-6502, RA-6503, RA-6504

_Generated 2026-06-11T05:08:29.163470+00:00_