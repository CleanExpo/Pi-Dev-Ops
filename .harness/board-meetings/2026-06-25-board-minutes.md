# Board Meeting Minutes — Cycle 0 (2026-06-25)

## Business Velocity Index (RA-696)
**BVI: 1** (0 from prior cycle)
- CRITICALs resolved: 1
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 1

## Attendees
- Pi CEO Autonomous Agent (Orchestrator)
- CEO Board: 9 personas (CEO, Revenue, Product Strategist, Technical Architect,
  Contrarian, Compounder, Custom Oracle, Market Strategist, Moonshot)
- Gap Audit Agent

## Phase 1 — STATUS
- ZTE Score (v1): unknown
- ZTE Score (v2): 96/100 [Zero Touch Elite] (v1 base 75 + Section C 21/25)
- Urgent Issues: 10
- Cron Health: unknown

## Phase 2 — LINEAR REVIEW
- Urgent: 10 | High: 20
- Stale: RA-6812 (4d stale), RA-6815 (4d stale), RA-6469 (4d stale), RA-6678 (7d stale), RA-6801 (7d stale), RA-6792 (7d stale), RA-6791 (7d stale), RA-2996 (7d stale), RA-2989 (7d stale), RA-2997 (7d stale), RA-2970 (8d stale), RA-2954 (8d stale), RA-3005 (8d stale), RA-5689 (8d stale), RA-2947 (8d stale), RA-2998 (8d stale), RA-1807 (8d stale), RA-6688 (8d stale), RA-2974 (8d stale), RA-6670 (8d stale), RA-5624 (8d stale), RA-6569 (8d stale), RA-2074 (8d stale), RA-5651 (8d stale), RA-5708 (8d stale), RA-5712 (8d stale), RA-5721 (8d stale), RA-6498 (8d stale), RA-6483 (8d stale)
- Unassigned: RA-6774, RA-6812, RA-6815, RA-6469, RA-6801, RA-2996, RA-2989, RA-2997, RA-2970, RA-2954, RA-3005, RA-2947, RA-2998, RA-1807, RA-6688, RA-2974, RA-6670, RA-5624, RA-6569, RA-2074, RA-5651, RA-5708, RA-5712, RA-5721, RA-6498, RA-6483

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 155.7s)

