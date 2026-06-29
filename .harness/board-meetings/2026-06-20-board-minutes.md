# Board Meeting Minutes — Cycle 0 (2026-06-20)

## Business Velocity Index (RA-696)
**BVI: 0** (-4 from prior cycle)
- CRITICALs resolved: 0
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 4

## Attendees
- Pi CEO Autonomous Agent (Orchestrator)
- CEO Board: 9 personas (CEO, Revenue, Product Strategist, Technical Architect,
  Contrarian, Compounder, Custom Oracle, Market Strategist, Moonshot)
- Gap Audit Agent

## Phase 1 — STATUS
- ZTE Score (v1): 85/100
- ZTE Score (v2): 96/100 [Zero Touch Elite] (v1 base 75 + Section C 21/25)
- Urgent Issues: 10
- Cron Health: unknown

## Phase 2 — LINEAR REVIEW
- Urgent: 11 | High: 19
- Stale: RA-3037 (4d stale), RA-6709 (4d stale)
- Unassigned: RA-6774, RA-6801, RA-2996, RA-2989, RA-2997, RA-2970, RA-2954, RA-3005, RA-2947, RA-2998, RA-1807, RA-6688, RA-2974, RA-6670, RA-5624, RA-6569, RA-2074, RA-5651, RA-5708, RA-5712, RA-5721, RA-6498, RA-6483, RA-3037, RA-6709

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 154.6s)

