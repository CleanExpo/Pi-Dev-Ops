# Board Meeting Minutes — Cycle 0 (2026-06-22)

## Business Velocity Index (RA-696)
**BVI: 1** (+1 from prior cycle)
- CRITICALs resolved: 1
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 0

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
- Stale: RA-6678 (4d stale), RA-6801 (4d stale), RA-6792 (4d stale), RA-6791 (4d stale), RA-2996 (4d stale), RA-2989 (4d stale), RA-2997 (4d stale), RA-2970 (5d stale), RA-2954 (5d stale), RA-3005 (5d stale), RA-5689 (5d stale), RA-2947 (5d stale), RA-2998 (5d stale), RA-1807 (5d stale), RA-6688 (5d stale), RA-2974 (5d stale), RA-6670 (5d stale), RA-5624 (5d stale), RA-6569 (5d stale), RA-2074 (5d stale), RA-5651 (5d stale), RA-5708 (5d stale), RA-5712 (5d stale), RA-5721 (5d stale), RA-6498 (5d stale)
- Unassigned: RA-6774, RA-6812, RA-6815, RA-6469, RA-6801, RA-2996, RA-2989, RA-2997, RA-2970, RA-2954, RA-3005, RA-2947, RA-2998, RA-1807, RA-6688, RA-2974, RA-6670, RA-5624, RA-6569, RA-2074, RA-5651, RA-5708, RA-5712, RA-5721, RA-6498

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 137.4s)

