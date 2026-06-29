# Board Meeting Minutes — Cycle 0 (2026-06-16)

## Business Velocity Index (RA-696)
**BVI: 5** (0 from prior cycle)
- CRITICALs resolved: 5
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
- ZTE Score (v2): 83/100 [Zero Touch] (v1 base 75 + Section C 8/25)
- Urgent Issues: 10
- Cron Health: unknown

## Phase 2 — LINEAR REVIEW
- Urgent: 4 | High: 26
- Stale: RA-6499 (4d stale), RA-6500 (4d stale), RA-6484 (4d stale), RA-6474 (4d stale), RA-6485 (5d stale), RA-6489 (5d stale), RA-6490 (5d stale), RA-6498 (5d stale), RA-6497 (5d stale), RA-6496 (5d stale), RA-6495 (5d stale)
- Unassigned: RA-6732, RA-6731, RA-6729, RA-6728, RA-3037, RA-6724, RA-6723, RA-6721, RA-6709, RA-6689, RA-6688, RA-6687, RA-6684, RA-6678, RA-6671, RA-6670, RA-6669, RA-6568, RA-6567, RA-6499, RA-6500, RA-6484, RA-6485, RA-6489, RA-6490, RA-6498, RA-6497, RA-6496, RA-6495

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 126.8s)

**Finding #1** [MEDIUM] — _What is the current status and pricing of Mythos AI's planner product, and what pricing changes are scheduled to take effect around 22 June 2026?_
  No company named 'Mythos AI' with a discrete 'planner' product was found. All results reference Anthropic's Mythos model tier, publicly available as Claude Fable 5 (launched 9 June 2026) at $10/M input tokens and $50/M output tokens. The pricing change taking effect 23 June 2026 removes Fable 5 from Pro/Max/Team/Enterprise subscription plans, requiring usage-credit billing on top of the monthly subscription; Anthropic states it will reinstate flat-rate access once capacity permits.
  - [Claude Fable 5 and Claude Mythos 5 | Anthropic](https://www.anthropic.com/news/claude-fable-5-mythos-5) (fetched 2026-06-16)
  - [Anthropic releases Claude Fable, a version of Mythos, days after warning AI is becoming too dangerous](https://techcrunch.com/2026/06/09/anthropics-claude-fable-5-is-a-version-of-mythos-the-public-can-access-today/) (fetched 2026-06-16)
**Finding #2** [MEDIUM] — _What are the ABR API's current authentication requirements and have there been any recent changes to the ABR_API_GUID parameter or endpoint behaviour?_
  The ABR API still requires a GUID obtained at registration ('AuthenticationGuid') for all web service calls; no changes to this parameter or the two SOAP endpoints (Document/RPC style at abr.business.gov.au) are documented. The latest recommended method is SearchByABNv202001; older versions remain active. Documentation is at version 9.9.7. A routine maintenance window was scheduled for 17 June 2026 but no authentication or endpoint changes were announced.
  - [Web services registration | ABN Lookup](https://abr.business.gov.au/Documentation/WebServiceRegistration) (fetched 2026-06-16)
  - [Web services methods | ABN Lookup](https://abr.business.gov.au/Documentation/WebServiceMethods) (fetched 2026-06-16)

**Open questions** (research could not resolve):
  - What is the current status and pricing of Mythos AI's planner product, and what pricing changes are scheduled to take effect around 22 June 2026? — No company 'Mythos AI' with a standalone 'planner' product was found; if this refers to a startup distinct from Anthropic's Mythos model tier, no public pricing or June-22 change announcement could be sourced.
  - Has DigitalOcean made any recent changes to their container registry or build pipeline that could affect monkfish-app builds failing since commit 0060d6f? — 'monkfish-app' and commit 0060d6f appear to be a private repository; no public DigitalOcean changelog entry, release note, or community thread specifically linking a platform-side change to this project or commit was found. The only platform-level context available is an ongoing BuildKit limitation on App Platform (RUN --mount directives unsupported) and a May 2026 multi-region build incident, neither of which can be tied to this specific commit without access to the private repo's CI logs.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)


## Phase 3 — SWOT


## Phase 4 — SPRINT RECOMMENDATIONS
PRIORITY 1: RA-6678 — ABR_API_GUID missing in prod breaks every ABN lookup and blocks onboarding entirely; this is the only P0 actively failing for real users and is almost certainly a missing env var or one-line config fix. — Estimate: XS (<1h) — Impact: Restores onboarding funnel to 100% functional; single highest ZTE score recovery per effort unit.

PRIORITY 2: RA-6728 — 8 high-severity prod dependency CVEs mean `pnpm audit --prod` is red in CI, which will block the release gate (RA-6688 already sitting at ~85/100) and expose the platform to known exploit paths; resolving these also unblocks any downstream security-gated deployments. — Estimate: M (2–4h) — Impact: Clears the audit gate, lifts release-gate score, eliminates known exploit surface before the next client demo.

PRIORITY 3: RA-6731 — The Live Teacher turn endpoint serving a canned stub means the product's headline AI feature is theatrically functional but operationally inert; wiring it to the real cloud client converts a demo into a shipped feature. — Estimate: M (2–4h) — Impact: Converts Live Teacher from vaporware to a real revenue-qualifying feature; directly improves product completeness score and unblocks QA sign-off on that surface.

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 2
- Low: 4
- Tickets created: RA-6737, RA-6738

_Generated 2026-06-16T05:06:46.625248+00:00_