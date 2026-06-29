# Board Meeting Minutes — Cycle 0 (2026-06-13)

## Business Velocity Index (RA-696)
**BVI: 0** (-3 from prior cycle)
- CRITICALs resolved: 0
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 3

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
### CURRENT-CYCLE RESEARCH (fast, 163.5s)

**Finding #1** [HIGH] — _What pricing changes did Anthropic announce for June 2026 that would affect the Mythos-as-planner strategy deadline of 22 June?_
  Two changes converge on the 22 June window. First, effective June 15 2026, all programmatic Claude usage (Agent SDK, claude -p, GitHub Actions) moves off the shared subscription pool onto a separate metered credit pool ($20/month Pro, $100 Max-5x, $200 Max-20x); unused credits do not roll over and heavy SDK users face 12×–150× effective cost increases. Second, Claude Mythos 5 is not available as a general API model: it remains gated exclusively to Project Glasswing partners at $25/$125 per million input/output tokens, with no public release date announced, meaning a Mythos-as-planner architecture cannot be executed through the standard API at any price prior to 22 June unless Glasswing partner access has been secured.
  - [Anthropic's June 15 Billing Change: What Every Claude Code & Agent SDK User Must Do](https://codersera.com/blog/anthropic-june-2026-billing-change-claude-code/) (fetched 2026-06-13)
  - [Project Glasswing – Anthropic](https://www.anthropic.com/project/glasswing) (fetched 2026-06-13)
  - [Anthropic's Claude Fable 5 and Mythos 5 Launch: What To Know](https://finance.yahoo.com/markets/crypto/articles/anthropic-claude-mythos-launches-today-142844796.html) (fetched 2026-06-13)
**Finding #2** [MEDIUM] — _What is the current status and timeline of ZTE's enterprise AI infrastructure offerings that could affect Pi-CEO competitive positioning?_
  At MWC Barcelona 2026 (March), ZTE unveiled a full-stack 'AI Factory' comprising AI servers with OEX architecture, the AI Agent Studio, Co-Claw enterprise AI agent, Elastic AIDC modular data-centre solution, and SuperPOD (up to 128 GPUs per rack). On June 3 2026 ZTE and Tencent announced a strategic partnership to ship an AI Cloud PC bundle running WorkBuddy; procurement pilots are expected to convert to scaled deployments by Q4 2026. No enterprise pricing has been publicly disclosed.
  - [ZTE Unveils Full-Stack AI Infrastructure, Driving Co-Design – The Register](https://www.theregister.com/2026/03/02/zte-unveils-full-stack-ai-infrastructure) (fetched 2026-06-13)
  - [ZTE, Tencent Unveil AI Cloud PC for Next-Gen Enterprises – AI CERTs News](https://www.aicerts.ai/news/zte-tencent-unveil-ai-cloud-pc-for-next-gen-enterprises/) (fetched 2026-06-13)
  - [ZTE Showcases Full-Stack AI Innovations at MWC Barcelona 2026](https://www.zte.com.cn/global/about/news/ZTE-Showcases-Full-Stack-AI-Innovations-at-MWC-Barcelona-2026-Creating-an-Intelligent-Future.html) (fetched 2026-06-13)
**Finding #3** [LOW] — _What WCAG 2.1 enforcement actions or legal precedents from 2025-2026 make the user-scalable=no viewport meta (RA-4864) an active compliance liability?_
  No court ruling or regulator filing specifically citing user-scalable=no as a named violation was found. The broader compliance liability is real but established indirectly: WCAG 2.1 SC 1.4.4 (Resize Text, Level AA) is violated by viewport meta tags that prevent scaling, the DOJ finalised mandatory WCAG 2.1 Level AA compliance under ADA Title II (public-entity deadline April 24 2026), and 5,000+ federal digital-accessibility lawsuits were filed in 2025 with courts treating WCAG Level AA failure as evidence of an ADA barrier (Fernandez v. SEB Management Group LLC, S.D. Fla., Apr. 13 2026). No settlement or injunction specifically naming the viewport meta tag was surfaced in three searches.
  - [April 2026 Accessibility Legal Update – Converge Accessibility](https://convergeaccessibility.com/2026/05/04/legal-update-april-2026/) (fetched 2026-06-13)
  - [DOJ Extends ADA Title II Website Accessibility Deadlines – ADA Title III Blog](https://www.adatitleiii.com/2026/04/doj-extends-ada-title-ii-website-accessibility-deadlines-for-governmental-entities-but-litigation-and-compliance-risks-remain/) (fetched 2026-06-13)
  - [ADA Lawsuit Statistics 2025–2026: Data & Trends – WCAGsafe](https://wcagsafe.com/blog/ada-lawsuit-statistics) (fetched 2026-06-13)
**Finding #4** [MEDIUM] — _What is the latest DigitalOcean App Platform build failure pattern for Node.js monorepos that could explain the monkfish-app CI block (RA-4188)?_
  The established failure pattern for pnpm-based Node.js monorepos on DigitalOcean App Platform is a buildpack-timing race: the Node.js buildpack v0.4.x attempts to restore cached node_modules before pnpm is installed, producing 'pnpm: executable file not found in $PATH' then 'WARN Local package.json exists, but node_modules missing' and downstream 'tsc: not found' errors. A secondary corepack compatibility issue with most heroku-buildpack-nodejs versions compounds this. DigitalOcean patched the buildpack for pnpm support but the fix requires explicit pnpm version pinning in package.json engines and disabling the build cache on first deploy.
  - [How to setup DO App Platform with pnpm monorepo – DigitalOcean Community](https://www.digitalocean.com/community/questions/how-to-setup-do-app-platform-with-pnpm-monorepo) (fetched 2026-06-13)
  - [Node.js Buildpack on App Platform – DigitalOcean Documentation](https://docs.digitalocean.com/products/app-platform/reference/buildpacks/nodejs/) (fetched 2026-06-13)

**Open questions** (research could not resolve):
  - Whether any court or regulator has issued a ruling, consent decree, or enforcement notice that specifically names the user-scalable=no (or maximum-scale=1) viewport meta attribute as a standalone WCAG 2.1 violation — no primary legal source was found in three searches.
  - Whether Anthropic intends to make Claude Mythos generally available via the standard API before or after 22 June 2026, and under what pricing structure outside Project Glasswing.
  - Whether DigitalOcean has issued a formal incident report or changelog entry for a platform-wide build regression affecting Node.js monorepos in 2025–2026 beyond the known pnpm/corepack timing issue.

_Personas: cite findings by `#N` when your position depends on a fact. The Contrarian MUST flag at least one open question or low-confidence claim._

## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)


## Phase 3 — SWOT
**SWOT — Pi-CEO · Cycle 2026-06-13**

---

**STRENGTHS**

- **Architectural integrity at 83–85 ZTE.** Core runtime (Railway BE + Vercel FE + GH Actions CI + Telegram inbound) is correctly topologised as always-on — the lesson that "autonomous is a property of topology, not cleverness" [INFO overnight autonomous] has been absorbed and encoded in ARCHITECTURE-V2.
- **Active learning loop with triage.** 20 lessons classified HIGH/WARN/ERROR/INFO, covering railway scheduler regression, rate-limit cloud-IP, XFF spoofing, op:// dotenv trap, and alert-fatigue anti-pattern. Each has a documented fix, not just an observation.
- **Safety rails are production-grade.** TAO kill switch (RA-1966, three axes), judge-gated loop (RA-1970), context compactor (RA-1967), and model-policy enforcement (RA-1099) are wired and tested. Runaway loops and Opus-leak are structurally prevented.
- **Senior agent topology scaffolded.** CFO/CMO/CTO/CS bots with dual-key gates, debate runner (RA-1867), and 6-pager dispatcher (RA-1863) are in place — intelligence-to-brief pipeline exists even if not yet firing daily.
- **Linear routing is canonical and automated.** `.harness/projects.json` + `autonomy.py` poller correctly routes work to 10 repos. The routing table is maintained and cross-referenced in CI.

---

**WEAKNESSES**

- **BVI = 0, delta –3.** Zero CRITICALs resolved, zero portfolio improvements, zero MARATHONs closed. The system is generating tickets faster than it is draining them. High ZTE with zero BVI is the definition of audit infrastructure that doesn't ship.
- **29 unassigned issues, 10 Urgent.** Assignment is the missing link between discovery and execution. `autonomy.py` will only autopick assigned issues — the queue is full and stalled at the assignment gate.
- **Silent-failure class of bugs recurs.** `LINEAR_API_KEY` missing → health green, loop dead [HIGH silent failure]; empty `ANTHROPIC_API_KEY` → 401 [WARN deployment]; `op://` refs in dotenv → None silently passed to SDK [WARN architecture]; Vercel trailing `\n` on key → 401 [WARN security]. Pattern: every integration boundary has a version of this bug. Not yet fixed systematically.
- **Mac/Cowork dependency not fully eliminated.** Scheduled-tasks MCP still runs in ephemeral Cowork sandboxes [INFO marathon-session/scheduled-tasks]. The topology lesson was written; the migration is incomplete.
- **Health endpoints still report breathing, not working.** `linear_api_key: bool` and `last_successful_tick` are prescribed [INFO /health lesson, INFO sleep-first poller] but not yet universally implemented across background loops.

---

**OPPORTUNITIES**

- **Auto-assignment closes the BVI gap immediately.** Wire auto-assignment on ticket creation using `.harness/projects.json` routing. No new infrastructure needed — `autonomy.py` already picks up assigned Urgent/High. This is the single highest-leverage action to lift BVI from zero.
- **Railway consolidation converts the system from "sophisticated cron" to genuine autonomy.** Move all remaining scheduled work off Mac onto Railway + GH Actions. The topology is documented; the migration is the bottleneck [INFO overnight autonomous].
- **Health telemetry sweep eliminates the silent-failure class.** Add `autonomy.armed`, `linear_api_key: bool`, `last_successful_tick` to every background loop in one pass. Converts the recurring HIGH/WARN lesson pattern into a detectable, alertable state [INFO /health, INFO sleep-first poller].
- **Daily 6-pager → Telegram activation.** The dispatch chain (4 ledgers + Margot insight → PII redact → voice → HITL draft) is scaffolded (RA-1863). Activating it closes the founder-visibility loop without requiring manual prompting each cycle.
- **Semantic RAG memory layer.** Per-project `memory/` folder + retrieval step before session start is designed [INFO TurboQuant lesson], 4-piece plan documented. Would reduce context waste and improve generator output quality without model changes.

---

**THREATS**

- **Second consecutive BVI=0 cycle converts tooling perception from "build engine" to "audit theatre."** If the next cycle also shows zero portfolio movement, stakeholder confidence in the autonomous loop collapses regardless of ZTE score.
- **Alert fatigue from false CRITICAL escalations.** The 00:38 UTC wolf-cry incident (46/46 tests actually green, wrong sandbox environment) [ERROR marathon watchdog] means the next real CRITICAL may be ignored. A single false positive at that severity permanently degrades alert trust.
- **Queue growth rate exceeds drain rate.** 37 open Urgent+High issues with zero BVI movement means the backlog is compounding. Without assignment automation, each cycle adds more tickets than it closes — compounding pressure, not progress.
- **Dual-key gate deadlock on async founder availability.** CFO/CTO/CS gates on spend/merge/refund require founder approval. In a fully async topology, high-confidence sub-$1k decisions stall indefinitely if the second key isn't available, directly suppressing BVI.
- **Dependency fragility is multi-layered and compounding.** Stale Vercel `rootDirectory` [ERROR sprint-12], missing CI secrets on hardcoded-fallback removal [ERROR sprint-12/security], cloudflared LaunchAgent needing exact subcommand args [WARN sprint-12/deployment] — each layer has its own silent-failure mode. The combination means a Railway redeploy + secret rotation + FE deploy in the same window can silently fail at three independent points with all health endpoints green.

## Phase 4 — SPRINT RECOMMENDATIONS
**PRIORITY 1: RA-6500 — Activate the Mac Mini node now; it's a single paste block that immediately doubles fleet execution capacity and gives BVI its first non-zero delta.**
Estimate: **XS (<1h)**
Impact: +1 active agent node; unblocks the Nexus Mesh critical path (RA-6474 stays In Progress but becomes testable end-to-end); ZTE unchanged but BVI starts moving the moment the second node claims its first ticket.

---

**PRIORITY 2: RA-6495 — Implement idle detection + auto-claim so free agents pull the next Urgent/High ticket without a human assignment step, collapsing the 29-issue assignment bottleneck that is the root cause of BVI = 0.**
Estimate: **M (2–4h)**
Impact: Structural fix to the single biggest execution gap identified in the SWOT; `autonomy.py` can drain the backlog autonomously once agents self-assign; expected BVI lift of 3–5 resolutions per 24 h cycle.

---

**PRIORITY 3: RA-6464 — Triage and restore the plaud-processor Postgres service before the app-code-over-database deployment causes irreversible data loss; this is a silent-failure class bug, the exact pattern the SWOT flags as recurring.**
Estimate: **S (1–2h)**
Impact: Eliminates a live data-safety risk; closes one instance of the silent-failure pattern (health green, service dead) that the SWOT calls out as a systemic weakness; operational health +1 critical resolved.

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 3
- Low: 4
- Tickets created: RA-6539, RA-6540, RA-6541

_Generated 2026-06-13T05:09:31.054595+00:00_