**Finding #1** [MEDIUM] — _What are Anthropic's current trial credit policies and API key requirements for new signups as of June 2026, and do they support platform-managed credits that remove the need for a user-supplied key?_
  Anthropic grants new API signups a small free credit allotment (reported as ~$5 by multiple secondary sources) with phone verification but no credit card required; the official pricing FAQ confirms 'new users receive a small amount of free credits to test the API.' Anthropic does not offer a native platform-managed credit feature that removes the need for an end-user API key — that pattern requires the platform operator to embed their own Anthropic key, or a third-party integration layer such as Relay.app.
  - [Pricing - Claude API Docs](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-06-22)
  - [How to Get a Free Anthropic API Key in 2026 (Plus Free Credits) | Get AI Perks](https://www.getaiperks.com/en/ai/free-anthropic-api-key) (fetched 2026-06-22)
  - [How to buy credits for the Anthropic API to use the Claude models | Relay.app Blog](https://www.relay.app/blog/how-to-buy-credits-for-the-anthropic-claude-api) (fetched 2026-06-22)
**Finding #2** [HIGH] — _Has Anthropic announced any pricing or access changes to Claude API plans effective around 22 June 2026 that would affect the Mythos-as-planner strategy?_
  The headline June 15 billing change (Agent SDK / claude -p moved to a separate monthly credit pool) was officially paused on June 16 and did not take effect; as of June 22 all SDK and subscription usage continues unchanged. Separately, the official pricing page confirms Claude Mythos 5 is listed at $10/MTok input and $50/MTok output but carries a 'limited availability' flag gated behind Project Glasswing approval — access constraints, not price, are the practical risk for a Mythos-as-planner strategy.
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-06-22)
  - [Pricing - Claude API Docs](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-06-22)
  - [Anthropic Just Quietly Raised Claude Pro Bill (June 15 Repricing for Agent SDK) | Level Up Coding](https://levelup.gitconnected.com/anthropic-will-quietly-reprice-your-claude-pro-plan-on-june-15-the-free-20-credit-replacing-1ebd922a7786) (fetched 2026-06-22)
**Finding #3** [HIGH] — _What is the current status of ABR (Australian Business Register) API availability and any known outages or authentication changes affecting ABN lookups in June 2026?_
  As of June 22, 2026 the ABR status page reports all systems operational — ABN System, ABR Web Services, and Identifier Search are all green with no incidents recorded between June 8–22. Authentication remains GUID-based (issued via email on registration approval) with no published changes to that flow.
  - [Australian Business Register Status](https://status.abr.gov.au/) (fetched 2026-06-22)
  - [Web services registration | ABN Lookup](https://abr.business.gov.au/Documentation/WebServiceRegistration) (fetched 2026-06-22)
**Finding #4** [LOW] — _What competing AI-powered insurance or disaster recovery report generation platforms have launched or updated their onboarding flows in the past 60 days that RestoreAssist should be aware of for its organic launch?_
  BriteCore launched eight embedded AI copilots on May 21, 2026, including document generation and claims-summary workflows, targeting enterprise insurers via an MCP infrastructure layer — it is a workflow-automation competitor, not a self-serve consumer-facing disaster recovery report generator. No direct Australian-market or end-user-onboarding competitor specifically targeting property disaster-recovery report generation was identified in this search window.
  - [BriteCore launches AI copilots for insurance workflows](https://fintech.global/2026/05/21/britecore-launches-ai-copilots-for-insurance-workflows/) (fetched 2026-06-22)
  - [Roofing 2026: The Carrier AI Counter-Stack For Storm Season](https://www.marketingcode.com/roofing-ai-claims-storm-season-may-2026/) (fetched 2026-06-22)

**Open questions** (research could not resolve):
  - Does Anthropic operate a formal 'platform operator credit' program (analogous to OpenAI's operator key model) that would allow RestoreAssist to absorb API costs on behalf of end-users without requiring each user to supply their own key — no documentation of this was found in official Anthropic docs as of June 22 2026.
  - What is the exact dollar amount of Anthropic's trial credit for new API signups — official docs confirm credits exist but do not publish a figure; secondary sources cite $5 but this is unconfirmed from a primary source.
  - When will Project Glasswing approval for Claude Mythos 5 become broadly available, and what are the eligibility criteria — the pricing page links to anthropic.com/glasswing but that URL was not publicly fetchable for detailed terms.
  - Are there any Australian-built or Australian-launched AI property-damage report generation platforms (e.g. targeting insurer-policyholder workflows post-flood or bushfire) that have updated onboarding in the April–June 2026 window — searches returned no matching launch announcements.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)


## Phase 3 — SWOT
**SWOT — Pi-CEO · 2026-06-22**

---

**STRENGTHS**
- **ZTE v2 at 96/100** — harness infrastructure (kill-switch trio, model-policy enforcement, HMAC webhooks, SSE reconnect) is operationally mature; the scaffolding is sound.
- **Multi-layer scope control exists** — `LoopCounter`, `KillSwitchAbort`, `tao_judge`, and the scope-contract evaluator are all wired; the system *can* enforce boundaries.
- **Senior agent topology (CFO/CMO/CTO/CS) operational** with dual-key gates; daily 6-pager and debate runner are live patterns, not stubs.
- **Hard-won failure modes are documented** — rate-limit cloud-IP (XFF vs. `request.client.host`), `op://` literal passthrough, empty `ANTHROPIC_API_KEY` propagation, Vercel trailing-newline 401 — all in CLAUDE.md so future agents don't repeat them.
- **Context compactor + context mode (RA-1967/1969) implemented** — deterministic, LLM-free; provides a real cost-reduction lever once wired.

---

**WEAKNESSES**
- **BVI=1, zero MARATHON completions, zero portfolio improvements** — 96/100 autonomy score isn't translating to shipped business outcomes; the harness is running but not landing.
- **Generator producing empty diffs** (evaluator/bug lessons: all axes 1.0/10, three consecutive warnings) — the core value proposition (autonomous code generation) is broken in the loop that matters most; everything else is scaffolding around a non-working engine.
- **Backlog hygiene collapsed** — 25 stale items, 25+ unassigned issues; Linear is a graveyard, not a live prioritisation surface. BVI cannot improve if the input queue is frozen.
- **Watchdog false CRITICAL alerts** (marathon watchdog lesson: ModuleNotFoundError in sandbox, 46/46 tests actually green) — one false alert erodes trust in every subsequent alert; current escalation path is unreliable.
- **Judge-gated loop (RA-1970) and sessions.py integration deferred** — the feedback mechanism that would catch empty-diff failures and retry is not yet wired into production; failures silently score 1.0/10 and move on.

---

**OPPORTUNITIES**
- **25 stale + 25 unassigned issues = immediate BVI lever** — triaging, assigning, and unstalling these requires no new code; one session of backlog hygiene moves the needle more than any infrastructure sprint.
- **Judge-gated loop wiring** — connecting `tao_judge` fully into `sessions.py` closes the empty-diff failure loop; it's implemented (RA-1970), just not activated. This is the highest-leverage code change available.
- **Semantic RAG memory (TurboQuant lesson)** — per-project `memory/` folder + retrieval step before session start is architecturally designed but not built; would directly attack context relevance, the real constraint.
- **Stripe-Xero CFO provider** is stubbed behind `TAO_CFO_PROVIDER=stripe_xero`; wiring real financial data makes the CFO bot actionable rather than synthetic and unlocks genuine board-quality insights.
- **MARATHON completion = 0** — shipping one end-to-end demonstrates the full pipeline and creates a replicable template; the first completion is disproportionately valuable as proof-of-concept.

---

**THREATS**
- **Broken generator is existential** — three back-to-back evaluator sessions scoring 1.0/10 across completeness, correctness, conciseness, format, and Karpathy means the autonomous loop is not producing real work. If uncorrected, every other metric is meaningless.
- **591-file hotfix scope violation** (evaluator/hotfix lesson) — uncontrolled scope in autonomous runs can corrupt production repos, create unresolvable merge conflicts, and invalidate the scope-contract gate that's supposed to be a control layer.
- **Alert fatigue destroying ops trust** — false CRITICALs from sandbox environments (marathon watchdog lesson) plus the consecutive-failure threshold gap (sprint-12 health-check lesson) mean operators are conditioning themselves to ignore alerts at the moment the system most needs them to act.
- **Stale backlog → autonomy poller stalls** — `autonomy.py` only picks up `Todo` + `Urgent/High`; if tickets age past triage and sit unassigned in `In Progress` or never transition, the poller skips them silently and the loop stalls without surfacing why.
- **Dependency on Railway env correctness** — `ANTHROPIC_API_KEY=""` propagation (RA-1043), `op://` literal passthrough, and Vercel trailing-newline are each silent 401s that look like rate limits; any Railway redeploy without explicit env audit reintroduces known failure modes.

## Phase 4 — SPRINT RECOMMENDATIONS
**PRIORITY 1: RA-6678** — ABR_API_GUID missing in prod is almost certainly a single env-var or config record fix, and it blocks *every* ABN lookup, making onboarding impossible for every new client regardless of what else ships — fix this before touching anything downstream. — **Estimate: XS (<1h)** — **Impact:** Unblocks the entire signup funnel; without this, RA-6792/RA-6801 cannot produce a verified first-client completion even if they land cleanly.

---

**PRIORITY 2: RA-6801** — Report-gen requiring an explicit Anthropic key despite platform-managed trial credits is the last gate preventing a new client from completing signup → report → PDF; it's a credential-routing bug sitting in the critical path of BVI. — **Estimate: S (1–2h)** — **Impact:** Closes the onboarding funnel end-to-end; BVI moves from 1 to a verifiable ≥2, which is the only metric that proves the harness is actually landing business outcomes.

---

**PRIORITY 3: "Wire RA-1970 judge-gated loop into sessions.py production path"** (no current open ticket — file as P1 under RA-6800 or standalone) — The generator is producing empty diffs and the evaluator is silently scoring every axis at 1.0/10 because the judge feedback loop is deferred from production; wiring it in turns empty-diff failures into automatic retries instead of silent scores, directly addressing the structural cause of BVI=1 despite 96/100 ZTE. — **Estimate: M (2–4h)** — **Impact:** Converts the engine from "runs but doesn't land" to self-correcting; expected to surface and retry the majority of current silent failures, raising MARATHON completion rate from zero toward measurable.

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 4
- Low: 3
- Tickets created: None

_Generated 2026-06-22T05:08:45.763143+00:00_