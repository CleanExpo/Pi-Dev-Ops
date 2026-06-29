# Board Meeting Minutes — Cycle 0 (2026-06-17)

## Business Velocity Index (RA-696)
**BVI: 11** (+6 from prior cycle)
- CRITICALs resolved: 11
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 5

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
- Urgent: 9 | High: 21
- Stale: None
- Unassigned: RA-6797, RA-6774, RA-2997, RA-6684, RA-2970, RA-2954, RA-3005, RA-2947, RA-6678, RA-2998, RA-6689, RA-1807, RA-4864, RA-6688, RA-2974, RA-6670, RA-5624, RA-6569, RA-2074, RA-5651, RA-5708, RA-5712, RA-5721

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 117.9s)

**Finding #1** [HIGH] — _What is the current status and reliability of the Australian Business Register (ABR) API, and have there been any recent outages or GUID format changes affecting ABN lookups?_
  As of 18 June 2026, all ABR services (ABN System, ABR Web Services, Identifier Search) are fully operational with zero incidents reported across the preceding 15 days. The API change control log (v9.9.7) shows no GUID format or authentication changes since 2012; the GUID-based auth mechanism is unchanged.
  - [Australian Business Register Status](https://status.abr.gov.au/) (fetched 2026-06-18)
  - [Change control | ABN Lookup Web Services](https://abr.business.gov.au/Documentation/ChangeControl) (fetched 2026-06-18)
  - [Web services user guide | ABN Lookup](https://abr.business.gov.au/Documentation/Default) (fetched 2026-06-18)
**Finding #2** [HIGH] — _What are the current pricing changes taking effect around 22 June 2026 for Anthropic's Claude models that would affect the Mythos-as-planner strategy?_
  The Agent SDK billing change announced for 15–16 June 2026 — which would have moved claude -p and Agent SDK usage out of subscription pools into separate credit pools at API rates — was indefinitely suspended by Anthropic on 15 June 2026. Current API pricing for Claude Mythos 5 (limited availability via Glasswing) remains $10/MTok input and $50/MTok output, identical to Claude Fable 5; no new pricing changes are in effect as of 18 June 2026.
  - [Anthropic abruptly suspends Claude Agent SDK pricing change](https://www.digitaltoday.co.kr/en/view/66431/anthropic-suspends-claude-agent-sdk-pricing-change-no-changes-for-now) (fetched 2026-06-18)
  - [Pricing - Claude API Docs](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-06-18)
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-06-18)
**Finding #3** [HIGH] — _What Australian regulatory or compliance requirements apply to SaaS platforms handling ABN verification data for business onboarding flows?_
  SaaS platforms verifying ABNs in onboarding flows face a two-track obligation: a sole trader's ABN is personal information under Privacy Act 1988 and triggers full Australian Privacy Principles (APP 1, 5, 8, 11) including collection notification and cross-border transfer constraints; a company ABN alone is not personal information. From 10 December 2026, the mandatory ADM disclosure requirement also applies to automated onboarding and credit-assessment systems, and the Bunnings v Privacy Commissioner [2026] ARTA 130 ruling establishes that even transient processing of personal data constitutes 'collection', tightening obligations at the API-call layer.
  - [Australian privacy compliance: four key developments in 2026 - Corrs Chambers Westgarth](https://www.corrs.com.au/insights/australian-privacy-compliance-four-key-developments-in-2026) (fetched 2026-06-18)
  - [Australia Privacy Act: Complete APPs Compliance Guide for SaaS Companies](https://complydog.com/blog/australia-privacy-act-apps-compliance-guide-saas-companies) (fetched 2026-06-18)
  - [Australian business data APIs are a mess — here's how to fix it in one call](https://dev.to/sachhm/i-built-a-rest-api-for-australian-business-data-heres-how-b94) (fetched 2026-06-18)

**Open questions** (research could not resolve):
  - Does the ABR intend to migrate from SOAP/XML to a REST/JSON-first web services architecture, and if so on what timeline?
  - Has OAIC issued specific guidance on API-layer ABN verification (e.g. minimum data fields, retention limits) for SaaS onboarding — distinct from general APP guidance?
  - What is the anticipated timeline for Claude Mythos 5 to move from limited Glasswing availability to general API availability, and will pricing change at that point?

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)
**CEO:** The ZTE v2 score of 96/100 is a vanity metric while RA-6678 sits Pi-Dev: Blocked — that single missing env var breaks every ABN lookup and makes the P0 onboarding flow (RA-6792) impossible to close commercially. Finding #1 confirms ABR services are fully operational and the API hasn't changed since 2012, so this is entirely self-inflicted; rotate ABR_API_GUID into prod today and unlock the entire onboarding funnel before anything else moves.

**Revenue:** RA-6678 is the most expensive bug on the board — not because it's complex but because it's blocking the commercial handshake on every new customer acquisition attempt. Finding #1 makes it undeniable: the ABR side is clean, we own this failure, and every hour it stays blocked is closed revenue deferred. Fixing billing verification (RA-6791) in parallel completes the loop; without both resolved, we cannot book a paying client regardless of everything else shipping.

**Product Strategist:** The P0 cluster (RA-6792, 6791, 6790) is the minimum viable first-customer journey and needs to be traversed end-to-end before the organic launch campaign (RA-5036) spends a single dollar of attention. Finding #3 is a hidden product requirement that isn't in any of these tickets — sole trader ABN processing triggers full Australian Privacy Principles including a collection notification obligation, so the onboarding flow needs a compliant disclosure surface before we scale intake.

**Technical Architect:** ABR_API_GUID is a config gap, not a code defect — Finding #1 confirms no API changes since 2012, so the fix is one env var pushed to Railway, not a PR. The more durable structural risk is RA-4951 (CI Prisma failures without DATABASE_URL): that instability degrades every subsequent PR's test signal, and a false-green CI at commercial launch is a compounding liability that erodes trust in the entire gate-to-green loop.

**Contrarian:** The Technical Architect's "one env var" framing for RA-6678 undersells the risk — this ticket has been Pi-Dev: Blocked long enough to surface as Urgent, which means something has actively prevented the straightforward fix; `confidence: low` that this is a pure deployment oversight rather than a credential, IAM, or environment-isolation issue that hasn't been diagnosed yet. I also flag open question #3 from the Research Brief: Mythos GA timeline is entirely unknown, so the Compounder's case for RA-6469 as a durable planning moat rests on pricing stability that Finding #2 confirms only as a suspension announcement — not a permanent policy — making "operational before 22 June" an obsolete framing built on an assumption that could reverse without notice.

**Compounder:** Building APP-compliant data handling for sole trader ABN collection correctly now — per Finding #3 — satisfies the December 2026 ADM disclosure mandate before it becomes a painful retrofit, and it becomes a trust signal in a market where sole traders are the dominant client profile. A clean compliance posture from day one compounds as a moat; a patched one three years into scaled operation is a liability that competitors will use against us in enterprise sales.

**Custom Oracle:** Finding #3 is non-negotiable for this market — restoration contractors are predominantly sole traders, meaning every ABN lookup is processing personal information under the Privacy Act, and the Bunnings v Privacy Commissioner [2026] ARTA 130 ruling establishes that even transient API-layer processing constitutes 'collection'. A privacy incident at the onboarding layer in an insurance-linked compliance context is a termination event for client relationships; the APP disclosure requirement is not optional polish, it is a prerequisite to commercial operation at any scale.

**Market Strategist:** Finding #2 removes the 22 June deadline pressure on RA-6469, which is strategically valuable — it means the Mythos-as-planner decision can be made on capability merit rather than pricing panic, giving us a calmer evaluation window. The organic launch via Synthex (RA-5036) is well-timed: ABR infrastructure is stable per Finding #1, the compliance framework is navigable, and the competitive window for a zero-touch restoration SaaS is open now before compliance-software incumbents register the segment.

**Moonshot:** If the P0 onboarding flow works at ZTE 96 and ABR lookup is unblocked, this system has the architecture to onboard the entire Australian restoration industry with zero human touchpoints — that is a census-scale distribution moat, not a product feature. The Mythos-as-planner strategy, with pricing pressure suspended per Finding #2, becomes an opportunity to build planning intelligence that separates RestoreAssist from any tool-grade competitor by a compounding margin that widens each quarter.

---

**CEO SYNTHESIS:** The debate converges on one unlock with a verification step attached: confirm within 30 minutes whether RA-6678 is a pure config gap or a deeper credential issue — the Contrarian's challenge is warranted given how long it has sat blocked — then deploy ABR_API_GUID to prod and run the P0 stack (6791, 6792, 6790) end-to-end before the organic campaign (RA-5036) drives a single visitor. In parallel, the Custom Oracle and Compounder are both right that APP-compliant onboarding disclosure must be designed in before scale, not retrofitted — it is a legal prerequisite and a trust moat in this market, and it belongs in the RA-6792 acceptance criteria now.

## Phase 3 — SWOT
**SWOT — Pi-CEO | 2026-06-18 | ZTE 96 / BVI +6**

---

**STRENGTHS**
- **ZTE 96/100 with 11 CRITICALs resolved this cycle** — autonomous triage and resolution loop is demonstrably functional at near-ceiling velocity.
- **Kill-switch + judge-gated loop architecture is mature** (RA-1966, RA-1970, RA-1973) — three independent abort axes, Telegram watchdog, orphan recovery, per-team state all wired; the control plane can be trusted.
- **Senior-agent topology (Wave 4)** with CFO/CMO/CTO/CS bots fully stubbed and wired into the daily 6-pager — executive intelligence layer exists and fires without human prompting.
- **Linear → Railway → Vercel pipeline is end-to-end** with HMAC-verified webhooks, session isolation, and crash-safe atomic state persistence — the plumbing doesn't leak.
- **Hardwired credential hygiene lessons applied** (op:// validator, `os.environ.pop`, `.trim()` on Vercel keys) — the class of silent-401 failures from [WARN] sprint-12 / RA-1049 are documented and codified.

---

**WEAKNESSES**
- **BVI velocity is rising but portfolio improvement = 0, MARATHON completions = 0** — CRITICALs are being resolved but no net-new capability shipped to end users; resolving debt ≠ advancing the product.
- **Generator silently produces empty diffs** — evaluator repeatedly scores 1.0/10 across all axes ([WARN] evaluator/bug ×4); the autonomous loop can complete a full cycle and deliver nothing with no hard-stop signal.
- **23 unassigned issues sit idle** — the autonomy poller picks Urgent/High from Linear but these tickets never get assigned; either the poller criteria don't match or the queue is saturated and items fall through.
- **Environment fragility under scheduled-task sandboxes** — [INFO] watchdog lesson: `anthropic>=0.90` missing from Cowork sandbox triggered false CRITICAL at 00:38 UTC; after one false alert the entire alert channel loses credibility.
- **Scope contract violations are recurring** — [WARN] evaluator/hotfix logged 591 files modified against a max-15 contract; autonomous agents are not reliably respecting scope constraints mid-run.

---

**OPPORTUNITIES**
- **ABR_API_GUID → P0 stack (RA-6791/6792/6790) → organic campaign (RA-5036)** is a single unblocked chain: CEO Board synthesis confirms RA-6678 is the only gate; 30-minute credential diagnosis unlocks a full campaign-ready stack.
- **APP-compliant onboarding disclosure** — persona debate flagged this as a compliance unlock; closing it opens a customer segment currently blocked by regulatory exposure, not a technical gap.
- **Semantic RAG memory layer** (TurboQuant lesson [INFO]) — per-project `memory/` + retrieval step + weekly summarisation is scoped and justified; implementing it directly improves generator context quality and reduces empty-diff failures.
- **X-Forwarded-For fix is trivially scoped** — [WARN] RA-1043 rate-limiter is non-functional in Railway prod because it keys on the LB's internal IP; one-line `_IS_CLOUD` guard converts a dead control to a live one.
- **Health-check consecutive-failure threshold** ([WARN] sprint-12/scheduled-tasks) — adding a 2-failure gate + 30-min cooldown to the watchdog immediately restores alert credibility lost by the sandbox false-positive.

---

**THREATS**
- **Organic campaign (RA-5036) driving traffic before P0 stack is end-to-end verified** — CEO Board synthesis explicitly flags this ordering risk; a live campaign hitting an unverified ABR integration is an SLA and trust event, not just a bug.
- **False CRITICAL alerts have already eroded the alert channel** — [INFO] watchdog lesson states directly: "after one false CRITICAL alert, every subsequent alert is suspect." If this isn't corrected before the next real incident, on-call response will be delayed.
- **CI secret removal pattern** ([ERROR] sprint-12/security) — removing a hardcoded fallback without pre-seeding the GitHub secret causes hard CI failure on next push; any refactor touching auth defaults carries this risk silently.
- **Empty-diff loop completion with no detection** — if the generator produces nothing and the evaluator scores it 1.0/10 but the loop doesn't abort, the autonomy engine will mark the Linear ticket In Progress, exhaust retries, and close it as "complete" with zero delivered work; this is a silent audit failure.
- **Stale Vercel `rootDirectory` config** ([ERROR] sprint-12/deployment) — the fix requires a direct API PATCH, not the UI; any redeployment without correcting this breaks the frontend build silently until someone reads the Vercel build log.

## Phase 4 — SPRINT RECOMMENDATIONS
PRIORITY 1: **RA-6678** — P0 ABR_API_GUID missing in prod is a single env-var injection that unblocks every onboarding ABN lookup and directly enables the RA-6792 first-client flow currently stalled In Review. — Estimate: **XS (<1h)** — Impact: Unblocks the full paid-launch P0 chain (RA-6790→6795); converts the highest-priority In-Review cluster from stuck to mergeable; expected BVI +1 toward first MARATHON completion.

PRIORITY 2: **RA-6797** — CI smoke self-poisoning the /api/login rate limit between deploys is the hidden gate blocking clean merges on all six P0/P1 In-Review tickets; resolving it restores the gate-to-green loop the autonomous system depends on to confirm shipped work. — Estimate: **S (1–2h)** — Impact: Re-enables reliable CI for the entire paid-launch cluster; ZTE holds at 96 rather than regressing when false-red checks accumulate; clears the merge path for RA-6790 through RA-6795 in one shot.

PRIORITY 3: **"Generator empty-diff hard-stop"** *(no ticket — file as RA-new under Pi-Dev-Ops)* — The autonomous loop is completing full cycles and the evaluator scores 1.0/10 four consecutive times with no abort signal, meaning ZTE climbs on resolved CRITICALs while BVI stays flat and MARAATHONs stay at zero; add a hard-stop gate that fires when post-generation diff byte count equals zero before the evaluator runs. — Estimate: **M (2–4h)** — Impact: Converts loop cycles from wasted compute into real output; BVI improvement from 0 to positive within one autonomy window; directly addresses the SWOT's core gap between velocity metrics and user-visible progress.

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 3
- Low: 7
- Tickets created: None

_Generated 2026-06-17T20:39:23.897499+00:00_