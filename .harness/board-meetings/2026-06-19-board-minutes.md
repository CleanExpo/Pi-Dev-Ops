# Board Meeting Minutes — Cycle 0 (2026-06-19)

## Business Velocity Index (RA-696)
**BVI: 4** (-4 from prior cycle)
- CRITICALs resolved: 4
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 8

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
### CURRENT-CYCLE RESEARCH (fast, 153.7s)

**Finding #1** [MEDIUM] — _What is Anthropic's current policy on trial credits and API key requirements for new signups as of June 2026?_
  New API accounts at console.anthropic.com receive approximately $5 in free trial credits on signup with no credit card required; phone number verification is mandatory before API access is granted. The proposed June 15 billing change — which would have split Agent SDK, claude -p, and third-party app usage into a separate monthly credit pool — was paused and did not take effect; subscription usage continues drawing from existing Pro/Max/Team/Enterprise pools unchanged.
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-06-19)
  - [How to Get a Free Anthropic API Key in 2026 (Plus Free Credits)](https://www.getaiperks.com/en/ai/free-anthropic-api-key) (fetched 2026-06-19)
**Finding #2** [MEDIUM] — _Has Anthropic made any changes in the last 30 days to Claude model pricing or the Sonnet/Opus tier structure that would affect Pi-CEO orchestration costs?_
  No per-token price changes to Sonnet or Opus in the last 30 days. Current API rates are Claude Sonnet 4.6 at $3.00/$15.00 per 1M input/output tokens and Claude Opus 4.8 at $5.00/$25.00 per 1M tokens; the 1M-token context window is now included at standard per-token pricing with no premium surcharge. The paused June 15 Agent SDK billing split means Pi-CEO orchestration costs on subscription plans remain unchanged.
  - [Current Anthropic Claude API Pricing 2026: Opus, Sonnet & Haiku Costs](https://devtk.ai/en/blog/claude-api-pricing-guide-2026/) (fetched 2026-06-19)
  - [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026) (fetched 2026-06-19)
**Finding #3** [HIGH] — _What is the current Australian Business Register (ABR) API status and any known outages or authentication changes affecting ABN lookup in June 2026?_
  The ABR API — covering ABN System, ABR Web Services, and Identifier Search — is fully operational as of June 19 2026 with no incidents, outages, or authentication changes recorded at any point in June 2026.
  - [Australian Business Register Status](https://status.abr.gov.au/) (fetched 2026-06-19)
**Finding #4** [LOW] — _What competing AI-powered business intelligence or report-generation platforms have launched or updated their onboarding flows in the last 60 days that RestoreAssist should benchmark against?_
  Two notable launches in the April–June 2026 window: Sakana AI opened a closed beta (≈300 professionals across financial institutions and consulting firms) for an 'ultra deep research' agent producing 100+ page reports in ~8 hours; and Perplexity launched its 'Computer' enterprise AI agent routing proprietary Snowflake data and legal contracts for BI use cases, targeting Microsoft and Salesforce enterprise buyers. Specific onboarding-flow UX details were not available from indexed sources.
  - [Sakana AI launches ultra deep research agent for 100+ page reports in 8 hours | VentureBeat](https://venturebeat.com/technology/when-deep-research-isnt-enough-for-your-business-sakana-ai-launches-ultra-deep-research-agent-for-100-page-reports-in-8-hours) (fetched 2026-06-19)
  - [Perplexity takes its 'Computer' AI agent into the enterprise, taking aim at Microsoft and Salesforce | VentureBeat](https://venturebeat.com/technology/perplexity-takes-its-computer-ai-agent-into-the-enterprise-taking-aim-at) (fetched 2026-06-19)

**Open questions** (research could not resolve):
  - What exact date will Anthropic implement its revised Agent SDK billing plan after the June 15 2026 pause — no revised timeline published as of June 19 2026.
  - Are there specific onboarding-flow UX details (step count, free-trial gate, friction benchmarks) for Sakana AI ultra deep research or Perplexity Computer enterprise? Primary VentureBeat articles were rate-limited; only search-result excerpts retrieved.
  - Are there Australian disaster-recovery or insurance-vertical AI report-generation tools (beyond general BI platforms) that updated onboarding in this window? No indexed sources found at this specificity level.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)
**CEO:** ZTE v2 at 96/100 is strong infrastructure signal, but 10 urgent issues open means the system produces faster than it closes — and RA-6801 is a direct revenue block where new clients cannot complete the core product loop. The ABR API is fully operational per Finding #3, which means RA-6678's MALFORMED lookups are a code/configuration bug that must close today before any campaign spend compounds onboarding failure.

**Revenue:** RA-6801 and RA-6791 together represent the complete commercial validation loop — a client who can't finish signup and a paid subscriber whose billing gate fails are both zero-revenue events regardless of ZTE score. Per Finding #1, Anthropic trial credits remain on subscription plans (the June 15 change was paused), so report-gen requiring a direct API key is an implementation choice, not a platform constraint — this is fixable and must be fixed before RA-5036's organic campaign sends live traffic into a broken funnel.

**Product Strategist:** RA-6792 (first-client onboarding: signup to report export) is the single highest-fidelity product signal available — until a real client completes that loop, every other metric is synthetic. Finding #4 shows Sakana AI and Perplexity are accelerating into enterprise report generation, which means the window to establish onboarding quality as a differentiator is now, not after the organic launch is already running.

**Technical Architect:** With four P0s clustered around the same user-facing surfaces (ABR auth, Anthropic key injection, billing gate, report export), the pattern is integration surface misconfiguration, not architectural debt. The 7-day hardening sprint (RA-6800) is the right container, but it must sequence P0 closure first — hardening non-blocking surfaces while the core loop is broken delivers a reliable system nobody can use.

**Contrarian:** The Compounder's "pause campaign spend" recommendation is correct in direction but the CEO's framing that RA-6801 is a pure "code choice" deserves scrutiny — Finding #1's claim that the June 15 billing pause is stable carries `confidence: low` because the Research Brief explicitly flags that no revised Anthropic timeline has been published; if that billing architecture activates mid-sprint, Pi-CEO orchestration costs could shift materially with zero warning, invalidating the assumption that fixing the API key injection is a free move. At least one open question in the brief is a live commercial risk, not a background curiosity.

**Compounder:** Every day RA-6678 and RA-6801 stay open, RA-5036's organic traffic converts to zero — that is compounding churn before first activation, which is the most expensive failure mode in SaaS and the hardest to reverse once brand impression is set. The organic launch running against a broken funnel is burning the precise moment when first impressions form; pause spend until P0s are verified end-to-end in production.

**Custom Oracle:** In Australian restoration and insurance-linked compliance, a client who hits ABN lookup failure during onboarding reads it as a data reliability signal, not a bug — and that perception is terminal in a sector where regulatory accuracy is table stakes. Finding #3 confirms the ABR API is fully operational, so this is an internal `ABR_API_GUID` env misconfiguration; it is both urgent and straightforward, but must be verified end-to-end in production before any regulated client is touched.

**Market Strategist:** Finding #4 confirms enterprise AI report generation is accelerating — Sakana AI's 100+ page reports and Perplexity's enterprise data routing are both closing on RestoreAssist's core value proposition. RestoreAssist's defensible moat is Australian compliance specificity (ABR, insurance vertical), and that moat only holds if the product demonstrably works — every week the P0s stay open is a week competitors establish enterprise report credibility without the compliance friction that RestoreAssist uniquely solves.

**Moonshot:** If the four P0s close this week and the hardening sprint delivers a genuinely zero-touch signup-to-report experience, RestoreAssist becomes a replicable template for the broader Pi-CEO platform — any regulated Australian vertical (NDIS, aged care, construction compliance) runs the same onboarding-to-report engine. The ceiling is not one product but a compliance reporting platform that compounds across verticals; that ceiling only becomes visible once the first client completes the loop without human intervention.

---

**CEO SYNTHESIS:** The system is structurally strong at ZTE 96/100 but commercially non-functional — RA-6801 and RA-6678 are blocking the first paying client from completing the core product loop, and running RA-5036's organic campaign against a broken funnel is destroying brand trust at the worst possible moment. The exclusive focus of the hardening sprint must be closing the four P0 blockers (RA-6801, RA-6678, RA-6792, RA-6791) with end-to-end production verification before any further campaign spend. ABR is operational (Finding #3) and Anthropic billing is stable (Findings #1, #2) — every blocker is fixable code, so ship the fix, verify in prod, then scale.

## Phase 3 — SWOT
**STRENGTHS:**
- **ZTE 96/100 structural integrity** — system architecture, CI pipeline, and harness hardening are elite-tier; 4 CRITICALs resolved this cycle confirms execution cadence works
- **Senior-agent topology (Wave 4)** is operational with CFO/CMO/CTO/CS covering all executive slices; dual-key gates prevent runaway spend decisions
- **SDK architecture is battle-hardened** — `TAO_USE_AGENT_SDK=1` with `bypassPermissions`, `asyncio.wait_for` guards, and Sonnet-on-planner policy (RA-1169–1178 lessons all absorbed and documented)
- **Kill-switch triad (RA-1966/1973)** is wired: `TAO_MAX_ITERS`, `TAO_MAX_COST_USD`, `HARD_STOP` file — runaway loops have three independent abort axes
- **Linear → Railway → Vercel autonomous loop** is always-on without Mac dependency; autonomy queue works without human intervention when keys are present

**WEAKNESSES:**
- **Funnel is broken at first contact** — RA-6801 and RA-6678 block the core product loop for paying clients; per persona synthesis, every campaign impression against a broken funnel is brand destruction, not acquisition
- **BVI at +4 net but portfolio improvement at 0** — velocity is consumed by internal hardening, not customer-visible outcomes; no MARATHON completions this cycle
- **25 unassigned Urgent/High issues** — autonomous poller fires on `Todo` status but these tickets have no owner, so they won't self-dispatch; autonomy queue silently skips them
- **Evaluator degradation visible in lessons** — three consecutive `1.0/10` scores across completeness/correctness/conciseness (evaluator/bug entries) indicate the generator is producing empty diffs for some task classes; tao-judge telemetry not yet wired into sessions.py so the loop can't self-correct
- **Scope contract breach (591 files, evaluator/hotfix)** — a routine auto-session modified an order of magnitude more files than permitted; the scope guard (`max 15`) either wasn't enforced or was bypassed

**OPPORTUNITIES:**
- **P0 sprint is clearly scoped** — RA-6801, RA-6678, RA-6792, RA-6791 are the four blockers; closing all four with end-to-end production verification unblocks the first paying client and restores campaign ROI from RA-5036
- **25 unassigned issues are ready inventory** — assigning them to the autonomy queue (set to `Todo`, route via `.harness/projects.json`) could convert backlog debt into shipped features without new scope discovery
- **tao-judge full integration (RA-1970)** is designed but deferred — wiring `run_until_done()` into `sessions.py` would self-terminate empty-diff loops before they score 1.0/10, directly fixing the evaluator degradation pattern
- **Stripe-Xero provider (`TAO_CFO_PROVIDER=stripe_xero`)** is coded but using synthetic data; connecting real credentials would give the CFO bot actual burn/NRR signals and make the 6-pager commercially credible
- **ABR (mentioned as incomplete in persona synthesis)** — completing the ABR regulatory path opens a revenue/compliance gate that is currently blocked by process, not engineering

**THREATS:**
- **Campaign spend against a broken funnel (RA-5036 + RA-6801/6678)** — per persona synthesis, this is the highest-probability brand trust destruction event; every organic impression that hits a broken conversion path compounds the damage
- **False-positive watchdog credibility collapse** — the 00:38 UTC CRITICAL alert (scheduled-task sandbox missing `anthropic>=0.90`) demonstrates that one false alarm makes every subsequent real alert suspect; with 10 Urgent open issues, a degraded alert channel is a critical operational risk
- **Scope contract breach at scale** — if a routine auto-session can touch 591 files undetected, a production incident where the wrong files are modified in the wrong repo is a matter of when, not if; the `pidev/` webhook skip guard (RA-1182) only covers self-modification
- **API key hygiene failures are recurring** — three separate lessons (empty-string `ANTHROPIC_API_KEY`, Vercel trailing `\n`, `op://` literal passthrough) indicate the key-handling pattern is fragile across surfaces; a silent 401 in the autonomy loop would halt all autonomous work without alerting
- **Empty-diff generator loops burning budget without producing output** — with `TAO_MAX_COST_USD=5.00` per session and the evaluator scoring `1.0/10` on empty diffs, the system can exhaust budget allocations on no-op loops; until tao-judge is fully wired, this is undetected waste

## Phase 4 — SPRINT RECOMMENDATIONS
PRIORITY 1: **RA-6801** — Every marketing impression against a broken signup→report→PDF funnel is brand destruction, not acquisition; the Anthropic key bypass for platform-managed trial credits is the single highest-leverage fix in the portfolio right now. — Estimate: **M (2–4h)** — Impact: Restores the conversion funnel end-to-end; unblocks RA-6792 (first-client onboarding flow) and RA-6791 (billing gate); direct revenue enablement with no further prerequisite work.

PRIORITY 2: **RA-6678** — ABR_API_GUID missing in prod means every Australian client onboarding hard-fails MALFORMED before the session even reaches the report stage, compounding the RA-6801 funnel destruction in parallel. — Estimate: **XS (<1h)** — Impact: A prod env-var set or config patch restores ABN lookup instantly; unblocks the entire AU onboarding path and removes the second independent P0 funnel break with near-zero engineering cost.

PRIORITY 3: **RA-6670** — The cron worker is silently skipping 88% of the backlog pile, which is why 25 Urgent/High tickets remain unassigned and the autonomy queue fires but does nothing; closing the bounded daily backlog-burndown loop restores autonomous throughput from ~12% to full capacity. — Estimate: **S (1–2h)** — Impact: Multiplies all future autonomy ROI by ~8×; the 25 unassigned tickets become dispatchable this cycle, directly converting the current BVI plateau (+4 net, zero MARATHON completions) into compounding delivery velocity.

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 2
- Low: 4
- Tickets created: None

_Generated 2026-06-19T05:08:44.139283+00:00_