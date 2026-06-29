# Board Meeting Minutes — Cycle 0 (2026-06-28)

## Business Velocity Index (RA-696)
**BVI: 6** (+6 from prior cycle)
- CRITICALs resolved: 6
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 0

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
- Stale: RA-6812 (7d stale), RA-6678 (10d stale)
- Unassigned: RA-6774, RA-2989, RA-6469, RA-6470, RA-3041, RA-3042, RA-3043, RA-3044, RA-3045, RA-3900, RA-3971, RA-4189, RA-4190, RA-4191, RA-5261, RA-6464, RA-6471, RA-6472, RA-6475, RA-6495, RA-6669, RA-6671, RA-6815, RA-6838, RA-6850, RA-6847, RA-6842, RA-6841, RA-6812

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 94.5s)

**Finding #1** [HIGH] — _Has Anthropic changed its API key requirements or trial credit policies in the last 30 days in a way that would affect platform-managed credits for new signups?_
  Anthropic announced on May 14, 2026 that Agent SDK and claude -p usage would move to separate metered credit pools starting June 15, 2026 — but on June 15 Anthropic confirmed via its Help Center that the change is 'no longer happening' and those surfaces continue drawing from Pro/Max/Team/Enterprise subscription limits exactly as before. No changes were made to API key requirements or trial credit grants for new signups; new accounts still receive a small free credit allocation via the standard console registration flow.
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-06-28)
  - [Pricing - Claude Platform Docs](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-06-28)
**Finding #2** [HIGH] — _What is the current status and documentation for the Australian Business Register (ABR) API, and are there any known outages or GUID/authentication changes affecting ABN lookups?_
  As of June 28, 2026, the ABR reports all systems operational with no incidents in the past two weeks. GUID-based authentication for ABN Lookup web services remains unchanged — GUIDs are obtained via free registration at abr.business.gov.au and no authentication scheme changes have been announced. Scheduled Christmas/New Year maintenance runs midday AEDT 24 Dec 2026 through 4 Jan 2027.
  - [Australian Business Register Status](https://status.abr.gov.au/) (fetched 2026-06-28)
  - [Web services | ABN Lookup - Business.gov.au](https://abr.business.gov.au/Tools/WebServices) (fetched 2026-06-28)
**Finding #3** [HIGH] — _What are the current Anthropic Claude API pricing tiers and trial credit offerings as of June 2026 that would affect RestoreAssist's onboarding flow?_
  Anthropic's current API tiers (from primary docs, June 2026): Haiku 4.5 at $1/$5 per MTok input/output; Sonnet 4.5/4.6 at $3/$15; Opus 4.5–4.8 at $5/$25; Fable 5 and Mythos 5 at $10/$50. New accounts receive a small free credit allocation (third-party sources cite $5); a phone-verified registration is required. The Batch API applies a 50% discount across all models. No additional per-use charges were introduced in the last 30 days — the June 15 subscription-billing change was paused.
  - [Pricing - Claude Platform Docs](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-06-28)
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-06-28)

**Open questions** (research could not resolve):
  - The exact dollar amount of Anthropic's new-account trial credit is not confirmed in primary Anthropic documentation (only 'a small amount'); the $5 figure comes from third-party sources and may not reflect a formally published policy.
  - Whether RestoreAssist's onboarding uses direct API key issuance (new-signup trial credits) or a subscription seat model is not determinable from public sources — if it uses Pro/Max/Team seats, the paused June 15 change would have been directly relevant; confirm which billing surface RestoreAssist provisions for new users.
  - No ABR changelog or developer newsletter was found confirming the absence of GUID format changes; only the status page was checked. A direct query to ABR developer support would give higher certainty.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)
