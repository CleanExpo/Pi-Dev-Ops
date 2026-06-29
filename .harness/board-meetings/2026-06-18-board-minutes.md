# Board Meeting Minutes — Cycle 0 (2026-06-18)

## Business Velocity Index (RA-696)
**BVI: 8** (-3 from prior cycle)
- CRITICALs resolved: 8
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 11

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
- Stale: None
- Unassigned: RA-6774, RA-6801, RA-2996, RA-2989, RA-2997, RA-2970, RA-2954, RA-3005, RA-2947, RA-2998, RA-1807, RA-6688, RA-2974, RA-6670, RA-5624, RA-6569, RA-2074, RA-5651, RA-5708, RA-5712, RA-5721, RA-6498, RA-6483, RA-3037, RA-6709

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 116.7s)

**Finding #1** [HIGH] — _What changes has Anthropic made to trial credit policies or API key requirements in the last 30 days that could affect platform-managed credit flows?_
  Anthropic announced on May 14, 2026 that Agent SDK and headless claude -p usage would move to separate monthly credit pools (Pro $20, Max 5x $100, Max 20x $200) effective June 15; however, on June 15 Anthropic confirmed the change was shelved and all usage continues drawing from existing subscription limits unchanged. Trial API credit policy is unaltered: new accounts receive a small free credit grant; no new key-gating requirement was introduced.
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-06-18)
  - [Pricing - Claude API Docs](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-06-18)
  - [Anthropic Ends Subscription Subsidy for Agents June 15: Credit Pool Replaces Flat-Rate Access](https://www.techtimes.com/articles/317625/20260602/anthropic-ends-subscription-subsidy-agents-june-15-credit-pool-replaces-flat-rate-access.htm) (fetched 2026-06-18)
**Finding #2** [HIGH] — _What is the current status of Anthropic's pricing changes scheduled around 22 June 2026 that could impact Mythos-as-planner strategy?_
  Claude Fable 5 subscription access (free on Pro and Team tiers) ends June 22, 2026; post-22 June subscription terms have not been published. Separately, Claude Mythos 5 — the model relevant to a Mythos-as-planner strategy — is priced at $10/MTok input and $50/MTok output via the API (same as Fable 5) and is currently under limited availability via the glasswing program; its API token pricing is stable with no announced changes around June 22.
  - [Pricing - Claude API Docs](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-06-18)
  - [Claude Fable 5 Pricing, Access, and Usage Limits: What You Need to Know](https://www.mindstudio.ai/blog/claude-fable-5-pricing-access-usage-limits) (fetched 2026-06-18)
**Finding #3** [HIGH] — _Are there any known outages or changes to the Australian Business Register (ABR) API that could affect ABN lookup reliability in production?_
  As of June 18, 2026, the ABR reports all systems fully operational — ABN System, ABR Web Services, and Identifier Search are green with no incidents recorded in the past two weeks (June 4–18). No API-breaking changes or deprecation notices are active; the only scheduled downtime is the Christmas/New Year closure (24 Dec 2026 – 4 Jan 2027).
  - [Australian Business Register Status](https://status.abr.gov.au/) (fetched 2026-06-18)
  - [Scheduled site maintenance | Australian Business Register](https://www.abr.gov.au/general-information/scheduled-site-maintenance) (fetched 2026-06-18)
**Finding #4** [LOW] — _What competing RestoreAssist or disaster recovery SaaS platforms have launched or updated their offerings in the last 60 days?_
  HYCU R-Cloud added Hyper-V and Proxmox VE 9.0 support with a real-time replication engine in April 2026; no direct RestoreAssist-category (insurance-claims-focused disaster recovery for Australian SMEs) platform launch was found across PR Newswire, BusinessWire, or major review sites in the April–June 2026 window.
  - [New Features and Innovations in the HYCU R-Cloud Platform | HYCU](https://www.hycu.com/new) (fetched 2026-06-18)
  - [10 Best Cloud Disaster Recovery Solutions In 2026](https://controlmonkey.io/resource/cloud-disaster-recovery-solutions/) (fetched 2026-06-18)

**Open questions** (research could not resolve):
  - What specific post-June 22 subscription-tier terms will Anthropic publish for Fable 5 and Mythos 5 access — will Mythos 5 remain limited-availability indefinitely or transition to general availability with changed pricing?
  - Are there Australia-specific or insurance-claims-workflow SaaS platforms (direct RestoreAssist competitors) that launched or updated in April–June 2026 that did not surface in general DR SaaS review-site searches?

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)
**CEO:** The P0 cluster (RA-6801, RA-6792, RA-6791, RA-6678) is a single funnel failure — no client can complete signup, report, or pay — and it must be green before any other work ships. Finding #1 confirms the Anthropic credit-pool change was shelved, meaning the key-gating bug in RA-6801 is self-inflicted configuration debt, not a platform constraint, and that makes it fixable today. With a 96/100 ZTE score the system is capable; the execution gap is in shipping closed loops, not capacity.

**Revenue:** Every day RA-6801 and RA-6678 sit open is a day the first paying client cannot close — that is not a sprint backlog item, that is a revenue gate. Finding #3 confirms the ABR API is fully operational, meaning RA-6678 is a missing env var we own entirely; there is no external dependency blocking resolution. Resolve both this session and protect the RA-5036 organic launch campaign from launching into a broken funnel.

**Product Strategist:** Users hitting a signup-to-report wall will not file a bug report — they will leave and attribute the failure to product quality, not configuration. Finding #1 removes the platform excuse for RA-6801; the report-gen Anthropic key requirement is a product decision that must be replaced with platform-managed credential injection before any growth motion starts. RA-6792's full onboarding flow verification should be the acceptance gate before RA-5036 campaign traffic is turned on.

**Technical Architect:** RA-6678 (missing ABR_API_GUID) and RA-6801 (hardcoded Anthropic key requirement) are both environment-injection failures, not architectural ones — the fix is a Railway env var set plus a credential-routing patch, sub-one-hour work. What concerns me structurally is that two P0 production blockers were both caused by secrets not reaching the runtime, suggesting the env hygiene pipeline (the `op://` resolver pattern documented in CLAUDE.md) is not being enforced at deploy time. That systemic gap needs a pre-deploy env-validation smoke step added to CI before the next release cycle.

**Contrarian:** The Technical Architect's "sub-one-hour fix" framing for RA-6801 is confidence: low — Finding #1 confirms the credit-pool change was shelved, but the open question of *how* platform-managed trial credits are threaded through the report-gen layer is unresolved; if the code path explicitly asserts an API key before calling Anthropic rather than falling through to OAuth, the fix is not a config change but a code change requiring a deploy cycle with smoke-test gate. I also challenge the CEO's implicit assumption that the ZTE 96/100 score signals readiness — a system that cannot onboard its first client is a 0/100 on the only metric that pays rent.

**Compounder:** Fixing the env-injection failure mode once, correctly, with a pre-deploy validation gate compounds: every future deploy is self-verifying and the P0 class of bug disappears from the backlog permanently. Finding #2's June 22 Fable 5 access cutoff is the compounding risk nobody has named — if Mythos-as-planner (RA-6469) is not operational before that date, the planning tier reverts to a model that historically produced 5%-confidence plans, which degrades every autonomous session quality until Mythos GA. The Mythos operational deadline is four days away and sits in Backlog.

**Custom Oracle:** In Australian B2B SaaS serving insurance-linked restoration clients, a broken onboarding flow that exposes an internal API key configuration error to end users — even as an error message — is a trust-termination event; clients in regulated environments pattern-match "API key error" to "insecure platform." Finding #3 confirms ABR is green, which means any client who sees an ABN lookup failure today correctly attributes it to RestoreAssist, not ABR — that attribution is brand damage in a compliance-sensitive vertical. Resolve RA-6678 with a sanitised, client-facing error message as part of the fix, not just the backend env var.

**Market Strategist:** Finding #4 shows no direct RestoreAssist-category competitor launched in the last 60 days — this is a narrow window of clear differentiation that the RA-5036 organic launch campaign is positioned to exploit, but only if the funnel works. Finding #2's June 22 pricing signal is externally meaningful: if Mythos 5 moves toward GA post-cutoff with stable $10/$50 pricing, early adoption of Mythos-as-planner (RA-6469) before the market catches on is a cost and capability moat. The market window for both moves — clean funnel and Mythos-as-planner — closes inside this sprint.

**Moonshot:** If the P0 funnel is closed this week and Mythos-as-planner is live before June 22, RestoreAssist becomes the first Australian insurance-claims SaaS running an Opus-class planner at scale — that is not a feature, that is a defensible capability ceiling that competitors cannot replicate without the same platform investment. Finding #1's confirmation that subscription limits are unchanged means the unit economics of running Mythos-as-planner for trial users are currently subsidised by Anthropic's Pro/Max pools — that window funds the proof-of-concept at zero marginal cost. The ceiling here is a fully autonomous claim-to-report pipeline that a restorer can trigger from a phone; everything in this sprint is foundation for that.

---

**CEO SYNTHESIS:** The entire board collapses to one instruction: close the P0 funnel (RA-6801, RA-6678, RA-6792, RA-6791) this session — these are configuration and code fixes, not architectural work, and no other priority is real until a client can sign up, look up their ABN, and export a report. Simultaneously, RA-6469 (Mythos-as-planner) must move from Backlog to active before June 22 or the autonomous session quality floor drops at the exact moment the growth campaign launches. Everything else — the ZTE score, the debate about compound moats, the competitive window — is noise until those two threads are green.

## Phase 3 — SWOT
**STRENGTHS:**
- ZTE Score jumped 85→96 in one cycle, and 8 CRITICALs resolved — the execution engine is clearing blockers at pace
- Hardwired architectural lessons (RA-1043–1184 series) are institutionalised in CLAUDE.md, reducing repeat failures on auth, rate-limiting, and SDK misuse
- Senior-agent topology (CFO/CMO/CTO/CS) with dual-key gates and debate-runner gives genuine executive oversight without human latency
- Model routing policy (RA-1099) — Opus reserved, Sonnet for generation — prevents budget blowouts and keeps quality consistent
- Surface Treatment Prohibition (RA-1109) is enforced at PR-template level, not just convention — prevents the "green CI, broken feature" failure mode documented in PR #48/#56

**WEAKNESSES:**
- BVI dropped to 8 (-3): 8 CRITICALs closed but portfolio improved = 0 and MARATHON completions = 0 — execution is resolving debt, not shipping growth
- P0 funnel (RA-6801, RA-6678, RA-6792, RA-6791) still open; a client cannot sign up, look up ABN, or export a report — the core revenue loop is broken
- 25 unassigned issues including RA-6801 (P0 funnel) — ownership gaps mean CRITICALs can sit without a session picking them up
- Watchdog false-positive pattern (`[WARN] sprint-12-review/scheduled-tasks`, marathon sandbox lesson): alert credibility is degraded; real failures risk being ignored as noise
- Evaluator lessons show empty-diff sessions scoring 1.0/10 across all axes — the TAO loop is capable of generating zero output and calling it a session

**OPPORTUNITIES:**
- RA-6469 (Mythos-as-planner): if activated before June 22, autonomous session quality floor rises at the exact moment the growth campaign goes live — a compounding leverage point
- 19 open High issues with no stale items and autonomy queue enabled — the backlog is actionable and the machinery exists to drain it without human involvement
- Semantic RAG / per-project memory (from TurboQuant assessment lesson): the architecture is scoped correctly (relevance not raw memory), implementation plan exists — this directly lifts session quality for every future run
- Context compactor (RA-1967) + context mode (RA-1969) already implemented: ≥30% and ≥40% additional reduction validated — cost per session is structurally lower than competitors

**THREATS:**
- Scope contract violated at 591 files in one hotfix session (`[WARN] evaluator/hotfix`) — a single runaway session can corrupt the entire repo; the 15-file cap is not enforced at the kill-switch layer
- Growth campaign launches June 22: if P0 funnel (sign-up/ABN/export) is not closed before then, the campaign drives traffic into a broken product — the CEO board explicitly flagged this as the only real priority
- Stale `last_fired_at` cron-trigger reset on Railway redeploy (`CLAUDE.md` scheduled-tasks section) means autonomy can silently stop firing after any deploy without an alert
- Dependency on `TAO_USE_AGENT_SDK=1` with no fallback exercised except quarterly (`scripts/fallback_dryrun.py`) — an Anthropic SDK breaking change mid-campaign would halt all autonomous sessions with no immediate recovery path

## Phase 4 — SPRINT RECOMMENDATIONS


## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 3
- Low: 2
- Tickets created: None

_Generated 2026-06-18T05:09:03.510182+00:00_