# Board Meeting Minutes — Cycle 0 (2026-07-01)

## Business Velocity Index (RA-696)
**BVI: 2** (0 from prior cycle)
- CRITICALs resolved: 2
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 2

## Attendees
- Pi CEO Autonomous Agent (Orchestrator)
- CEO Board: 9 personas (CEO, Revenue, Product Strategist, Technical Architect,
  Contrarian, Compounder, Custom Oracle, Market Strategist, Moonshot)
- Gap Audit Agent

## Phase 1 — STATUS
- ZTE Score (v1): unknown
- ZTE Score (v2): 94/100 [Zero Touch] (v1 base 75 + Section C 19/25)
- Urgent Issues: 10
- Cron Health: unknown

## Phase 2 — LINEAR REVIEW
- Urgent: 7 | High: 23
- Stale: RA-6838 (5d stale), RA-6850 (5d stale), RA-6847 (5d stale), RA-6842 (5d stale), RA-6841 (5d stale), RA-6812 (10d stale), RA-6678 (13d stale), RA-6801 (13d stale), RA-6792 (13d stale), RA-6791 (13d stale), RA-2996 (13d stale)
- Unassigned: RA-6774, RA-6873, RA-6874, RA-2989, RA-6469, RA-6470, RA-3045, RA-3900, RA-3971, RA-4190, RA-4191, RA-6464, RA-6471, RA-6472, RA-6475, RA-6495, RA-6669, RA-6671, RA-6815, RA-6838, RA-6850, RA-6847, RA-6842, RA-6841, RA-6812, RA-6801, RA-2996

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 162.2s)

