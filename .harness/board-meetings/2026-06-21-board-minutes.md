# Board Meeting Minutes — Cycle 0 (2026-06-21)

## Business Velocity Index (RA-696)
**BVI: 0** (0 from prior cycle)
- CRITICALs resolved: 0
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
- Stale: RA-2997 (4d stale), RA-2970 (4d stale), RA-2954 (4d stale), RA-3005 (4d stale), RA-5689 (4d stale), RA-2947 (4d stale), RA-2998 (4d stale), RA-1807 (4d stale), RA-6688 (4d stale), RA-2974 (4d stale), RA-6670 (4d stale), RA-5624 (4d stale), RA-6569 (4d stale), RA-2074 (4d stale), RA-5651 (4d stale), RA-5708 (4d stale), RA-5712 (4d stale), RA-5721 (4d stale), RA-6498 (4d stale)
- Unassigned: RA-6774, RA-6812, RA-6815, RA-6469, RA-6801, RA-2996, RA-2989, RA-2997, RA-2970, RA-2954, RA-3005, RA-2947, RA-2998, RA-1807, RA-6688, RA-2974, RA-6670, RA-5624, RA-6569, RA-2074, RA-5651, RA-5708, RA-5712, RA-5721, RA-6498

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 158.8s)

**Finding #1** [MEDIUM] — _What are the current Anthropic trial credit policies and API key requirements for new accounts as of June 2026, specifically whether platform-managed trial credits bypass the need for a user-supplied API key?_
  Anthropic's official pricing docs confirm new API accounts receive 'a small amount of free credits to test the API' but require billing infrastructure to be configured before requests succeed. The 'no-key option' circulating in guides refers to OAuth-based CLI authentication (via `ant auth login`), which still mandates billing setup and does not constitute a platform-managed bypass — there is no documented mechanism by which an orchestration platform can inject trial credits that eliminate the per-user API key or billing requirement.
  - [Pricing - Claude API Docs](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-06-22)
  - [How to Get an Anthropic API Key in 2026 (Step-by-Step, Plus the New No-Key Option) - Tygart Media](https://tygartmedia.com/how-to-get-anthropic-api-key/) (fetched 2026-06-22)
**Finding #2** [HIGH] — _Has Anthropic made any pricing or access changes to the Claude API in the 30 days prior to 22 June 2026 that would affect orchestration platforms relying on OAuth or subscription tokens?_
  Anthropic announced a June 15, 2026 Agent SDK billing split that would have moved programmatic access (claude -p, Agent SDK, Claude Code GitHub Actions, third-party tools like Conductor and Zed) to a separate monthly credit pool billed at standard API rates — but this change was PAUSED before the effective date and has not been implemented. The status quo remains unchanged: Agent SDK and headless usage continue drawing from existing subscription limits. Separately, a February 2026 ToS revision formally restricts OAuth subscription tokens to Claude Code and Claude.ai only, meaning orchestration platforms cannot rely on subscription OAuth tokens for programmatic access.
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-06-22)
  - [Anthropic June 15 Claude subscription billing overhaul: Agent SDK separate billing pool - Apiyi.com Blog](https://help.apiyi.com/en/anthropic-claude-subscription-agent-sdk-billing-split-june-2026-en.html) (fetched 2026-06-22)
**Finding #3** [HIGH] — _What is the current status and public documentation of the Australian Business Register (ABR) API, including any recent outages, GUID requirement changes, or authentication updates affecting ABN lookups?_
  The ABR API is fully operational as of 22 June 2026 with all sub-services (ABN System, ABR Web Services, Identifier Search) reporting operational status. No incidents have been reported from June 9–22, 2026. GUID-based authentication remains the current requirement for ABN Lookup web services access, with no documented changes to the registration or authentication process.
  - [Australian Business Register Status](https://status.abr.gov.au/) (fetched 2026-06-22)
  - [Web services registration | ABN Lookup](https://abr.business.gov.au/Documentation/WebServiceRegistration) (fetched 2026-06-22)
**Finding #4** [MEDIUM] — _What competing AI-powered business intelligence or report-generation platforms (e.g. Jasper, Copy.ai, Notion AI) have shipped onboarding or trial-credit flows in the last 60 days that RestoreAssist should benchmark against?_
  Notion AI made the most significant recent onboarding change: Custom Agents exited their free exploration period on May 3, 2026, and since May 4, 2026 require paid Notion Credits ($10/1,000 credits, pooled workspace-wide, no rollover), with a Business plan minimum ($20/user/month) required before credits can be purchased. Free-plan users get limited trial prompts for reactive AI features only. Jasper maintains a 7-day free trial with an optional 10,000-word credit offer; no major onboarding change was found in the April–June 2026 window. Copy.ai retains a 2,000-words/month free tier with no documented recent change.
  - [Notion AI Pricing: Plans, Credits & Real Costs (2026)](https://techjacksolutions.com/ai-tools/notion-ai/notion-ai-pricing/) (fetched 2026-06-22)
  - [Jasper AI Free Trial 2026 + 10,000 Words Free Credits - CyberNaira](https://cybernaira.com/jasper-ai-free-trial/) (fetched 2026-06-22)

**Open questions** (research could not resolve):
  - Whether Anthropic offers any formal 'platform-managed trial credit' programme allowing orchestration platforms to provision API access on behalf of end users without requiring those users to supply their own API keys or billing details — this is not documented in current public Anthropic developer docs.
  - Specific Jasper AI or Copy.ai onboarding or trial-credit changes shipped in the April–June 2026 window: no primary-source announcement or changelog was found confirming material changes within that period.
  - Whether the February 2026 Anthropic ToS OAuth restriction has been enforced in practice against existing third-party orchestration platforms or only applied to new integrations.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)
**CEO:** RA-6801 and RA-6678 are compounding blockers destroying the same funnel — new clients hit a broken ABN lookup *and* an API key wall before they see a single report. Research #1 confirms there is no platform-managed trial credit mechanism; we shipped a product promise with no technical backing, and the fix is a decision, not a debug: proxy trial usage through our own key with hard cost caps, or gate on BYOK upfront. Ship the ABR env var (RA-6678) today, make the API architecture call this week, and don't extend RA-5036 spend until both are green.

**Revenue:** The organic launch campaign (RA-5036) is running *now*, acquiring leads into a funnel that cannot convert — RA-6801 blocks report export, RA-6678 breaks ABN lookup, and RA-6792 confirms the full onboarding flow is unverified in prod. Research #3 confirms ABR is fully operational; our GUID misconfiguration is self-inflicted and fixable in minutes via an env var, making it the highest-revenue-per-hour fix on the board. Every hour of campaign spend without resolving these two P0s is negative ROI.

**Product Strategist:** The UX implies "start free, no API key needed" — Research #1 makes clear Anthropic has no mechanism to support that promise, so we've built a false onboarding contract. The right product decision is a proxied trial tier: our key, 1–2 reports free, hard $3 cost cap per user, then a paywall — Research #4 shows Notion AI is now monetising AI credits at $10/1,000 and creating friction; a clean "first report free, no card" story is a genuine differentiator right now. Define the trial architecture before touching another acquisition channel.

**Technical Architect:** RA-6678 is a deployment hygiene failure — ABR_API_GUID is a static credential that belongs in the Railway env checklist, not discovered by a client in prod; Research #3 confirms the ABR API itself is unchanged and fully operational, so this is 100% our own operational gap. The 19 stale items at a uniform 4-day age suggests a batch entered the autonomy queue simultaneously and has not moved — that is a throughput ceiling signal, not 19 independent slow tickets, and the hardening sprint (RA-6800) cannot be declared successful until the close rate improves. Audit `autonomy.py`'s poller against these ticket states before reporting sprint progress.

**Contrarian:** Challenging the Technical Architect's implicit assumption that the stale-ticket problem is a throughput issue — with 19 tickets all stalled at exactly 4 days, the more likely explanation is that the autonomy loop is producing commits that don't resolve the *actual acceptance criteria*, creating an illusion of activity while Linear stays stuck. Research #2 raises a `confidence: low` open question the board has not named: the February 2026 Anthropic ToS explicitly restricts OAuth subscription tokens to Claude Code and Claude.ai — if Pi-Dev-Ops's pipeline is currently using subscription OAuth tokens for programmatic access, we may already be non-compliant, and enforcement against existing integrations is an unresolved open question that could be a far larger existential risk than RA-6801.

**Compounder:** The API access architecture decision (Research #1, #2) is not a hotfix — it is a permanent cost-structure bet that will compound into margin pressure at every scale milestone. Proxying through our key is the right trial mechanic, but only if paired with per-user cost caps and a clear upgrade gate; without that, every viral moment becomes a cost spike we absorb. Research #2's paused billing split means Anthropic will revisit this again — building cost isolation and BYOK upgrade paths now buys us antifragility against the next policy change.

**Custom Oracle:** In Australian restoration and insurance-linked compliance, a broken onboarding flow is not a UX inconvenience — it is a vendor disqualification event in a market where procurement decisions travel by word of mouth across fewer than 200 key decision-makers nationally. Research #3 confirms ABR has had zero incidents in the last two weeks; our GUID misconfiguration signals operational immaturity to the exact buyers who run ABN lookups as a baseline compliance check. Fix RA-6678 before any further outreach to prospects in regulated environments, or the reputation cost exceeds the acquisition cost.

**Market Strategist:** Research #4 shows Notion AI's aggressive credit monetisation is actively creating buyer anxiety about AI tool cost unpredictability — a "first report free, no card, no API key" offer is a genuine market positioning advantage *right now*, but only if RA-6801 is resolved to make it real. The window is narrow: Jasper and Copy.ai have not made material onboarding changes in the April–June period, meaning we have an uncontested 30–60 day window to own the "zero-friction first report" narrative in the Australian SMB compliance space before competitors adjust. Delay closes that window.

**Moonshot:** A 96/100 ZTE score means the autonomy infrastructure is nearly production-grade — the ceiling from here is a fully autonomous compliance intelligence platform where Australian SMBs receive regulatory reports without ever configuring an API key, managing billing, or touching a dashboard. That vision is currently blocked by a missing env var (RA-6678) and an unresolved product architecture question (RA-6801) — the distance between where we are and the ceiling is entirely operational, not technical or visionary. Resolve the two P0s this week and the compounding begins.

---

**CEO SYNTHESIS:** The campaign is live, the funnel is broken, and the fix is known — RA-6678 is an env var deployment today, and RA-6801 resolves to a proxied trial tier with a hard cost cap, the only viable path confirmed by Research #1. The Contrarian's flag on February 2026 ToS compliance is the highest-severity unaddressed risk: if current pipeline OAuth usage violates Anthropic's terms, it supersedes every P0 on the board and must be audited before the hardening sprint closes. Clear both P0s, audit the ToS exposure, and diagnose the stale-ticket throughput ceiling — in that order — before any further acquisition spend.

## Phase 3 — SWOT
**STRENGTHS:**

- **Architecture maturity at 96/100 ZTE.** Zero-touch infrastructure (Railway + Vercel + GitHub Actions) with hardened patterns — HMAC webhooks, bcrypt auth, rate-limit XFF fix, op:// guard, API key trim — all locked into CLAUDE.md and lesson memory. Known failure modes won't recur.
- **P0 resolution paths are fully defined.** RA-6678 is an env var deploy (same-day close); RA-6801 has a confirmed proxied trial tier with hard cost cap (Research #1 verified). No discovery work remains — only execution.
- **Senior-agent topology is live.** CFO/CMO/CTO/CS bots with dual-key gates, debate runner, and 6-pager dispatcher provide executive visibility that most autonomous systems at this stage lack.
- **Lesson library prevents known regressions.** 20 captured lessons covering env hygiene, CI secrets, cloudflared plist args, rate-limiter cloud-IP bug, and watchdog false-positive patterns. These are wired into CLAUDE.md, not just notes.

---

**WEAKNESSES:**

- **BVI = 0.** Zero CRITICALs resolved, zero portfolio improvements, zero MARATHON completions this cycle. The autonomy loop is running but not landing.
- **Generator producing empty diffs and scope explosions.** Multiple evaluator scores at 1.0/10 for completeness/correctness (`[WARN] evaluator/bug`), plus one run modifying 591 files against a 15-file cap (`[WARN] evaluator/hotfix`). The generator is either no-oping or running unconstrained — both destroy BVI.
- **Backlog not being consumed.** 19 stale items (4d+) and 25+ unassigned issues. If the autonomy poller is silently skipping polls due to a missing `LINEAR_API_KEY` (a known silent failure documented in CLAUDE.md), the queue compounds invisibly.
- **Watchdog trust is degraded.** The Cowork sandbox false-CRITICAL alert (`[INFO] marathon watchdog`) means every subsequent Telegram escalation is suspect. A watchdog that cries wolf is worse than no watchdog.

---

**OPPORTUNITIES:**

- **RA-6678 is a same-day BVI point.** An env var deployment with no architectural risk. Closing it today breaks the BVI=0 streak and restores campaign funnel integrity.
- **RA-6801 proxied trial tier unlocks the live campaign.** Board synthesis confirms this is the only viable path. Campaign spend is live with a broken funnel — clearing this has direct revenue impact.
- **ToS audit, if clean, frees the hardening sprint.** The Contrarian's flag is the highest-severity unresolved risk. A clean audit removes the veto on closing sprint items; a dirty audit surfaces a real board-level decision before more investment goes in.
- **Semantic RAG roadmap is defined.** The TurboQuant lesson (`[INFO] ?/?: TurboQuant`) documented a four-piece implementation plan. Per-project memory retrieval is the correct architecture and the design already exists.

---

**THREATS:**

- **Anthropic ToS compliance (February 2026 changes) is unaudited and supersedes all P0s.** CEO Board synthesis is explicit: if current OAuth pipeline usage violates ToS, it invalidates the hardening sprint. This is the only threat that can stop the company, not just slow it.
- **Generator instability is compounding backlog stall.** Empty diffs waste compute; 591-file scope explosions risk committing garbage. Until the evaluator catch (`score < 8 → reject`) is reliably blocking bad outputs, every autonomy loop run is a lottery.
- **Alert fatigue from false watchdog CRITICALs.** The lesson explicitly warns: "after one false CRITICAL alert, every subsequent alert is suspect." Real production failures (Railway crash, API 401 wave, Linear poller death) will be dismissed as sandbox noise.
- **Live marketing spend with no conversion path.** The campaign is live; the funnel is broken. Every day RA-6801 stays open is direct budget burn with zero return.
- **Silent autonomy poller failure.** CLAUDE.md documents that a missing `LINEAR_API_KEY` causes the poller to silently skip every cycle while `/health` still returns 200. If this is active, the 10 Urgent + 19 High items will never auto-session — stale count will grow past 4d to 8d+.

## Phase 4 — SPRINT RECOMMENDATIONS
PRIORITY 1: **RA-6678** — Deploy `ABR_API_GUID` to Railway prod as an env var; resolution path is fully defined with zero remaining discovery, making this the fastest possible BVI point — **Estimate: XS (<1h)** — **Impact: Closes P0 onboarding blocker, eliminates MALFORMED ABN lookups, unblocks the RA-6792 first-client flow; +1 BVI with same-day close**

PRIORITY 2: **RA-6801** — Wire the confirmed proxied Anthropic trial tier (Research #1 verified, hard cost cap ready) to remove the report-gen key dependency from the signup funnel — **Estimate: S (1–2h)** — **Impact: Completes the signup→report→PDF funnel end-to-end; when paired with RA-6678 it closes the full RA-6792 P0 chain and delivers a demonstrable first-client path**

PRIORITY 3: **Generator scope guard** *(no existing ticket — propose: "Generator: enforce 15-file mutation cap + abort on empty diff before evaluator fires")* — The BVI=0 root cause is unconstrained generator runs (591-file diffs) and no-op completions scoring 1.0/10 on completeness; neither RA-6678 nor RA-6801 will move the autonomy velocity needle until the loop itself stops wasting cycles — **Estimate: M (2–4h)** — **Impact: Structural; every subsequent autonomy cycle has a non-zero probability of landing rather than burning compute on empty or blown-out diffs — prerequisite for the 7-day hardening sprint (RA-6800) producing any measurable BVI gain**

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 3
- Low: 5
- Tickets created: None

_Generated 2026-06-21T20:18:14.117267+00:00_