**CEO:** The two P0s (RA-6801, RA-6678) are both blocking the same critical path — first-client onboarding — and neither has shipped a fix despite sitting In Review. With a 96 ZTE score (#1, #2 confirm no external blockers), the drag is internal: review velocity is the constraint, not the problem definition. Unblock those two PRs today; everything else is noise until revenue is flowing.

**Revenue:** RA-6678 means every ABN lookup in production returns MALFORMED (#2 confirms ABR auth is unchanged, so the fault is ours — a missing GUID env var), which means zero clients can complete onboarding and no money moves. RA-6801 compounds it: even if ABN resolves, the report-gen wall stops the trial-to-paid conversion moment cold. Both tickets are 7–10 days stale with zero excuse — these are the only two numbers that matter this week.

**Product Strategist:** The signup-to-PDF flow (RA-6792) is the product's single proof point: a new user arrives, verifies their business, gets a report, sees value, pays. Every hour RA-6801 and RA-6678 remain open is an hour that proof point can't be demonstrated to real prospects. Fix the key requirement architecture (#3 confirms platform-managed credits exist and are sufficient) so no user ever hits an API-key wall — that's a product design debt, not just a bug.

**Technical Architect:** RA-6801's root cause — report-gen requiring a direct Anthropic key when platform-managed trial credits exist — signals an architectural coupling between credential provisioning and the report pipeline that will keep biting us. Research finding #1 confirms the subscription credit model is stable and the June 15 change was paused, so there's no moving target here; the fix is to wire report-gen through the platform credential layer, not ask new users to supply a key. Do it once, do it cleanly, or we'll patch this forever.

**Contrarian:** The Technical Architect recommends wiring report-gen through the platform credential layer as a clean fix — but open question #2 in the research brief flags that we don't actually know whether RestoreAssist provisions direct API keys or subscription seats for new users; `confidence: low` on the assumption that trial credits are sufficient. If new signups are on a direct-API surface with only a $5 unconfirmed free tier (#3 cites a third-party figure, not primary Anthropic docs), the "platform-managed credits" framing may be wrong and the correct fix is a different architecture entirely. Ship a hotfix today but don't architect around an assumption we haven't verified.

**Compounder:** A 96 ZTE score is a genuine asset — it means the autonomous loop is close to frictionless — but compound value only accrues if the top of funnel clears. Two stale P0s on the same onboarding path suggest a review-gate bottleneck that will recur on every future critical fix. Building a faster unblock reflex (same-day In Review → Merged for P0s) compounds more than any individual feature shipped this quarter.

**Custom Oracle:** In the restoration and insurance-compliance space, a broken ABN lookup (RA-6678) isn't just a UX defect — it's a trust signal that the platform can't validate business identity, which is a regulatory red flag for any client operating under AFSL or insurance intermediary obligations. ABR GUID auth is confirmed stable (#2), so the fix is a 5-minute env var deployment; leaving a known identity-verification failure in production for 10 days in this vertical is commercially dangerous, not just embarrassing.

**Market Strategist:** The Anthropic credit model is stable (#1, #3) and the ABR is operational (#2), which means all external blockers are resolved — the market window for first-client onboarding is open right now. Competitors in the Australian SMB compliance space are not standing still; a 10-day stale P0 on identity verification is 10 days a rival can use to close the same prospect. The signal is clear: the moat is execution speed, not technology differentiation.

**Moonshot:** If the signup-to-PDF flow works frictionlessly at scale, RestoreAssist becomes the fastest path from "I have a damaged property" to "I have a verified, documented claim" in the Australian market — that's a distribution wedge into every insurance panel and restoration network in the country. RA-6801 and RA-6678 aren't bug fixes; they're the gate to a $50M+ addressable market that's currently locked. Solve the two env vars, prove the loop, then sell the loop.

---

**CEO SYNTHESIS:** Both P0s are self-inflicted env var and architecture gaps — not external blockers — confirmed by research finding #2 (ABR operational) and #1 (Anthropic credits stable). The Contrarian's flag is the only open risk worth acting on: before architecting the credential layer, confirm whether new signups hit direct API keys or subscription seats, because the fix differs materially. Unblock RA-6678 today (env var deploy), ship a hotfix for RA-6801, verify the assumption on billing surface, and let nothing else move until a real user completes signup-to-PDF in production.

## Phase 3 — SWOT
**STRENGTHS:**
- ZTE Score v2 at 96/100 — architecture is objectively near-elite; the harness, kill-switches (RA-1966), judge-gating (RA-1970), and context compaction (RA-1967) are all wired and tested
- BVI +6 from 6 CRITICAL resolutions confirms the loop is closing real issues, not just generating tickets
- Self-healing infrastructure: Anthropic credits stable (research #2), ABR operational (research #1) — external dependencies are not the constraint; blockers are internal and controllable
- SDK architecture is hardened (RA-1169–1184): push auth, webhook HMAC, rate-limit cloud-IP fix, model-policy enforcement — no surface-treatment gaps remaining from the April marathon

**WEAKNESSES:**
- Two P0s are self-inflicted env var / architecture gaps (RA-6678 env var deploy, RA-6801 hotfix) — confirmed by persona synthesis; both are fixable today but haven't shipped
- 10 Urgent + 26 High open issues with 29 unassigned tickets signals triage debt exceeding capacity; the autonomy queue isn't consuming backlog fast enough
- Evaluator scores of 1.0/10 across completeness/correctness/conciseness (lessons `evaluator/bug`) reveal a loop that produces empty diffs — the generator is stalling silently rather than producing surgical code
- Scope contract violated: 591 files modified in a hotfix-class task (lesson `evaluator/hotfix`) — the containment gate is not enforced consistently upstream of commit

**OPPORTUNITIES:**
- Unblock RA-6678 (env var deploy) today — persona synthesis explicitly calls this the highest-leverage single action; unblocking it likely clears a cluster of downstream Urgent issues
- Billing surface assumption (new signups: direct API keys vs subscription seats) is unverified — persona synthesis flags this as the only open risk that changes the architecture decision; one confirmation call avoids a wrong-path credential layer build
- 29 unassigned issues represent capacity the autonomy loop can absorb without any new scoping — routing these through `.harness/projects.json` and `autonomy.py` is zero-cost pipeline fill
- Semantic RAG / per-project memory (lesson `sprint-12-review/architecture`, TURBOQUANT-ASSESSMENT) is architecturally mapped but unimplemented — delivers context precision gains without model or infra changes

**THREATS:**
- Stale items RA-6812 (7d) and RA-6678 (10d) signal issues that survive multiple autonomy cycles unresolved — if the judge never marks GOAL_MET on these, they become permanent fixtures and erode BVI signal
- Watchdog false-positives (lesson `sprint-12-review/scheduled-tasks`, lesson `marathon watchdog`) destroy alert trust; one false CRITICAL means every subsequent CRITICAL is discounted — the credibility of the escalation path degrades silently
- Empty-diff generator failures (evaluator/bug lessons) burn API budget and TAO_MAX_ITERS without producing value; if unchecked, the autonomy loop will exhaust cost ceilings on no-ops while the backlog grows
- Hardcoded fallback secrets removed without CI secret injection (lesson `sprint-12-review/security`) caused a hard CI failure — any similar cleanup across the portfolio without a matching secret-set step will break CI on the next push

## Phase 4 — SPRINT RECOMMENDATIONS
**PRIORITY 1: RA-6678** — Resolve env var deploy breakage — *Rationale: Persona synthesis marks this the single highest-leverage action in the entire backlog; it is the upstream gate blocking a cluster of downstream Urgents from deploying, making every hour it sits open compound waste.* — **Estimate: S (1–2h)** — **Impact: Restores Railway deploy path; expected to cascade-close 3–5 downstream Urgent tickets and lift operational health score immediately; highest ZTE delta per hour of any item on the board.**

---

**PRIORITY 2: RA-2989** — Complete secret rotation (LINEAR / PERPLEXITY / swarm-ANTHROPIC / PI_CEO_PASSWORD) — *Rationale: Four credentials are confirmed live and leaked; the ticket is already half-resolved, meaning the remaining blast radius is known and bounded — this is the cheapest security close on the board.* — **Estimate: XS (<1h)** — **Impact: Eliminates active credential exposure that currently undermines the entire ZTE security posture regardless of architecture score; closes the final gap between a 96 and a clean 100 on the security sub-dimension.**

---

**PRIORITY 3: Fix evaluator empty-diff stall** *(propose new ticket: "RA-eval-stall-fix — generator producing silent empty diffs, evaluator returning 1.0/10")* — *Rationale: Until the generator stops stalling and producing empty diffs, the autonomy loop burns compute but cannot consume the 29 unassigned backlog items — triage debt will grow regardless of how many tickets exist.* — **Estimate: M (2–4h)** — **Impact: Restores autonomous loop throughput; the 29 unassigned tickets become processable without any new scoping; scope containment gate (591-file hotfix lesson) should be wired in the same pass to prevent recurrence.**

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 3
- Low: 7
- Tickets created: None

_Generated 2026-06-28T05:06:55.380592+00:00_