**Finding #1** [MEDIUM] — _What is Anthropic's current policy on trial credits and API key requirements for new signups as of June 2026?_
  New Anthropic API accounts receive $5 in free trial credits upon signup with no payment details required; the API key is issued immediately via platform.claude.com. Larger grants ($300–$1,000+) require application through programs such as AWS Activate or the Anthropic Startup Program; Claude for Open Source gives qualifying maintainers six months of Max 20x free.
  - [Claude Code Pricing 2026: Free Credits, API Costs & Max Plan Explained | NxCode](https://www.nxcode.io/resources/news/claude-code-pricing-2026-free-api-costs-max-plan) (fetched 2026-06-20)
  - [Anthropic Free Tier 2026 — Free Models, Credits & Limits | Price Per Token](https://pricepertoken.com/endpoints/anthropic/free) (fetched 2026-06-20)
**Finding #2** [MEDIUM] — _Has Anthropic announced any changes to platform-managed credits or free tier access in the last 30 days that could affect third-party SaaS products?_
  Anthropic announced on May 14 a plan to move Agent SDK, claude -p, and third-party app usage to a separate monthly credit pool billed at full API rates (no rollover); on June 15 that change was officially paused with Anthropic stating it is reworking the plan. Agent SDK and headless usage continue drawing from existing subscription limits unchanged until advance notice of any revised rollout. A contradicting report claims metered credits ($20/$100/$200 by plan tier) did activate June 15 — this discrepancy is unresolved.
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-06-20)
  - [Anthropic Brings Back Third-Party Agents on Claude With Monthly SDK Credits | Coding with AI](https://codingwithai.com/news/claude-agent-sdk-credits-june-2026) (fetched 2026-06-20)
**Finding #3** [HIGH] — _What is the current status and pricing of the Australian Business Register (ABR) API, and are there known outages or credential/GUID requirements that changed recently?_
  The ABR ABN Lookup web services API is free of charge with no usage limits. Access requires a GUID obtained at no cost by accepting the web services agreement at abr.business.gov.au. No GUID requirement or pricing changes were found in the primary source; a maintenance window causing delayed ABN updates was documented but the year on that notice was ambiguous (2025 not 2026).
  - [Web services registration | ABN Lookup](https://abr.business.gov.au/Documentation/WebServiceRegistration) (fetched 2026-06-20)
**Finding #4** [MEDIUM] — _What did Anthropic ship in the last 30 days that affects orchestrator or multi-agent SDK behaviour relevant to Pi-CEO?_
  May–June 2026 shipments relevant to Pi-CEO's orchestrator: multiagent sessions and Outcomes public beta (May 6); live MCP server and tool config updates during active sessions plus 100K-token tool output auto-spill to sandbox files (May 19); Opus 4.8 adaptive thinking that fires only when needed (May 28); scheduled cron deployments, Vault env-var credentials for secure CLI/SDK auth, and multi-agent thread webhooks with new session_thread_id field for cross-agent routing (June 9); self-hosted sandboxes on AWS with IAM access control via AnthropicSelfHostedEnvironmentAccess managed policy (June 10). Claude Fable 5 launched June 9 with always-on adaptive thinking, 1M context, 128k max output, and stop_reason: refusal safety classifier.
  - [Claude Developer Platform Updates by Anthropic - June 2026 - Releasebot](https://releasebot.io/updates/anthropic/claude-developer-platform) (fetched 2026-06-20)

**Open questions** (research could not resolve):
  - Whether the June 15 credit change was truly paused or partially activated — digitalapplied.com (fetched) reports a pause while codingwithai.com (fetched) reports activation; no official Anthropic changelog page was directly accessible to adjudicate.
  - Whether the ABR maintenance window noted in the fetched source refers to June 20–21 2025 or 2026 — the page timestamp was ambiguous and no 2026-specific outage notice was found.
  - Exact API key issuance UX for new signups on platform.claude.com — the $5 trial credit figure comes from third-party summaries, not a directly fetched primary Anthropic docs or pricing page.
  - Whether the new session_thread_id webhook field and Vault credentials (June 9) require Pi-CEO's orchestrator to update its ACP/SDK client version to receive or emit these fields.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)


## Phase 3 — SWOT
**SWOT — Pi-CEO (Cycle ending 2026-06-20)**

---

**STRENGTHS:**
- ZTE Score jumped 85→96 in one cycle, confirming the autonomous harness architecture is converging on elite operating state
- SDK architecture is hardened with three enforcement layers (model policy, assert_model_allowed, config gate) — Opus leakage eliminated per RA-1099
- Inner-loop kill switches (RA-1966: MAX_ITERS/MAX_COST/HARD_STOP) prevent runaway spend without human intervention
- Senior-agent topology (CFO/CMO/CTO/CS) gives executive-layer visibility with dual-key gates — rare at this autonomy tier
- Surface Treatment Prohibition (RA-1109) is CI-enforced, not just policy — the PR template + evaluator flags close the gap between "green CI" and "working feature"

---

**WEAKNESSES:**
- BVI = 0: CRITICALs resolved = 0, portfolio improved = 0 — the harness is healthy but not shipping value; velocity is stalled
- 25 unassigned issues including 2 stale >4d (RA-3037, RA-6709) — work is accumulating without an owner, which will compound
- Evaluator logged four consecutive 1.0/10 scores (`evaluator/bug` entries) — the generator produced empty diffs; the judge-gated loop (RA-1970) detected failure but the root cause (empty generation) was never fixed in this cycle
- Scope contract violated: 591 files in a hotfix (max 15) — the autonomy loop has a scope discipline problem that risks destructive over-reach on the next autonomous run
- Watchdog false-positive pattern (lesson `sprint-12-review/scheduled-tasks`, `RA-1043-1049` sandbox CRITICAL) erodes alert credibility; consecutive-failure thresholds are documented but not confirmed implemented

---

**OPPORTUNITIES:**
- 10 Urgent + 19 High open issues = a clear, prioritised queue; BVI of 0 means any single CRITICAL resolution immediately lifts the score
- Judge-gated loop (RA-1970) is architecturally ready — wiring it into full `sessions.py` integration (currently deferred pending telemetry) would give autonomous quality gates on every session
- Semantic RAG memory (TURBOQUANT-ASSESSMENT.md plan) is designed but unbuilt — implementing per-project `memory/` retrieval would directly improve generator quality and cut the empty-diff failure mode
- Stripe-Xero CFO provider is the only senior-agent on a real data path — enabling CMO/CTO/CS real providers upgrades the 6-pager from synthetic to actuals, raising board-meeting signal quality
- `TAO_BOARD_RESEARCH_MODE=hybrid` (RA-1974) is the documented recommendation but default is `fast` — switching to hybrid costs nothing and improves next-cycle brief depth

---

**THREATS:**
- Empty diffs scoring 1.0/10 across completeness, correctness, conciseness, format, and karpathy axes — if the generator silently fails without the evaluator catching it upstream, autonomous sessions burn cost with zero output
- 591-file hotfix scope violation (lesson `evaluator/hotfix`) shows the autonomy loop can blow past its own constraints; without a file-count gate in CI the next violation may land in production
- Alert fatigue from sandbox-environment false CRITICALs (lesson `sprint-12-review/scheduled-tasks`) — if Phill discounts Telegram alerts, a real production failure will be ignored alongside the noise
- `ANTHROPIC_API_KEY=""` inheritance (lesson `RA-1043-1049-review/deployment`) and `op://` literal pass-through (architecture lesson) are documented but rely on every new route/service applying the fix pattern — a new integration that skips either will silently 401 in production
- Stale items RA-3037 and RA-6709 at 4d with no movement suggest the autonomy poller is either not reaching them or failing soft without surfacing why — if the pattern holds, Urgent/High items will age into blockers

## Phase 4 — SPRINT RECOMMENDATIONS
**Phase 4 — SPRINT RECOMMENDATIONS**

---

**PRIORITY 1: RA-6678** — Missing `ABR_API_GUID` in prod is a single env-var gap that makes every ABN lookup return MALFORMED and hard-blocks new-client onboarding — Estimate: **XS (<1h)** — Impact: First BVI point this cycle (one CRITICAL resolved = BVI lifts from 0); unblocks the entire onboarding funnel downstream of RA-6792 and RA-6801

---

**PRIORITY 2: RA-6801** — Report-gen incorrectly gates on a raw Anthropic key despite the platform running trial credits, meaning no new client can reach a PDF export — Estimate: **S (1–2h)** — Impact: Second BVI point; directly unblocks new-client conversion and makes RA-6792 (full onboarding E2E) verifiable for the first time this cycle

---

**PRIORITY 3: RA-5624** — Four consecutive 1.0/10 evaluator scores confirm the generator is producing empty diffs; repairing sandbox env health and the release-gate smoke path closes the root cause, not just the symptom — Estimate: **M (2–4h)** — Impact: Restores autonomous value delivery (BVI = 0 is structurally caused by the generator shipping nothing); every subsequent autonomous session produces real diffs, compounding ZTE from its current 96 ceiling rather than stalling there

---

**Rationale for ordering:** RA-6678 and RA-6801 are the two fastest BVI lifts available — both are "In Review," scoped tightly, and P0 product blockers. RA-5624 is the systemic unlock: without it, BVI resets to 0 next cycle regardless of how many P0 tickets get triaged, because the generator that ships autonomous work is broken.

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 3
- Low: 4
- Tickets created: None

_Generated 2026-06-20T05:07:50.706145+00:00_