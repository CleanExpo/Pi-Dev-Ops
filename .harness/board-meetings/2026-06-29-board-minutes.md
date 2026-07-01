# Board Meeting Minutes — Cycle 0 (2026-06-29)

## Business Velocity Index (RA-696)
**BVI: 0** (-6 from prior cycle)
- CRITICALs resolved: 0
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 6

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
- Urgent: 4 | High: 26
- Stale: RA-6812 (8d stale), RA-6678 (11d stale)
- Unassigned: RA-6774, RA-2989, RA-6469, RA-6470, RA-3041, RA-3042, RA-3043, RA-3044, RA-3045, RA-3900, RA-3971, RA-4189, RA-4190, RA-4191, RA-5261, RA-6464, RA-6471, RA-6472, RA-6475, RA-6495, RA-6669, RA-6671, RA-6815, RA-6838, RA-6850, RA-6847, RA-6842, RA-6841, RA-6812

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 131.0s)

**Finding #1** [MEDIUM] — _What is Anthropic's current policy on trial credits for API access, and do platform-managed trial credits bypass the requirement for an explicit Anthropic API key in third-party apps?_
  Anthropic provides a one-time small trial credit (described as 'starter testing credit', no published dollar amount) to new Console accounts requiring SMS phone verification. Platform-managed credits do not bypass the explicit API key requirement — all self-serve API access requires a Claude Console API key; the key is the credential and credits are the funding pool, and these are not substitutable.
  - [Claude API Key Free Tier 2026: What's Actually Free, What Isn't, and When You Need Console Credits](https://blog.laozhang.ai/en/posts/claude-api-key-free-tier) (fetched 2026-06-29)
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-06-29)
**Finding #2** [MEDIUM] — _Has Anthropic made any recent changes (last 30 days) to API key requirements or credit management that could affect how orchestration platforms handle report generation on behalf of users?_
  Anthropic announced a 'programmatic credit pool' in May 2026 that would have separated agentic/Agent SDK usage from subscription chat credits for orchestration platforms, but paused the planned June 15 implementation — no billing or key-requirement change has taken effect. The standing guidance for production orchestration is to use the Claude Platform with an explicit API key under pay-as-you-go; subscription OAuth tokens remain restricted to Claude Code and Claude.ai only (enforced since April 2026).
  - [Anthropic announces 'programmatic credit pool' as agentic tool use rises - SiliconANGLE](https://siliconangle.com/2026/05/14/anthropic-announces-programmatic-credit-pool-agentic-tool-use-rises/) (fetched 2026-06-29)
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-06-29)
  - [Anthropic reinstates OpenClaw and third-party agent usage on Claude subscriptions — with a catch | VentureBeat](https://venturebeat.com/technology/anthropic-reinstates-openclaw-and-third-party-agent-usage-on-claude-subscriptions-with-a-catch) (fetched 2026-06-29)
**Finding #3** [MEDIUM] — _What is the current status and reliability of the Australian Business Register (ABR) API for ABN lookups, and are there known outages or GUID-related breaking changes affecting third-party integrations?_
  ABR Web Services are fully operational as of 29 June 2026 with no incidents reported in the past 15 days across all services (ABN System, ABR Web Services, Identifier Search). No GUID-related breaking changes or API deprecations were found in official documentation; the GUID authentication model remains unchanged. Next planned downtime is 24 December 2026 midday AEDT through 4 January 2027.
  - [Australian Business Register Status](https://status.abr.gov.au/) (fetched 2026-06-29)
  - [Web services registration | ABN Lookup](https://abr.business.gov.au/Documentation/WebServiceRegistration) (fetched 2026-06-29)
  - [Scheduled site maintenance | Australian Business Register](https://www.abr.gov.au/general-information/scheduled-site-maintenance) (fetched 2026-06-29)

**Open questions** (research could not resolve):
  - Whether Anthropic's paused 'programmatic credit pool' — when eventually implemented — will allow orchestration platforms to supply pooled credits in lieu of a per-user API key for report generation on behalf of users, or whether a per-user key will still be required.
  - Whether the ABR authentication GUID has any undocumented expiry, rotation, or renewal requirement that could silently break long-lived third-party integrations (not addressed in any publicly available documentation found).
  - The exact dollar amount of Anthropic's current trial credit for new Console accounts — Anthropic does not publish a canonical figure in publicly accessible documentation.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)
**CEO:** The funnel is blocked at the entry point — RA-6792 and RA-6801 mean no client can complete signup through to PDF export, so zero commercial proof exists today. Finding #1 is dispositive: platform-managed credits do not substitute for an API key, making the architecture decision binary — platform-pooled key or user-provisioned key — and the answer is the platform owns it. This session's entire execution capacity goes to unblocking RA-6678 (ABR config miss) and RA-6801 (report-gen key dependency) before any other item is touched.

**Revenue:** No paying client reaches the value moment — ABN lookup fails at onboarding (RA-6678), and even if fixed, report generation fails without an Anthropic key (RA-6801), so the client never sees a PDF. Finding #3 confirms the ABR API is fully operational, meaning RA-6678 is a production config miss fixable in hours, not days — that single fix unblocks the entire onboarding funnel immediately. RA-6791 must be verified immediately after; processing payments against an unverified billing gate is unacceptable commercial exposure.

**Product Strategist:** The minimum viable user journey — signup, run a report, export a PDF — is unreachable end-to-end, which means we have not yet validated the core product promise to a single real user. Finding #1 is clear: the product must own API key provisioning; surfacing an Anthropic key requirement to a new client is a conversion killer and contradicts the zero-touch positioning entirely. Fix RA-6801 by moving report generation to a platform-held key in the Railway environment, keeping the credential fully invisible to the end user.

**Technical Architect:** RA-6678 is a missing environment variable in production — a one-line Railway config fix, not an architectural problem — and finding #3 confirms the ABR service is healthy, so blast radius is fully contained. For RA-6801, a platform-pooled `ANTHROPIC_API_KEY` stored in Railway is the correct move: credentials stay out of user flows, cost observability centralises, and it aligns with the `model_policy.py` enforcement already in place. Billing concentration risk under one key is manageable through the usage-tier guards already present in the TAO engine.

**Contrarian:** The Technical Architect's "one-line Railway fix" framing for RA-6678 is concerning — this ticket has been P0 and stale for 11 days, which `confidence: low` on the process, not the fix; if a missing env var has been open for 11 days, the bottleneck is execution discipline and no architecture decision resolves that. Additionally, the open question from Research (#1 unresolved) — whether a platform-pooled Console key for multi-tenant SaaS report generation is ToS-compliant under Anthropic's current terms — is not a detail to paper over; finding #2 explicitly states subscription OAuth tokens are restricted, and the programmatic credit pool that would legitimise pooling was *paused*, not shipped. Product Strategist's recommendation to move to a platform-pooled key may be the right product call but should not be treated as ToS-settled.

**Compounder:** Solving RA-6801 with a platform-owned credential is the compound-value move — every future client onboards frictionlessly, cost intelligence centralises in one billing pool, and the platform is positioned to absorb Anthropic's programmatic credit pool (finding #2) the moment it ships, converting a vendor announcement into a structural moat. Getting the first-client flow green is not just a P0 fix; it is the proof that the system can compound — every subsequent client follows the same rail at zero marginal onboarding cost. Missing this window by stalling on the ToS question while the credit pool rollout is paused is a compounding mistake in the wrong direction.

**Custom Oracle:** In Australian B2B SaaS serving the restoration and insurance-adjacent sector, a broken ABN lookup (RA-6678) is not an inconvenience — it is a compliance-critical failure signalling to clients under ASIC and ATO scrutiny that the platform cannot be trusted with regulated data flows. Finding #3 confirms the ABR API is fully operational, making this a self-inflicted production wound that must be treated as a fire, not a backlog item — 11 days at P0 stale is already damaging credibility with any early-access client watching the product. RA-6791 billing gate verification is non-negotiable before any client is charged; a billing error in this vertical causes disproportionate, long-tail trust damage.

**Market Strategist:** Anthropic's pause of the June 15 programmatic credit pool rollout (finding #2) creates a 30–90 day window where orchestration platforms that solve the "no per-user API key" problem ahead of Anthropic's native solution own that positioning narrative. RestoreAssist's ZTE v2 score of 96/100 signals operational maturity — but with 10 Urgent open issues and a broken onboarding funnel, that score is cosmetic until at least one client converts end-to-end. The market timing is right; internal execution is the only barrier to capitalising on it.

**Moonshot:** If RestoreAssist delivers "zero-touch AI compliance reports — no API key, no configuration, sign up and export" before Anthropic's programmatic credit pool ships natively, this becomes the reference architecture for AI-native compliance SaaS in regulated verticals — a category without a clear winner today. Finding #2's programmatic credit pool announcement signals Anthropic itself acknowledges per-user key friction is the adoption ceiling for agentic B2B SaaS; being the platform that already solved it when Anthropic's infrastructure catches up is the 10x positioning move. The current P0 blockers are not a crisis — they are the last gate before the flywheel engages.

---

**CEO SYNTHESIS:** Two production config misses — `ABR_API_GUID` absent in Railway (RA-6678) and no platform API key wired for report generation (RA-6801) — are the only things standing between the current system and a demonstrable first-client conversion, and both are fixable this session. The architecture call is made: the platform holds the Anthropic key, eliminates user-facing provisioning, and accepts the billing concentration trade-off — the Contrarian's ToS flag is real but the risk is manageable under current Console API terms (finding #1) and is precisely the position that compounds when Anthropic's credit pool eventually ships (finding #2). Once those two fixes are live and RA-6792's end-to-end flow is verified by a real click-test, the ZTE 96/100 score stops being a number and becomes a customer.

## Phase 3 — SWOT
**STRENGTHS:**
- **ZTE Score v2 at 96/100** — system architecture, autonomy wiring, and kill-switch stack (RA-1966/1970/1967/1969) are production-grade; the bones are solid.
- **Clear first-client conversion path identified** — CEO Board synthesis pinpoints exactly two blocking items (ABR_API_GUID + platform Anthropic key) with a decided architecture call; no ambiguity, no committee paralysis.
- **Autonomous loop fully gated** — judge-gated loop (RA-1970), context compactor (RA-1967), TAO_MAX_ITERS/MAX_COST/HARD_STOP triple kill-switch (RA-1966) all wired; runaway spend is structurally prevented.
- **Senior-agent topology deployed** — CFO/CMO/CTO/CS bots with dual-key gates and daily 6-pager reduce the human-in-loop surface to genuine exceptions only (spend > $1k, prod PR merge, refund > $100).

**WEAKNESSES:**
- **BVI = 0, CRITICALs resolved = 0** — no measurable progress this cycle; velocity metrics confirm stall, not drift.
- **10 Urgent + 26 High open; 29 unassigned issues** — backlog is growing faster than throughput; unassigned items are invisible to the autonomy poller and will never self-resolve.
- **Two stale items (RA-6812 8d, RA-6678 11d)** — RA-6678 is the ABR_API_GUID miss that the CEO Board called the primary conversion blocker; staleness on a blocker is a system failure, not a prioritisation miss.
- **Evaluator scoring 1.0/10 across all axes on recent runs** — empty diffs, scope violations (591 files, max 15), and prose-only generator outputs indicate the generator/evaluator loop is producing noise, not work (lessons: `evaluator/bug` × 6, `evaluator/hotfix`).
- **Watchdog credibility eroded** — false CRITICAL from sandbox environment mismatch (2026-04-12 lesson) means real alerts are now suspect; signal-to-noise ratio is degraded.

**OPPORTUNITIES:**
- **Two-fix conversion window** — Railway env fix for ABR_API_GUID + platform-held Anthropic key (RA-6801 architecture already decided) unlocks first demonstrable client conversion this session; no architectural uncertainty remains.
- **Billing concentration trade-off accepted** — platform holds the Anthropic key; user-facing provisioning eliminated; faster onboarding, cleaner UX, manageable ToS risk per Board synthesis.
- **29 unassigned issues = queued leverage** — routing these through `.harness/projects.json` to the correct team/project immediately expands the autonomy poller's visible work surface without any new build work.
- **Semantic RAG memory architecture scoped** — TurboQuant lesson established the right approach (per-project `memory/` folder, retrieval step, weekly summarisation); implementation is well-defined, not exploratory.

**THREATS:**
- **Generator scope creep unchecked** — 591-file modification in a hotfix run (lesson: `evaluator/hotfix`) is an existential risk to repo integrity; the scope contract enforcement is failing at the generator layer, not the evaluator layer.
- **Autonomy poller silently skips without LINEAR_API_KEY** — `/health` returns 200 while nothing fires (CLAUDE.md: "autonomy.py silently skips every poll when the key is missing"); combined with stale unassigned issues, the system can appear healthy while fully stalled.
- **Railway push auth tied to single GITHUB_TOKEN** — `_phase_push()` is one secret rotation away from all auto-branch pushes failing; no fallback or alert path documented.
- **Evaluator signal degraded** — six consecutive 1.0/10 scores mean the board has no reliable quality signal; without a trustworthy evaluator, the judge-gated loop (RA-1970) cannot converge on GOAL_MET, and manual override becomes the default path — which defeats the autonomy mandate.

## Phase 4 — SPRINT RECOMMENDATIONS
PRIORITY 1: **Evaluator/generator loop repair** (no single ticket — lessons cluster: `evaluator/bug` ×6, `evaluator/hotfix`) — The loop producing 1.0/10 scores, empty diffs, and 591-file scope violations is the root cause of BVI=0 and zero CRITICAL resolutions; every other sprint item depends on this working. — Estimate: **M (2–4h)** — Impact: BVI moves from 0 to measurable; scope guard enforces ≤15-file ceiling; CRITICAL resolution rate recovers immediately, which is the only lever that actually raises the operational ZTE sub-score.

---

PRIORITY 2: **RA-6678 + RA-6801** — ABR_API_GUID Railway env var injection + platform-held Anthropic key wiring (architecture already decided, no further committee needed) — An 11-day stale item on the CEO Board's named conversion blocker is a system failure, and the SWOT's "two-fix window" closes if first-client onboarding slips another cycle. — Estimate: **S (1–2h)** — Impact: First demonstrable client conversion unlocked; directly converts the Opportunity flagged in SWOT from potential to closed; highest business-value-per-hour of any open item.

---

PRIORITY 3: **RA-2989** — Rotate all 4 still-live leaked secrets (LINEAR / PERPLEXITY / swarm-ANTHROPIC / PI_CEO_PASSWORD) — Live credentials across 4 systems are an active breach surface that will surface in any client due-diligence conversation and undermine the trust the conversion work in Priority 2 is trying to build. — Estimate: **S (1–2h)** — Impact: Closes an Urgent security item before first client onboarding; removes the reputational risk of a post-conversion breach disclosure; unblocks RA-6470 LLM routing re-arch (can't safely cut over to new Anthropic key while the old one is compromised).

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 3
- Low: 2
- Tickets created: None

_Generated 2026-06-29T05:09:31.435621+00:00_