**Finding #1** [MEDIUM] — _What is Anthropic's current policy on platform-managed trial credits for API access, and does it allow third-party platforms to proxy Anthropic API calls without end-user keys?_
  Anthropic's API requires an API key (or Workload Identity Federation token) per organisation — no public platform-managed trial-credits scheme exists in the documented API. A May 2026 proposal to move Agent SDK / claude -p / third-party usage to separate monthly credits was paused before its June 15 implementation date; all subscription-linked surfaces (including third-party tools via ACP) continue drawing from Pro/Max pools unchanged. No explicit permission or prohibition on proxying API calls without end-user keys appears in public documentation.
  - [Claude API Getting Started — Anthropic Platform Docs](https://platform.claude.com/docs/en/api/getting-started) (fetched 2026-07-01)
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-07-01)
**Finding #2** [MEDIUM] — _Have there been any recent changes to ABR (Australian Business Register) API authentication or GUID requirements in 2026 that could explain production lookup failures?_
  No documented GUID rotation, revocation, or authentication-format changes were found for 2026. However, the ABR live status dashboard (checked 2026-07-01) shows 'ABR Web Services — Degraded Performance' and 'Identifier Search — Degraded Performance' with no formal incidents logged since June 17 — degraded infrastructure performance is the most likely documented cause of current production lookup failures, not an authentication change.
  - [Australian Business Register Status](https://status.abr.gov.au/) (fetched 2026-07-01)
  - [Web Services Registration | ABN Lookup — Business.gov.au](https://abr.business.gov.au/Documentation/WebServiceRegistration) (fetched 2026-07-01)
**Finding #3** [HIGH] — _What are the current Stripe subscription gate best practices for SaaS onboarding flows, particularly around trial-to-paid conversion verification?_
  Stripe's canonical gate pattern is webhook-driven: listen for checkout.session.completed to begin provisioning, invoice.paid to renew access each billing cycle, and invoice.payment_failed to restrict access immediately. Use Stripe Entitlements (linked to checkout.session.completed) to mark the precise trial-to-paid conversion moment; store subscription.id and customer.id in your database as the gate source of truth rather than re-querying Stripe on each request.
  - [Sell subscriptions as a SaaS startup | Stripe Documentation](https://docs.stripe.com/get-started/use-cases/saas-subscriptions) (fetched 2026-07-01)
  - [Integrate a SaaS business on Stripe | Stripe Documentation](https://docs.stripe.com/saas) (fetched 2026-07-01)
**Finding #4** [HIGH] — _Has Anthropic shipped any model or API changes in the last 30 days that affect orchestrator compatibility or Claude Code SDK behaviour?_
  Multiple breaking-adjacent changes shipped in June–July 2026: SDK v2.1.197 makes Claude Sonnet 5 the default model (1M context window, promotional pricing through Aug 31); v2.1.187 fixes structured output reliability (StructuredOutput can no longer be re-called indefinitely after a successful call) and introduces a 5-minute idle abort for remote MCP tool calls that previously blocked forever (overridable via CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT); org-level model restrictions now gate --model/ANTHROPIC_MODEL; v2.1.196 fixes background job data loss and adds auto-resume after server restart.
  - [Claude Code Updates by Anthropic — July 2026 — Releasebot](https://releasebot.io/updates/anthropic/claude-code) (fetched 2026-07-01)
  - [Claude Platform Release Notes — Anthropic](https://docs.anthropic.com/en/release-notes/api) (fetched 2026-07-01)

**Open questions** (research could not resolve):
  - Anthropic does not publicly document whether it permits third-party SaaS platforms to proxy API calls on behalf of end users without requiring per-user API keys — this requires direct confirmation from Anthropic's sales or legal team via the Console usage-policy page or enterprise agreement review.
  - No evidence was found of specific ABR GUID rotation, revocation, or format changes in 2026 that would break previously working GUIDs — only platform-level degraded performance that appears transient and undocumented in the incident log.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)
**CEO:** Three P0 issues (RA-6801, RA-6792, RA-6791) are stacked in "In Review" with no resolution signal — 13 days of stale velocity on RA-6678 tells me the review gate is the bottleneck, not the engineering. The highest-leverage move this cycle is a forced merge-or-close decision on every "In Review" item before touching anything in Backlog; 94/100 ZTE means we're one broken onboarding flow away from a real churn event.

**Revenue:** The signup→PDF blocker (RA-6801) is a closed door on new ARR — every trial that hits the Anthropic key wall is a customer we're paying acquisition costs on and converting at zero (Finding #1 confirms no public platform-managed credits scheme exists, so the current architecture assumes something that isn't real). Simultaneously, RA-6791 means we can't verify paid billing end-to-end, which is a revenue-leak vector we're flying blind on.

**Product Strategist:** The core onboarding funnel — signup → report → PDF — is broken at two independent points (key requirement, ABR lookups), which means real users are hitting dead ends before they see product value; no validated demand signal survives a broken first run (Findings #1, #2). Fixing RA-6801 by proxying the Anthropic key server-side for trial users is the minimum viable product decision that unblocks the entire conversion loop without waiting for Anthropic policy clarity.

**Technical Architect:** Finding #4 is the quiet time bomb here — SDK v2.1.197 makes Claude Sonnet 5 the default and the 5-minute MCP idle abort is now active, meaning any orchestrator call that previously blocked indefinitely now silently dies at 5 minutes; we need to audit every MCP tool call site against `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` before the next deploy. The ABR issue (RA-6678) should be triaged against Finding #2's degraded-performance signal first — a retry-with-backoff wrapper may resolve it without any GUID rotation.

**Contrarian:** The Product Strategist's recommendation to proxy the Anthropic key server-side for trial users is commercially dangerous — Finding #1 explicitly notes no public permission exists for third-party platforms to proxy API calls without end-user keys, and this is flagged as `confidence: low` in the open questions; shipping this without direct Anthropic policy confirmation exposes us to a ToS violation that could terminate our API access and kill every paying customer simultaneously. The 13-day stale cluster (RA-6678, RA-6801, RA-6792, RA-6791) sitting "In Review" also suggests these aren't simple fixes — the CEO's merge-or-close framing may be masking genuine unresolved technical blockers, not a process failure.

**Compounder:** The Stripe webhook-driven gate pattern (Finding #3) — `checkout.session.completed` → provision, `invoice.paid` → renew, `invoice.payment_failed` → restrict — is the right architecture precisely because it compounds: once wired correctly it gates forever without re-querying Stripe on each request, eliminating a whole class of future billing bugs. Investing the engineering time to implement this canonically now (RA-6791) versus a quick-fix gate pays compounding dividends across every future pricing tier and plan change.

**Custom Oracle:** In Australian B2B SaaS with insurance-linked compliance exposure, a broken ABN lookup (RA-6678) isn't just a UX bug — it's a compliance and liability signal; clients in the restoration industry need ABN verification for contractor credentialing, and a `MALFORMED` failure in production means we may have already onboarded clients with unverified entities. The ABR degraded-performance finding (Finding #2) is somewhat reassuring, but we need a hard-coded fallback verification path (manual override or cached ABN validation) that satisfies due-diligence obligations even when ABR infrastructure is degraded.

**Market Strategist:** The June 15 Anthropic credit overhaul being paused (Finding #1) is actually a short-term window — it means competitors building on the same assumption of platform-managed trial credits are equally broken, and the first platform to establish a clean, documented trial flow with server-side key management wins the cohort of builders evaluating RestoreAssist right now. The 5-minute MCP idle abort introduced in SDK v2.1.197 (Finding #4) is a signal the market is moving toward tighter, more predictable agent runtimes — our orchestrator architecture should publicly demonstrate it handles this correctly as a trust differentiator.

**Moonshot:** If the onboarding flow (signup → ABN verify → report → PDF) becomes genuinely zero-touch — no manual steps, no key management friction, no ABR timeout failures — RestoreAssist becomes the only compliance-grade restoration SaaS a new operator can activate in under 10 minutes, which is the actual 10x framing: not a better report, but the first report a new business can generate before their first job. That ceiling justifies treating RA-6801, RA-6678, and RA-6791 as a single integrated onboarding sprint, not three separate tickets.

---

**CEO SYNTHESIS:** The debate converges on one critical constraint: the P0 cluster (RA-6801, RA-6678, RA-6791) must be treated as a single zero-touch onboarding sprint, not three independent tickets, because each broken individually kills the full funnel. Before shipping any server-side Anthropic key proxy, we must obtain explicit Anthropic policy confirmation — the Contrarian is right that ToS ambiguity is an existential risk that outweighs time-to-ship — so the unblocking path is a direct Anthropic sales/legal enquiry running in parallel with an ABR retry-with-backoff fix and the canonical Stripe webhook gate. Close or escalate every "In Review" item to a named decision by EOD today; stale reviews are the actual velocity constraint, not engineering capacity.

## Phase 3 — SWOT
**SWOT — Pi-CEO | Phase 3 | 2026-07-01**

---

**STRENGTHS**

- **ZTE v2 at 94/100.** The autonomous zero-touch pipeline is architecturally mature; the scoring system itself validates the design intent.
- **Operational intelligence depth.** 20 documented hard-won lessons (ANTHROPIC_API_KEY inheritance, XFF spoofing, op:// literal passthrough, trailing-newline 401s) function as a regression firewall — failures are named, fixed once, and stay fixed.
- **Multi-axis kill switch (RA-1966).** `TAO_MAX_ITERS` + `TAO_MAX_COST_USD` + `HARD_STOP_FILE` means runaway loops are bounded by design, not by manual intervention.
- **Bidirectional Telegram loop.** Async inbound-idea routing without auto-promotion to Linear gives human oversight without blocking the autonomy loop.
- **Senior-agent topology (Wave 4).** CFO/CMO/CTO/CS bots with dual-key gates give executive visibility and spend controls without requiring Phill in the loop.

---

**WEAKNESSES**

- **BVI of 2, zero MARATHON completions.** High ZTE score masks low throughput — the pipeline runs cleanly but isn't closing work at velocity. Portfolio improved: 0 this cycle.
- **P0 funnel fragmented (RA-6801, RA-6678, RA-6791).** CEO Board synthesis is explicit: these three are one zero-touch onboarding sprint, not independent tickets. Treating them separately guarantees partial funnel breakage regardless of individual completion.
- **27 unassigned + 11 stale issues (up to 13 days).** No owner, no movement — backlog hygiene is structurally broken. RA-6678 and RA-6791 are both in the stale list *and* the P0 cluster.
- **Silent failure modes not yet closed.** `/health` still doesn't surface `linear_api_key: bool` or last-successful-tick timestamp (lessons: *Silent failure mode discovered*, *Sleep-first poller bootstrap delay*). The system reports green on a dead autonomy loop.
- **Scheduled-task topology not 24/7.** Cowork sandboxes are ephemeral; seven commits sat unpushed locally while Railway ran stale code (lesson: *'autonomous' is a property of TOPOLOGY*). Any task dependent on Mac uptime isn't autonomous.

---

**OPPORTUNITIES**

- **P0 sprint consolidation is a single decision away.** Reframing RA-6801/6678/6791 as one sprint rather than three tickets unlocks the full onboarding funnel — the CEO Board synthesis already states the blocker is framing, not capability.
- **Anthropic policy confirmation unblocks scalable multi-tenancy.** The Contrarian is correct that ToS ambiguity on the server-side key proxy is existential. One direct Anthropic sales/legal inquiry resolves it and either clears or re-routes the entire architecture decision.
- **Cron reset fix is one PR.** `abs()` in the debounce check + startup catch-up firing overdue triggers within 10s eliminates an entire class of missed-window bugs on every Railway redeploy (lesson: RA-579/scheduler).
- **`/health` hardening converts silent failures into observable alerts.** Adding `linear_api_key: bool` + last-tick timestamp lets the external watchdog catch dead autonomy loops without human inspection — closes the gap the lesson explicitly names.
- **Consecutive-failure thresholds on watchdog prevent alert fatigue.** The lesson (*watchdog false positives*) proves one false CRITICAL destroys trust in all subsequent alerts. A 2-failure threshold + 30-min cooldown is a small change with outsized signal-to-noise ROI.

---

**THREATS**

- **Anthropic ToS on server-side key proxy is an existential risk.** Shipping before explicit policy confirmation — as the Contrarian warned — could invalidate the entire multi-tenant architecture post-launch. Time-to-ship does not outweigh compliance exposure.
- **Alert trust erosion from sandbox false positives.** Watchdog CRITICAL from a Cowork sandbox with missing `anthropic>=0.90` (lesson: *marathon watchdog*) means the next real CRITICAL may be ignored. One false alarm poisons the channel.
- **Stale + unassigned backlog compounds.** 10 Urgent + 23 High with 0 MARATHON completions this cycle — if the trend holds, the backlog grows faster than it's cleared, and Urgent issues age into architectural debt.
- **Railway redeploy resets cron state silently.** Without the abs() fix and startup catch-up, every deploy drops scheduled windows with no error surfaced — a recurring operational tax that compounds across the portfolio (lesson: RA-579).
- **Autonomy poller silent-skip on missing `LINEAR_API_KEY`.** The system can appear fully operational (health 200, uptime climbing) while the autonomy loop fires zero sessions — indistinguishable from a working system until `sessions.total` is inspected manually (lesson: *Silent failure mode discovered*).

## Phase 4 — SPRINT RECOMMENDATIONS
**PRIORITY 1: RA-6801 + RA-6678 + RA-6791 (P0 zero-touch onboarding cluster — run as a single sprint)** — The CEO Board synthesis is explicit: these three tickets are one broken funnel, and completing any subset leaves the pipeline inoperable at the seam between them. — Estimate: **XL (>8h)** — Impact: The only path to non-zero MARATHON completions this cycle; every point of BVI improvement flows through this funnel being end-to-end passable.

---

**PRIORITY 2: New ticket — "Fix /health silent failure: expose `linear_api_key: bool` + last-successful-tick timestamp"** — The autonomy loop can be fully dead while `/health` returns 200 green, making the ZTE score structurally untrustworthy; this is a documented hardwired lesson (CLAUDE.md §Autonomy and Health) that has not been closed. — Estimate: **S (1–2h)** — Impact: Restores observability integrity; without it, a dead autonomy loop is invisible and BVI stagnation goes undetected until a manual check.

---

**PRIORITY 3: RA-2989 — Complete rotation of 4 still-live leaked secrets (LINEAR / PERPLEXITY / swarm-ANTHROPIC / PI_CEO_PASSWORD)** — Half-resolved status means three of four credentials remain a live compromise vector across every bot and pipeline that touches them, and any autonomy sprint built on top inherits that exposure. — Estimate: **XS (<1h remaining)** — Impact: Removes the security ceiling on autonomous operation; a compromised `swarm-ANTHROPIC` key can silently reroute or exhaust the entire Wave 4 senior-agent fleet.

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 0
- Low: 0
- Tickets created: None

_Generated 2026-07-01T05:08:48.862161+00:00_