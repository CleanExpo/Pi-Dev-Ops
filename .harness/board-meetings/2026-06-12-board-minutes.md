# Board Meeting Minutes — Cycle 0 (2026-06-12)

## Business Velocity Index (RA-696)
**BVI: 3** (+2 from prior cycle)
- CRITICALs resolved: 3
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 1

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
- Urgent: 3 | High: 27
- Stale: None
- Unassigned: RA-6499, RA-6500, RA-6484, RA-6485, RA-6489, RA-6490, RA-6498, RA-6497, RA-6496, RA-6495, RA-6470, RA-6475, RA-6491, RA-6483, RA-6482, RA-6481, RA-6461, RA-6464, RA-6471, RA-6472, RA-6469, RA-5713, RA-5968, RA-5725, RA-5724, RA-5723, RA-5721, RA-5720, RA-5719

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
### CURRENT-CYCLE RESEARCH (fast, 155.3s)

**Finding #1** [MEDIUM] — _What pricing changes is Anthropic (Claude API) introducing around 22 June 2026 that would affect the Mythos-as-planner strategy?_
  Effective June 15 2026, all programmatic Claude usage via the Agent SDK and `claude -p` exits subscription limits and draws instead from a separate metered monthly credit ($20 Pro / $100 Max-5x / $200 Max-20x, no rollover). Anthropic's own coverage notes that Opus-heavy pipelines and recursive agents will exhaust this credit within days; Claude Fable 5 (the first publicly available Mythos-class model, launched June 9) is priced at $10/1M input tokens, and Mythos 5 itself remains limited-preview under Project Glasswing — meaning any Mythos-as-planner architecture running over the SDK now faces full API-rate metering with no subscription subsidy.
  - [Anthropic's June 15 Billing Change: What Every Claude Code & Agent SDK User Must Do](https://codersera.com/blog/anthropic-june-2026-billing-change-claude-code/) (fetched 2026-06-12)
  - [Anthropic Ends Subscription Subsidy for Agents June 15: Credit Pool Replaces Flat-Rate Access](https://www.techtimes.com/articles/317625/20260602/anthropic-ends-subscription-subsidy-agents-june-15-credit-pool-replaces-flat-rate-access.htm) (fetched 2026-06-12)
  - [Anthropic Claude API Pricing 2026 - Fable 5 $10/1M, Opus $5, Sonnet $3](https://www.aipricing.guru/anthropic-pricing/) (fetched 2026-06-12)
**Finding #2** [MEDIUM] — _What are the current WCAG 2.1 Success Criterion 1.4.4 compliance enforcement precedents or penalties relevant to Australian SaaS products?_
  Australia's Disability Discrimination Act (DDA) covers SaaS platforms explicitly; the Australian Human Rights Commission's April 2025 updated guidance sets WCAG 2.2 Level AA as the minimum standard for digital products including SaaS and AI tools. DDA non-compliance can result in complaints, conciliation, and court-awarded compensation up to AUD 100,000 per complainant, with fines reaching AUD 250,000 per violation — but no citable enforcement case specifically naming SC 1.4.4 (Resize Text) against an Australian SaaS vendor was found in available sources.
  - [Three major accessibility updates in Australia, and what they mean for your organization in 2026](https://www.deque.com/blog/accessibility-updates-in-australia-in-2026/) (fetched 2026-06-12)
  - [DDA Compliance: Web Accessibility in Australia (2026)](https://www.accessibilitychecker.org/guides/dda/) (fetched 2026-06-12)
  - [Australia Web Accessibility 2026: Updates, Laws & WCAG Compliance Guide](https://d2itechnology.com/blogs/australia-web-accessibility-2026-updates/) (fetched 2026-06-12)
**Finding #3** [MEDIUM] — _What is the current status and known issues with DigitalOcean App Platform build failures related to Node.js or monorepo configurations in 2026?_
  A confirmed 11.7-hour global App Platform outage on February 26–27 2026 was caused by failures in older Node.js buildpack versions; DigitalOcean resolved it by February 27 04:55 UTC and simultaneously changed the default Node.js version from v20 to v22 LTS. No active open incidents were found as of June 2026, but the version bump (v20→v22) is a known breaking-change vector for projects that do not pin their Node.js version in package.json.
  - [DigitalOcean App Platform Deployments — Feb 2026 | IsDown](https://isdown.app/status/digitalocean/incidents/543201-app-platform-deployments) (fetched 2026-06-12)
  - [Node.js Buildpack on App Platform | DigitalOcean Documentation](https://docs.digitalocean.com/products/app-platform/reference/buildpacks/nodejs/) (fetched 2026-06-12)
**Finding #4** [MEDIUM] — _Has Anthropic or any major AI orchestration vendor shipped changes to agent SDK behaviour or permission models in the last 30 days that affect Claude Code harnesses?_
  Claude Code v2.1.172 (shipped within the last 30 days) introduced nested sub-agents up to 5 levels deep, fixed `availableModels` restrictions not being applied to subagent model overrides and the agent-dispatch model picker, fixed background sub-agents reading another directory's project settings when dispatched on pre-warmed workers, and fixed worktree-isolated workflow agents being blocked from editing their own worktree files. v2.1.169 fixed enterprise managed MCP policies not being enforced on reconnect or before remote settings loaded. Separately, the June 15 billing change means Agent SDK calls from harnesses now draw from a capped metered credit rather than subscription limits.
  - [Claude Code Updates by Anthropic - June 2026 - Releasebot](https://releasebot.io/updates/anthropic/claude-code) (fetched 2026-06-12)
  - [Anthropic's June 15 Billing Change: What Every Claude Code & Agent SDK User Must Do](https://codersera.com/blog/anthropic-june-2026-billing-change-claude-code/) (fetched 2026-06-12)

**Open questions** (research could not resolve):
  - Specific Anthropic-published API pricing for Claude Mythos 5 tokens (input/output per MTok) — Mythos 5 is limited-preview under Project Glasswing and no public pricing sheet was found.
  - Cited Australian enforcement case or ACCC/AHRC formal determination specifically naming SC 1.4.4 (Resize Text) against a SaaS product — general penalty framework found but no SC-specific precedent.
  - Whether DigitalOcean App Platform has any active known issues with monorepo (pnpm/Yarn workspaces) build configurations as of June 2026 — only the resolved February incident was found; community forum threads exist but no confirmed current bug tracker entry.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)


## Phase 3 — SWOT
**STRENGTHS:**

- **ZTE 83–85/100 confirms near-zero-touch baseline.** Core pipeline (plan → generate → evaluate → push) runs without human steering; model-policy enforcement (RA-1099) and kill-switch topology (RA-1966: cost ceiling + hard-stop file + iter cap) are hardwired, not advisory.
- **Triage-to-fix loop is functional.** BVI +2 and 3 CRITICALs resolved in one cycle proves the autonomy queue → Railway → Linear ticket chain closes loops, not just opens them.
- **Institutional memory is accumulating with teeth.** 20 lessons, all codified into CLAUDE.md with specific rule + root cause + fix — not a changelog. Patterns like abs() debounce (scheduler lesson [HIGH]), do-while poller, and XFF trust (rate-limit WARN) are already preventing repeat failures.
- **Defensive architecture is structurally sound.** SDK locked (TAO_USE_AGENT_SDK=1 only), judge-gated loop (RA-1970), context compactor (RA-1967), and per-bot kill-switches give the orchestrator multiple abort axes before a runaway session burns budget.
- **Senior agent topology is fully specified.** CFO/CMO/CTO/CS wave (RA-1858) with dual-key gates, ledger files, and daily-brief pipeline is architecturally ready — not aspirational.

---

**WEAKNESSES:**

- **BVI absolute score of 3 is anemic.** 0 portfolio improvements, 0 MARATHON completions means the system is servicing technical debt, not delivering compounding business value. Velocity exists but isn't converting to outcomes yet.
- **29 unassigned issues + 37 open Urgent/High = backlog is outpacing resolution.** No triage or assignment means these items are invisible to the autonomy poller, which only picks up Linear `Todo` items with team routing.
- **Silent-failure modes are a recurring systemic pattern.** LINEAR_API_KEY missing → 0 sessions, health still green (lesson [HIGH]); sleep-first poller → 5-min blackout on every restart (lesson [INFO]); /health reporting "ok" while the autonomy loop is dead (lesson [INFO]). The pattern isn't one bug — it's an architectural gap: services report process-alive, not work-alive.
- **Always-on autonomy is not topologically autonomous.** Scheduled-tasks MCP runs in Cowork sandboxes that die when the Mac sleeps (lesson [INFO] "first overnight autonomous attempt failed"). Railway is the only 24/7 component; anything routed through Cowork is brittle by design.
- **Surface Treatment Prohibition (RA-1109) enforcement is policy, not a gate.** PR template requires a manual verification path, but the evaluator flags — not blocks — violations. PR #48 → fixed #56 shows the cost of late detection.

---

**OPPORTUNITIES:**

- **/health endpoint is one PR away from eliminating an entire failure class.** The fix is specified precisely: surface `linear_api_key: bool`, `autonomy.armed` boolean, and last-tick timestamp (lessons [INFO] ×2). This converts silent-failure theatre into an observable alarm.
- **Full Railway + GH Actions migration unlocks true 24/7.** The architecture is documented (`ARCHITECTURE-V2.md` referenced in lesson [INFO]). Moving scheduled tasks off Cowork removes the Mac-sleep failure mode and makes "autonomous" a topological fact, not a claim.
- **Judge-gated loop (RA-1970) + context compactor (RA-1967) enable longer autonomous runs.** Both are implemented. First MARATHON completion is within reach if the unassigned backlog is triaged and routed into the autonomy queue.
- **Stripe-Xero activation for CFO bot.** Real financial data (`TAO_CFO_PROVIDER=stripe_xero`) turns the CFO from a synthetic-data simulator into a live burn/runway/NRR monitor. The dual-key gate on spend >$1k already exists — activating real data is a credential + env var change, not an architecture change.
- **Semantic RAG memory is designed, not built.** The TurboQuant assessment (lesson [INFO]) produced a clear four-piece plan: per-project `memory/` folder, retrieval step pre-session, weekly summarization, embedding compression later. This directly addresses context-window thrash in long autonomy sessions.

---

**THREATS:**

- **Alert fatigue is eroding trust in the escalation channel.** Marathon watchdog false CRITICAL at 00:38 UTC (lesson [ERROR]) + health reporting green on a dead autonomy loop = when a real Urgent fires on Telegram, the prior track record argues against immediate response. A crying-wolf pattern on a 24/7 system is existential.
- **Railway env var drift is a recurring silent-failure vector.** ANTHROPIC_API_KEY="" inherited from claude CLI (lesson [WARN]), LINEAR_API_KEY missing post-redeploy, op:// refs not resolved by dotenv (lesson [WARN]), Vercel key with trailing \n causing 401 (lesson [WARN]). Every Railway restart is a potential silent regression with no detection until session count stays at 0 for >5 minutes.
- **ZTE v2 (83) regressed from v1 (85).** Two-point drop signals additional manual interventions required this cycle. If the trend continues across cycles, the Zero Touch claim degrades and the BVI improvement (+2) is masking increasing operator load, not decreasing it.
- **Recursive self-modification guard is a single-point check.** The 43-zombie-branch incident (hardwired lesson, push layer RA-1182) is why the webhook skips `pidev/` refs and `CleanExpo/Pi-Dev-Ops`. Any regression in that guard — a refactor of the webhook handler, a new route module — reinstates the loop. No automated test covers this invariant.
- **10 open Urgent issues with no queue assignment.** If any touch the autonomy poller, push auth, or Railway health — the three components the entire stack depends on — a single unresolved Urgent can stall all downstream MARATHON work. Priority ordering into the poller queue is currently manual.

## Phase 4 — SPRINT RECOMMENDATIONS


## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 3
- Low: 4
- Tickets created: RA-6515, RA-6516, RA-6517

_Generated 2026-06-12T05:09:09.923419+00:00_