**Finding #1** [MEDIUM] — _What is Anthropic's current policy on trial credits and API key requirements for platform-managed accounts as of June 2025?_
  New Anthropic Console accounts receive a small amount of free credits on sign-up (official docs confirm credits exist but do not state the dollar amount; third-party sources report $5). A proposed June 15 2026 change that would have split Agent SDK usage into separate per-user credit pools at full API rates was reversed on June 16 2026; Agent SDK, claude -p, and ACP usage continue on existing subscription terms until Anthropic provides advance notice of any future change.
  - [Pricing - Claude API Docs](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-06-25)
  - [What Anthropic's New Claude Billing Means for Zed Users — Zed's Blog](https://zed.dev/blog/anthropic-subscription-changes) (fetched 2026-06-25)
**Finding #2** [HIGH] — _Has Anthropic announced any changes to Claude API pricing or access tiers in the 30 days prior to June 25 2026 that would affect orchestrator cost modelling?_
  Two material changes affect orchestrator cost modelling since May 26 2026: (1) Claude Fable 5 and Claude Mythos 5 launched June 9 at $10/$50 per MTok input/output (roughly 60% cheaper than Mythos Preview at $25/$125), with Batch API at $5/$25; (2) Claude Managed Agents pricing was introduced at $0.08 per session-hour on top of standard token rates, with Batch API discount, Fast Mode, and Data Residency multipliers explicitly excluded from Managed Agent sessions.
  - [Pricing - Claude API Docs](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-06-25)
  - [Claude Fable 5 and Claude Mythos 5 — Anthropic](https://www.anthropic.com/news/claude-fable-5-mythos-5) (fetched 2026-06-25)
**Finding #3** [HIGH] — _What is the current ABR (Australian Business Register) API status and any known outages or GUID format changes affecting ABN lookups?_
  All ABR web services (ABN System, Apply for an ABN, Update your ABN, ABR Web Services, Identifier Search) are fully operational as of June 25 2026, with no incidents recorded since at least June 11 2026. No GUID format changes were surfaced on the official status page or in any search results.
  - [Australian Business Register Status](https://status.abr.gov.au/) (fetched 2026-06-25)
**Finding #4** [MEDIUM] — _Are there any publicly announced pricing changes from Mythos or competing AI planner platforms effective around 22 June 2026?_
  In the AI API context, 'Mythos' resolves to Anthropic's Claude Mythos model tier. The key change effective June 23 2026 is that Claude Fable 5 (the public Mythos-class model) was removed from no-extra-cost subscription access (Pro, Max, Team, Enterprise) after a free-access window from June 9–22; API pricing remained fixed at $10/$50 per MTok from launch. No evidence of pricing changes from any separate company or product named 'Mythos' was found across three searches.
  - [Claude Fable 5 and Claude Mythos 5 — Anthropic](https://www.anthropic.com/news/claude-fable-5-mythos-5) (fetched 2026-06-25)

**Open questions** (research could not resolve):
  - Exact dollar amount of Anthropic's new-account trial credits — official docs confirm credits exist but do not specify the amount; third-party sources cite $5 but no primary source confirmed this.
  - Whether any GUID format changes have been made or are planned for the ABR ABN Lookup API — no announcement found; direct confirmation requires contacting ABR support on 139226.
  - Whether a standalone company or SaaS product called 'Mythos' (distinct from Claude Mythos) has announced pricing changes effective around 22 June 2026 — no evidence found after three searches.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)


## Phase 3 — SWOT
**SWOT — Pi-CEO | Cycle ending 2026-06-25**

---

**STRENGTHS**
- **ZTE 96/100** confirms the autonomous harness can self-operate without human scaffolding — kill-switches, judge-gated loops, and model-policy enforcement are all wired and holding.
- **Senior-agent topology** (CFO/CMO/CTO/CS) gives executive-level automated visibility with dual-key gates; no other indie DevOps platform in this class has this layer.
- **Multi-layer CI gate** (ruff + tsc + smoke-prod) prevents regressions from reaching prod even when the generator misfires.
- **Rich observability** (Supabase fire-and-forget, Linear auto-ticket, Telegram watchdog) means failures surface without manual polling.
- **Comprehensive scope contracts** exist (`TAO_MAX_ITERS`, `TAO_MAX_COST_USD`, `HARD_STOP_FILE`) — the policy machinery to contain runaway agents is in place.

---

**WEAKNESSES**
- **BVI = 1, MARATHON completions = 0.** The autonomy loop is spinning but not completing deep work. High ZTE + near-zero velocity = the engine idles in neutral.
- **Generator reliability is broken.** Four evaluator lessons scored 1.0/10 across completeness, correctness, conciseness, and format — empty diffs shipped as output. The core value prop (autonomous code generation) is misfiring, not just underperforming.
- **Backlog rot: 29 stale items, 26 unassigned.** Auto-assignment routing is not functional; the autonomy loop's `Urgent → High` scan isn't picking these up or completing them.
- **Scope violations at scale** (lesson `evaluator/hotfix`: 591 files modified vs max 15) mean the generator sometimes destroys more than it builds — surgical-change discipline is not enforced at the generator layer, only at the policy layer.
- **Sandbox env divergence** (lesson `sprint-12-review/scheduled-tasks`, `watchdog`) causes false CRITICAL alerts. After one false alert, every subsequent alert is suspect — alert fatigue is already a real risk.

---

**OPPORTUNITIES**
- **30 open Urgent/High issues** are a pre-prioritised queue. Fixing generator reliability unlocks an immediate BVI multiplier without any new product work.
- **Judge-gated loop (RA-1970) is implemented but not wired into `sessions.py`.** Completing that integration would add a quality floor that stops 1.0/10 outputs from being treated as done.
- **Semantic RAG memory** (lesson `TurboQuant` assessment) is scoped and architecturally sound — per-project `memory/` + retrieval step before session start would shrink context waste and improve plan quality, directly attacking the empty-diff failure mode.
- **Per-team orphan recovery (RA-1973)** can mechanically unstick stale issues. Configuring `TAO_ORPHAN_RECOVERY_STATES` per team converts 8-day stale items into re-queued work automatically.
- **ZTE 96 is a marketable artefact.** At launch, it's a concrete, scored proof-of-autonomy that competitors can't claim — leverage it in positioning before the score degrades.

---

**THREATS**
- **Generator producing empty diffs is an existential defect.** If the autonomous build loop ships nothing or ships scope violations, clients and internal stakeholders lose confidence in the whole platform regardless of ZTE score.
- **API key env hygiene failures** (lessons: `ANTHROPIC_API_KEY=""` inherited by children; `op://` literals not resolved; Vercel trailing `\n`) create silent 401s that manifest as "Claude did nothing" — indistinguishable from a generator bug without careful log triage.
- **False CRITICAL alerts from sandbox environments** (lesson: watchdog cried wolf on 2026-04-12) erode the Telegram alert channel's usefulness. One more false positive and the channel will be treated as noise.
- **Scope violation (591 files)** on an auto-routine with a `max 15` contract means a single runaway session can corrupt a repo's history and require a force-push — a destructive action that requires human intervention and breaks the ZTE claim.
- **29 stale + 10 urgent open + no completions** signals the autonomy loop may be entering a low-grade deadlock pattern — sessions start, stall, and time out without marking issues complete. If the poller doesn't detect this, the backlog compounds silently.

## Phase 4 — SPRINT RECOMMENDATIONS
**PRIORITY 1: RA-6678 + RA-6801 + RA-6792 (cluster)** — These three P0s form a single dependency chain (broken ABN env var → broken onboarding → broken report export) and all are already In Review, meaning the sprint work is merge + smoke-test, not build. — **Estimate: M (2–4 h)** — **Impact:** Directly unblocks the first paying customer path end-to-end; no ZTE effect, but eliminates the external revenue blocker that makes every platform metric moot if left open.

---

**PRIORITY 2: RA-1807** — Prod schema drift (37 tables + many columns missing despite recorded migrations) is a foundational reliability issue that silently degrades every DB-touching feature and makes any new autonomy output untrustworthy the moment it touches the database layer. — **Estimate: L (4–8 h)** — **Impact:** Closes the widest class of silent runtime failures; restores DB-layer confidence as a prerequisite for any meaningful ZTE velocity gain — the autonomy loop cannot complete work it cannot persist.

---

**PRIORITY 3: New ticket — "Wire max-file-scope guard and non-empty-diff assertion into the evaluator gate"** — The SWOT's four evaluator lessons scoring 1.0/10 and the 591-file scope violation both trace to the same root: the evaluator accepts completions without asserting that the diff is non-empty and within the 15-file surgical-change limit. — **Estimate: M (2–4 h)** — **Impact:** MARATHON completions move off zero; BVI rises from 1; ZTE velocity component lifts because the autonomy loop stops grading empty or destructive diffs as successes — this is the highest-leverage single fix for the platform's stated autonomous-code-generation value prop.

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 3
- Low: 4
- Tickets created: None

_Generated 2026-06-25T05:09:04.619992+00:00_