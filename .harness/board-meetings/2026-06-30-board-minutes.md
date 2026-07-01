# Board Meeting Minutes — Cycle 0 (2026-06-30)

## Business Velocity Index (RA-696)
**BVI: 2** (+2 from prior cycle)
- CRITICALs resolved: 2
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
- Stale: RA-6838 (4d stale), RA-6850 (4d stale), RA-6847 (4d stale), RA-6842 (4d stale), RA-6841 (4d stale), RA-6812 (9d stale), RA-6678 (12d stale)
- Unassigned: RA-6774, RA-2989, RA-6469, RA-6470, RA-3041, RA-3042, RA-3043, RA-3044, RA-3045, RA-3900, RA-3971, RA-4189, RA-4190, RA-4191, RA-5261, RA-6464, RA-6471, RA-6472, RA-6475, RA-6495, RA-6669, RA-6671, RA-6815, RA-6838, RA-6850, RA-6847, RA-6842, RA-6841, RA-6812

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 115.6s)

**Finding #1** [MEDIUM] — _What is the current status of Anthropic's platform-managed trial credits API and whether API keys are required for trial-tier usage as of June 2026?_
  Anthropic's proposed June 15, 2026 billing restructure — which would have created a separate per-user monthly credit pool for Agent SDK and `claude -p` usage — was paused before taking effect; nothing changed and subscription limits remain as before. API keys are required for all direct API access; new Console accounts receive a one-time ~$5 starter credit (phone verification required, no credit card), after which prepaid Console credits must be purchased. Claude Pro/Max chat subscriptions do not include API access.
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-06-30)
  - [Claude API Key Free Tier 2026: What's Actually Free, What Isn't, and When You Need Console Credits](https://blog.laozhang.ai/en/posts/claude-api-key-free-tier) (fetched 2026-06-30)
**Finding #2** [MEDIUM] — _Have any Australian Business Register (ABR) API authentication or GUID requirements changed in the last 90 days that could affect ABN lookup integrations?_
  No changes to ABR API authentication or GUID requirements were detected. The official ABR web services registration page (currently version 9.9.7) still requires a GUID issued post-registration; no change notices, deprecation notices, or 2026 migration announcements were present in official documentation.
  - [Web services registration | ABN Lookup](https://abr.business.gov.au/Documentation/WebServiceRegistration) (fetched 2026-06-30)
**Finding #3** [HIGH] — _What are the current Stripe subscription gate best practices for SaaS onboarding flows, particularly around free-trial-to-paid transitions in 2026?_
  Stripe's current recommended approach for new integrations is the 'trial offers' API (requires `billing_mode=flexible` and API version `2026-03-25.preview` or later), which distinguishes 0-USD trials (status: `trialling`, no card required) from paid trials (status: `active`, card required); the legacy `trial_period_days` / `trial_end` parameter remains valid but is flagged as the legacy path and is the only option compatible with Stripe Checkout. Key end-behaviour options are cancel, pause, or create_invoice when no payment method exists at trial end; listening to `customer.subscription.trial_will_end` 3 days before expiry is the standard conversion hook.
  - [Configure trial offers on subscriptions | Stripe Documentation](https://docs.stripe.com/billing/subscriptions/trials) (fetched 2026-06-30)
  - [Use free trial periods on subscriptions | Stripe Documentation](https://docs.stripe.com/billing/subscriptions/trials/free-trials) (fetched 2026-06-30)

**Open questions** (research could not resolve):
  - Whether Anthropic has published a revised Agent SDK billing plan since pausing the June 15 change — the pause announcement committed to 'advance notice before any future change' but gave no timeline; no primary Anthropic changelog or console.anthropic.com announcement was reachable to confirm.
  - Whether the ABR has issued any out-of-band advisory (email to registered GUID holders, ATO developer newsletter) about upcoming authentication changes not yet reflected in the public documentation — the official page carries no dated change log.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)
**CEO:** The 96/100 ZTE score is measuring system elegance while three P0s enforce a zero-revenue state — RA-6678 (ABN lookup broken in prod), RA-6801 (PDF export requires an Anthropic key trial users don't have), and RA-6791 (subscription gate unverified) together mean no new client can sign up, verify their business, generate a report, or convert to paid. Highest-leverage action this sprint is unblocking the funnel in that order; everything else is compounding on a foundation that cannot yet earn.

**Revenue:** RA-6801 is the revenue kill-shot and finding #1 confirms there is no platform shortcut — Anthropic API keys are mandatory for all direct access; trial credits exist but require phone verification and a separate Console account, not a seamless in-product flow. The fix that protects existing revenue and unlocks the funnel is wrapping PDF generation behind a server-managed key with per-trial rate limits, turning the technical blocker into a conversion gate rather than a dead end.

**Product Strategist:** A user who reaches the PDF export step and hits a key wall will not debug Anthropic's billing structure — they will leave and attribute the failure to our product, not to an infrastructure constraint. Finding #1 confirms no managed trial path is coming from Anthropic's side, so the product must own the solution: either gate PDF to paid tiers as an explicit upgrade prompt (converting the blocker into a feature) or provision server-side trial keys with usage caps per account; the former ships in a day, the latter in a week.

**Technical Architect:** RA-6678 is a missing environment variable in Railway, not a code defect — finding #2 confirms the ABR API contract is unchanged and the GUID requirement is stable, so the fix is a single env var injection and a redeploy, testable in under ten minutes. The fact that this P0 is 12 days stale is a process failure: it should have been caught by the smoke-prod CI gate (`scripts/smoke_test.py`) on the first deploy that introduced the gap, and the absence of that detection signal is the real defect to fix.

**Contrarian:** Challenging the Technical Architect directly: finding #2 carries an explicit open question — whether the ABR has issued out-of-band advisory notices (email to GUID holders, ATO developer newsletter) not yet reflected in public docs (confidence: low). Patching the env var fixes today but doesn't confirm we're not one silent deprecation away from the same failure in 90 days; a health-check endpoint that probes the ABR GUID live, surfaced via `/health`, turns a one-time fix into durable signal. Also, a ZTE score of 96/100 while three P0s block all revenue entry is a measurement validity problem — if the metric cannot detect a zero-revenue state, we are optimising the wrong signal.

**Compounder:** The correct architecture for RA-6801 is a server-managed Anthropic key pool with per-trial credit metering — not because it's the fastest path today, but because it builds the metered-usage primitive that compounds into a self-funding trial-to-paid engine (usage approaches limit → upgrade prompt → Stripe conversion). Finding #3's Stripe `billing_mode=flexible` with `trial_will_end` webhook as the conversion hook is the pairing that makes this durable; building it as a flag now avoids a rearchitect in six months when trial volume justifies tiered credit pools.

**Custom Oracle:** In the restoration and insurance-compliance vertical, a prospective client whose ABN lookup fails at onboarding will not interpret that as a minor bug — they will interpret it as a signal that the platform cannot be trusted with compliance-critical data. Finding #2 confirms the ABR API is stable, meaning our instability is entirely self-inflicted; 12 days of P0 stale on RA-6678 in a regulated-industry product is a reputational risk that no ZTE score offsets, and a single onboarding failure shared in an industry Facebook group or broker network can foreclose an entire segment.

**Market Strategist:** The June 15 Anthropic billing restructure being paused (finding #1) is an inadvertent competitive window — any competitor who planned trial UX around managed credits faces the same constraint we do, and the first platform to ship a clean, frictionless, server-side-managed trial-to-report flow wins the segment's early adopters before the window closes. Our P0s are the distance between our current state and that first-mover position; the gap is measured in days if we prioritise correctly.

**Moonshot:** Resolving RA-6801 with a proper managed trial credit layer and wiring it to finding #3's Stripe flexible billing creates the components of a zero-touch acquisition funnel: signup → ABN verified → trial report generated server-side → Stripe trial starts → 3-day `trial_will_end` conversion hook fires — no human sales touch required. At scale across the Australian restoration sector, that is a self-funding distribution engine; the ceiling is every restoration business as a potential self-served customer, and the moat is the ABN-verified, compliance-aware onboarding no horizontal SaaS competitor will build for this vertical.

---

**CEO SYNTHESIS:** Finding #1 permanently closes the door on any platform-managed shortcut for trial API access, so we must own the solution: ship RA-6678 as an env var today, RA-6801 as a server-managed trial key with Stripe conversion hook this week, and RA-6791 end-to-end verified before the week closes — in that order, because each unblocks the next. The Contrarian's challenge to the ZTE score is the most uncomfortable truth in this debate: a 96/100 system that cannot onboard a single paying client is not a 96/100 business, and the metric needs a revenue-reachability gate before it means anything strategically. Until one client has completed the full signup → ABN → report → paid subscription loop, every other capability is velocity applied to a closed funnel.

## Phase 3 — SWOT
**STRENGTHS:**
- **ZTE Score 96/100** — system architecture and automation infrastructure score near-perfect; harness, kill-switches (RA-1966), judge-gated loop (RA-1970), and context compaction (RA-1967) are all production-wired.
- **BVI momentum** — 2 CRITICALs resolved this cycle; autonomous loop machinery (autonomy.py, tao_loop.py, swarm orchestrator) is operational and self-healing with Telegram alerting.
- **Senior agent topology live** — CFO/CMO/CTO/CS bots with dual-key gates (Wave 4, RA-1858) give executive-grade observability across burn, DORA, NPS, and ad-spend without human polling.
- **Security posture hardened** — HMAC webhooks, bcrypt auth with SHA-256 migration, path traversal guards, detect-secrets pre-commit, and 1Password validator all in place (lessons RA-1043-1049).

**WEAKNESSES:**
- **Zero paying clients onboarded** — CEO Board synthesis is explicit: a 96/100 system that cannot onboard one paying client is not a 96. RA-6678 (env var trial key), RA-6801 (server-managed trial + Stripe hook), and RA-6791 (end-to-end verification) are all open and blocking revenue.
- **28 unassigned issues** — 28 tickets floating with no owner (RA-6774 through RA-6815 range); 7 items stale 4–12 days. Autonomy queue cannot self-assign, so these silently age.
- **Watchdog credibility gap** — the false CRITICAL alert (2026-04-12, sandbox vs production env mismatch) demonstrates that the alerting layer cries wolf; every subsequent alert is discounted. Fix is documented but trust debt is real.
- **Scope discipline failures** — evaluator lessons show 591-file diffs on hotfixes (max 15) and 1.0/10 scores on empty diffs; the generator is not reliably surgical.

**OPPORTUNITIES:**
- **Trial-to-paid conversion funnel** — RA-6678 → RA-6801 → RA-6791 is a sequenced, unblocking chain; shipping it this week converts the system's biggest gap (onboarding) into a live revenue surface.
- **Stale issue sweep** — 7 stale items aged 4–12 days are low-hanging BVI points; resolving or triaging them this cycle lifts both BVI and autonomy queue throughput.
- **Semantic RAG memory** — per-project memory/ folders + retrieval-before-session (TurboQuant lesson) could materially improve generator output quality and reduce scope violations, compounding ZTE gains.
- **Stripe-Xero CFO provider** — synthetic data limits CFO bot's decision value; wiring real Stripe MRR + Xero cash/COGS unlocks the dual-key spend gate and makes the 6-pager actionable.

**THREATS:**
- **Onboarding bottleneck is existential** — Contrarian finding stands: no client onboarded = no validated unit economics = no growth thesis. Every week RA-6678/6801/6791 stays open, the ZTE score is a vanity metric.
- **Alert fatigue from sandbox false positives** — one false CRITICAL degrades trust in the entire alerting chain (lesson sprint-12-review/scheduled-tasks mirrors this). If a real production failure fires, it may be dismissed.
- **Scope creep in autonomous sessions** — 591-file hotfix diffs and 1.0/10 evaluator scores indicate the generator operates outside scope contract. Without enforcement, autonomous merges risk destabilising main.
- **Railway env var drift** — cron-trigger `last_fired_at` resets on every redeploy; 1Password op:// refs pass through dotenv as literals; ANTHROPIC_API_KEY="" inheritance poisons child processes. Each is documented but the pattern of env-layer surprises suggests systemic fragility under deploy pressure.

## Phase 4 — SPRINT RECOMMENDATIONS
PRIORITY 1: RA-6678 → RA-6801 → RA-6791 (Trial-to-paid conversion chain) — The system scores 96/100 on architecture but $0 on revenue; this three-ticket sequence (trial key env var → server-managed trial + Stripe hook → end-to-end verification) is the only sequenced, unblocked path to the first paying client. — Estimate: **L (4–8h)** — Impact: Closes the single largest ZTE gap; a working onboarding funnel converts the 96 into a commercially defensible number and demonstrates the autonomy loop produces real economic value.

---

PRIORITY 2: RA-2989 (Rotate 4 still-live leaked secrets — LINEAR / PERPLEXITY / swarm-ANTHROPIC / PI_CEO_PASSWORD) — Shipping a paid onboarding funnel while known credentials are live in production is an unhedged exploit vector that could erase the launch before it completes; rotation is non-negotiable before any external user touches the system. — Estimate: **S (1–2h)** — Impact: Eliminates active credential risk; also earns BVI points from closing a SECURITY ticket that has been open and partially-resolved, rebuilding alerting credibility (directly counters the watchdog trust-debt weakness).

---

PRIORITY 3: RA-3042 + RA-3043 + RA-3044 (CVE bundle — cryptography + setuptools RCE + pyjwt auth bypass on Pi-Dev-Ops) — A remote code execution via `setuptools` and an auth bypass via `pyjwt` on the production backend are incompatible with onboarding paying users; dependency bumps + smoke test can close all three in a single PR. — Estimate: **M (2–4h)** — Impact: Clears 3 High/Critical CVEs from the Pi-Dev-Ops backend; CI security checks go green and the system can be demonstrated to clients without known unpatched RCE exposure.

---

**Sequencing note:** Run 2 → 3 → 1 in that order. Rotate secrets and patch CVEs first (hours, not days), then launch the onboarding funnel against a hardened surface. Attempting the revenue funnel before secrets are rotated and CVEs patched is a reputational and security liability at the exact moment you need trust.

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 2
- Low: 3
- Tickets created: None

_Generated 2026-06-30T05:09:02.383841+00:00_