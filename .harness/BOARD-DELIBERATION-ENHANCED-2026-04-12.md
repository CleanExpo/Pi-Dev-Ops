# Board Deliberation — Pi-CEO Enhanced: Local AI Orchestration

**Date:** 2026-04-12
**Convened by:** Phill (CEO / Founder)
**Brief:** Approve Pi-CEO Enhanced roadmap — always-on local AI brain (Qwen 3 14B on Mac Mini M4 Pro 24GB), n8n visual workflow engine, Supabase vector memory, Open WebUI dashboard, intelligent Claude API routing — and generate a production build package for Linear.
**Attending:** CEO, Revenue, Product Strategist, Technical Architect, Contrarian, Compounder, Custom Oracle (Local AI Infrastructure Veteran), Market Strategist, Moonshot
**Output:** Decision memo + Linear ticket package for production build

---

## STAGE 1 — THE BRIEF

**From Phill to the board:**

> Pi-CEO is our Zero Touch Engineering platform — Second in Charge to the Organisation. It currently operates at ZTE Level 3 (60/60 leverage points), with 69 features shipped across 8 sprints, 21 MCP tools, 31 skills, and active monitoring of 10 repositories.
>
> The overnight autonomous failure (2026-04-11→12) exposed a critical topology weakness: everything depends on cloud services (Railway, Cowork sandboxes) that have single points of failure. The previous board deliberation recommended collapsing the V2 architecture to GH Actions + Railway-as-thin-state. But that still leaves us with no always-on local intelligence.
>
> Pi-CEO Enhanced proposes adding an always-on local AI brain — Qwen 3 14B (Q4_K_M quantisation, ~8GB) running on the Mac Mini M4 Pro (24GB unified memory). Combined with n8n for visual workflow orchestration, Supabase (local Docker) for Postgres + pgvector memory, Open WebUI for a visual dashboard, and Qdrant for hybrid RAG search. The local model handles triage, routing, monitoring, and the 80% of tasks that don't need frontier intelligence. The 20% that do escalate to Claude Haiku 4.5 / Sonnet 4.6 / Opus 4.6 via API.
>
> Cole Medin's open-source patterns (local-ai-packaged Docker Compose, second-brain-starter heartbeat monitoring) provide tested baselines for the Docker stack.
>
> Hardware is already purchased. All software is open-source / free tier. The 6-phase roadmap spans ~8-10 weeks.
>
> I want this running 24/7, 365 days a year. I want the board to decide: is this the right architecture, is the sequencing correct, and what does the Linear ticket package look like to build it into production?

---

## STAGE 2 — CEO FRAMES

**The Real Question:** *Should we commit to a local-first AI orchestration layer on the Mac Mini as the permanent always-on brain of the business, and if so, what is the minimum viable deployment that gives us 24/7 autonomy without repeating the topology failures we just experienced?*

**Where we'll disagree:**

- **Local vs. cloud reliability** — a Mac Mini in Phill's office is a single physical machine. Power outage, macOS update, disk failure, and the entire "always-on" promise dies. Is local-first actually more reliable than cloud-first, or are we trading one fragility for another?
- **Scope discipline vs. full vision** — the board paper describes 6 phases over 8-10 weeks with n8n, Supabase, Open WebUI, Qdrant, Telegram, Gmail, Google Drive, Claude routing. That's a lot of moving parts for a one-person operation that just had its first overnight attempt fail. Should we ship all six phases or ruthlessly cut to the minimum that delivers 24/7 autonomy?
- **Qwen 3 14B as orchestrator vs. dumb router** — is a 14B local model actually good enough to make triage decisions, classify intent, and route to the right Claude tier? Or will it introduce a new failure mode where the local model makes bad routing decisions and the system silently degrades?

**Debate parameters:**

1. Non-negotiable: the system must run 24/7/365 without requiring Phill to be awake, at his desk, or manually intervening for routine operations.
2. Non-negotiable: the overnight failure's root causes (unpushed commits, sandbox-dependent scheduling, false-positive watchdog) must not be reproducible in the new architecture.
3. Up for challenge: whether all six phases are needed, whether n8n is the right workflow engine, whether Qdrant is necessary alongside Supabase pgvector, and whether Open WebUI adds value or complexity.
4. Up for challenge: the Cole Medin Docker Compose baseline — is it production-grade or a YouTube demo?
5. What I need from the debate: a ranked phase list with clear go/no-go gates, a realistic timeline, and the exact Linear tickets to start building Monday.

---

## STAGE 3 — BOARD DEBATES

### ROUND 1 — Opening Positions

**Revenue:**
The commercial case for Pi-CEO Enhanced is straightforward: every hour the portfolio operates without autonomous monitoring is an hour where CCW's 196 high-severity findings, RestoreAssist's production downtime (now 76h+), and DR-NRPG's missed content deadlines compound silently. The overnight failure cost us the DR-529 NSW/QLD storms deadline and nearly cost us DR-528 Alfred (AU$1.877bn PERILS media peak). Local-first means the monitoring never sleeps even if Railway goes down or Cowork sandboxes die. But I need to see the unit economics: Qwen 3 14B running 24/7 on a Mac Mini costs electricity and depreciation — roughly $15-20/month all-in. Compare that to the Claude API costs for doing the same triage work: at Haiku rates, 24/7 polling would run $50-100/month depending on volume. The local model pays for itself in month one. I support the architecture. I want Phase 1 and Phase 2 shipped fast, and Phases 3-6 gated on demonstrated value from the first two.

**Product Strategist:**
The user is Phill. On Tuesday morning, success looks like: Phill opens Open WebUI on his phone or laptop, sees a dashboard showing what happened overnight across all 10 repos, which Linear tickets moved, which builds shipped, and what needs his attention — without reading 18 Slack heartbeat messages. That's the product. The current fleet (Scout, SPM, CTO, Orchestrator, CFO heartbeats) is generating enormous signal but it's buried in a Slack channel that Phill isn't reading fast enough. The Slack pull we just did showed 18 messages with zero Phill responses across 10+ hours. The product problem isn't "we need more AI" — it's "we need a single pane of glass." Open WebUI as a dashboard is the highest-value component in this entire proposal. I'd promote it from Phase 5 to Phase 1.

**Technical Architect:**
The architecture is sound in principle but has four engineering concerns. First: Docker on macOS uses Virtualization.framework, which adds overhead. The paper correctly notes Ollama runs natively (not in Docker) — good. But n8n + Supabase + Open WebUI + Qdrant in Docker on a 24GB Mac Mini is four containers competing for the remaining 16GB after Qwen claims 8GB. With macOS overhead (~4GB), that leaves ~4GB for all containers plus KV cache headroom. The paper says "comfortably satisfied" — I say it's tight under concurrent load. Second: Qdrant alongside Supabase pgvector is redundant for a single-user system. pgvector handles both semantic and keyword search. Drop Qdrant, save ~1-2GB of RAM and one container to maintain. Third: n8n is a solid workflow engine but it's another service to keep running. If the goal is "cron jobs + webhooks + conditional logic," a simple Python script with APScheduler does the same thing with zero Docker overhead. n8n's value is the visual editor — worth it only if Phill will actually use the visual editor. Fourth: the Mac Mini needs a UPS and an auto-restart-on-power-failure setting. Without those, "24/7/365" is a marketing claim, not an engineering reality.

**Market Strategist:**
The competitive landscape has shifted significantly in the last 90 days. Anthropic shipped Claude Code with hooks and scheduled tasks. Google shipped Gemma 4 and Qwen 3 is now competitive at 14B. Cole Medin's local-ai-packaged has 15K+ GitHub stars and a growing community. The pattern of "local model for triage + cloud API for heavy lifting" is becoming the standard architecture for solo operators and small teams. Phill is not building something novel — he's adopting a proven pattern. That's good. It means the risk is execution, not architecture. The market timing is right: local models crossed the "good enough for routing" threshold in Q1 2026. The strategic question is whether Phill positions Pi-CEO as a portfolio operator's toolkit (internal tool) or as a product others could use (external). For now, internal is the right call — but the architecture should be clean enough that productising later is possible, not impossible.

**Compounder:**
Everything in this proposal compounds except Qdrant (redundant with pgvector) and the Gmail/Google Drive integrations (Phase 2, nice-to-have, not compounding). What compounds: Supabase as the memory layer — every session, every decision, every lesson gets stored and retrieved, and the retrieval gets better as the corpus grows. The Qwen routing layer — every routing decision teaches us which tasks need Haiku vs. Sonnet vs. Opus, and over time the routing logic tightens and API costs drop. The n8n workflows — every workflow Phill builds is reusable across all portfolio businesses, and the library of workflows becomes an asset. The Open WebUI dashboard — every view Phill creates reduces his daily cognitive load permanently. I'd rank the phases by compounding value: Supabase memory > Qwen routing > n8n workflows > Open WebUI dashboard > integrations > research automation. That's a different order from the paper.

**Moonshot:**
Everyone is debating infrastructure. I want to ask the 10x question: what if the Mac Mini isn't just Phill's assistant — what if it's Phill's replacement for 80% of his current workload? The board paper frames Qwen 3 14B as a "router." That's thinking too small. A 14B model running locally with full access to Supabase memory, all Linear state, all repo scan results, and all business context can make decisions, not just route them. "Should we merge this PR?" — the local model has the scan results, the charter, the deadline, and the ACL compliance status. It can make that call. "Should we escalate to Phill?" — the local model knows Phill's action queue, his response patterns, and the urgency score. It can decide. The moonshot isn't "local model routes to cloud" — it's "local model runs the business, cloud model handles the exceptions." That reframes the entire Phase 3 routing layer from "intent classifier" to "autonomous decision engine with human escalation." If we build it that way from the start, Phase 6 (continuous research) becomes the local model proactively researching opportunities, not just monitoring.

**Custom Oracle (Local AI Infrastructure Veteran — senior ML engineer who has deployed local LLMs in production at three companies):**
Three patterns from deploying local LLMs that this proposal needs to absorb. One: Ollama is great for development but has no built-in health monitoring. If the Ollama process crashes at 3am, nothing restarts it unless you configure launchd (macOS) or a supervisor process. The paper doesn't mention this. You need a heartbeat check on Ollama itself — not just on the model responses. Two: Q4_K_M quantisation at 14B is the sweet spot for 24GB, confirmed. But KV cache grows with context length. If Qwen 3 14B is processing a 32K context window (which it will, when ingesting scan results + charters + Linear state), the KV cache can spike to 2-4GB temporarily. That eats into the "headroom" the paper claims. Set the Ollama context window to 8192 for routine triage and only expand for specific tasks. Three: the Docker Compose stack should use restart: always on every container and the Mac Mini should be configured with "Start up automatically after a power failure" in System Settings > Energy. Without both, "24/7/365" is aspirational. Cole Medin's template includes restart policies — use them.

**Contrarian:**
Three assumptions in this room that nobody has questioned.

*Assumption one, shared by everyone:* that running AI locally on a Mac Mini in Phill's office is more reliable than cloud services. It isn't — not inherently. A Mac Mini has no redundancy, no failover, no SLA. Railway has 99.9% uptime SLA. GitHub Actions has 99.9%. The Mac Mini has "whatever happens to Phill's power and internet." The overnight failure wasn't caused by Railway being unreliable — it was caused by unpushed commits and missing env vars. Those are operator errors, not infrastructure failures. A Mac Mini doesn't fix operator errors. If Phill forgets to configure Ollama's context window, or forgets to set restart: always, or forgets to plug in the UPS — same failure mode, different address.

*Assumption two, shared by Revenue and Compounder:* that the local model "pays for itself" by displacing Claude API costs. The real cost of a local model isn't electricity — it's Phill's time maintaining it. Ollama updates, Docker updates, macOS updates, model weight updates, n8n workflow debugging, Supabase schema migrations. Every hour Phill spends maintaining local infrastructure is an hour not spent on CCW revenue, RestoreAssist NIR compliance, or DR-NRPG content deadlines. The opportunity cost of local infra for a solo founder is enormous and nobody has priced it.

*Assumption three, shared by Moonshot:* that a 14B model can make business decisions. It can't. It can classify, it can route, it can summarise, it can draft. It cannot judge whether merging a PR is commercially safe, whether an ACL compliance gap is legally material, or whether a deadline should be extended. Those are judgment calls that require the kind of reasoning only frontier models (or humans) provide. Framing Qwen 3 14B as a "decision engine" is a recipe for silent failures where the local model confidently makes the wrong call and nobody catches it because the whole point was that Phill is asleep.

And one more: the paper lists "ZTE Score 60/60" and "fully operational." We just spent an entire board session documenting that autonomy.py is dead, 8 security items are frozen, RestoreAssist PROD is down 76h+, and the Slack fleet has been screaming into a void for 10+ hours. A 60/60 score that coexists with that reality is a vanity metric. Fix the scoring before building on top of it.

---

### ROUND 2 — Cross-Examination

**Contrarian, pressing Technical Architect:**
> You said Docker on macOS adds overhead and the memory budget is "tight under concurrent load." But you also support the architecture. If the memory budget is tight, why not kill Docker entirely? Ollama runs natively. Supabase can be a managed instance (Supabase cloud free tier). n8n can be a managed instance (n8n cloud free tier). Open WebUI can run as a native Python process. Why are we Dockerising anything on a 24GB machine?

**Technical Architect (responding):**
Good push. The honest answer is: Docker Compose is convenient for deployment and Cole Medin's template is tested. But you're right that on a 24GB machine, every container matters. Here's my revised position: Ollama runs natively (already planned). Supabase should start as the cloud free tier — it gives us Postgres + pgvector + auth with zero local RAM cost, and we can migrate to local Docker later if we hit the free tier limits. n8n should run as a local Docker container because its workflow state needs to persist locally and its webhook handling is the core scheduler — this is the one container worth the RAM. Open WebUI can be deferred to Phase 3+ or run as a lightweight local process. Net result: we go from four containers to one (n8n), plus Ollama native, plus Supabase cloud. Memory budget goes from "tight" to "comfortable."

**Contrarian, pressing Moonshot:**
> You said the local model should be an "autonomous decision engine." Give me one specific example of a decision the 14B model would make autonomously that wouldn't be better made by Claude Opus with full context. And tell me what happens when the 14B model gets it wrong at 3am.

**Moonshot (responding):**
Fair challenge. The specific example: "Should this Linear ticket be promoted from Backlog to Todo based on the latest scan results?" That's a classification task with structured inputs (scan severity, charter priority, deadline proximity, dependency status). A 14B model with the right context window handles this correctly 95%+ of the time. Claude Opus would be better — but at 100x the cost per decision, and with API latency that makes real-time polling impractical for 5-minute cycles. When the 14B model gets it wrong at 3am: the ticket stays in Backlog until the next human review, or gets promoted when it shouldn't and a reviewer catches it in the morning. The blast radius is small because the local model promotes tickets — it doesn't merge PRs or deploy code. I'll concede the Contrarian's point that "autonomous decision engine" was too strong. "Autonomous triage engine with human-gated execution" is the right framing.

**Contrarian, pressing Revenue:**
> You said the local model pays for itself in month one. But you didn't price Phill's time. If Phill spends 10 hours setting up and 2 hours/week maintaining the local stack, at even a modest $100/hour opportunity cost, that's $1,000 setup + $400/month. The Claude API savings you quoted were $30-80/month. The local stack is underwater for the first year. Where's the real ROI?

**Revenue (responding):**
You're right that I didn't price Phill's time, and that's a material omission. Let me revise. The direct API cost savings are real but modest — ~$50/month at current volumes. The actual ROI isn't in API savings. It's in avoided losses: the DR-529 missed deadline had a recoverable but real SEO cost. The 76h+ RestoreAssist downtime has a direct revenue impact. The 10+ hours of Slack heartbeats going unread while Phill slept means the fleet was shouting into the void. If the local brain catches even one of those situations per month and takes autonomous triage action (escalating to Telegram, promoting a ticket, triggering a build), the ROI is positive in month one. The framing should be "avoided loss from faster triage" not "API cost savings." I concede the cost savings framing was weak.

**Product Strategist, adding unprompted:**
The Contrarian's point about Phill's time is the most important thing said in this debate. Phill is not a systems engineer. He's told us explicitly: "I am not a Coding Engineer, and don't plan on studying to become one." Every piece of this architecture that requires Phill to maintain it is a liability, not an asset. The setup must be a one-time event. The maintenance must be zero-touch. If n8n breaks, it should self-restart. If Ollama crashes, launchd restarts it. If the Mac Mini loses power, it reboots and everything comes back automatically. If any component requires Phill to SSH in, read logs, or debug Docker — we've failed. The architecture must be self-healing or it's the same failure mode we just experienced, just on different hardware.

**Custom Oracle, responding:**
Product Strategist is exactly right, and this is the pattern I've seen work: a one-time setup script that configures launchd agents for Ollama, Docker Compose with restart: always for all containers, macOS Energy Settings for auto-restart, and a single health-check endpoint that the Telegram bot pings every 5 minutes. If the health check fails, Telegram alerts Phill. If Phill doesn't respond in 30 minutes, the system attempts self-recovery (restart Docker, restart Ollama). If self-recovery fails, it sends a CRITICAL alert. This is a 2-hour setup, not a 2-hour-per-week maintenance burden. The Contrarian's time cost drops from $400/month to ~$50/month (occasional updates, roughly quarterly).

**Compounder, responding:**
I want to reinforce the Custom Oracle's point with a compounding lens. The setup script itself is a compounding asset — once written, it works for every future Mac Mini, every future model swap (Qwen 4 replaces Qwen 3, just change the model name), every future service addition. The maintenance burden doesn't grow linearly with features because the self-healing layer handles restarts uniformly. This is the infrastructure-as-code pattern that compounds.

---

### ROUND 3 — Revised Positions

**Revenue:**
Revised position: the ROI case is "avoided losses from faster autonomous triage," not "API cost savings." The local brain is commercially justified if it prevents one missed deadline or catches one production outage per month. Phase 1 should ship within 7 days. Phase 2 within 14. Gate Phase 3+ on demonstrated value. The strongest counter-argument — Phill's time cost — is mitigated by the self-healing setup pattern the Custom Oracle described. I hold this position.

**Product Strategist:**
Revised position: Open WebUI dashboard should be Phase 2, not Phase 5. The single-pane-of-glass that replaces 18 unread Slack heartbeats is the product Phill actually needs. Phase 1 is the infrastructure (Ollama + n8n + Supabase cloud). Phase 2 is the interface (Open WebUI + Telegram integration). Phase 3 is the intelligence (Claude routing + memory/RAG). The strongest counter-argument is that this delays the routing layer — but Phill can't use routing intelligence he can't see. I hold this position.

**Technical Architect:**
Revised position: Docker footprint should be minimised. Ollama native. Supabase cloud (free tier). n8n as the single Docker container. Open WebUI deferred or run as a lightweight local process. Drop Qdrant entirely — pgvector in Supabase cloud handles vector search. The strongest counter-argument is that Supabase cloud introduces an external dependency — true, but it's a managed service with 99.9% uptime and automatic backups, which is strictly better than a self-hosted Postgres in Docker on a Mac Mini with no backup strategy. I hold this position and I'll add: the Mac Mini needs macOS Energy Settings configured for auto-restart, a UPS (even a basic one), and launchd agents for Ollama. These are Phase 0 prerequisites, not Phase 1 tasks.

**Market Strategist:**
Revised position: the architecture is market-standard for 2026 solo operators. The risk is execution, not design. The one competitive insight worth adding: n8n has become the de facto workflow engine for the local AI community, which means community-contributed workflow templates are available for common patterns (Linear polling, Telegram bots, health monitoring). Leverage them instead of building from scratch. The strongest counter-argument is that "market standard" means "not differentiated" — true, but differentiation comes from the portfolio coordination layer (charters, Pi-CEO Standard, business-specific memory), not from the infrastructure layer. I hold this position.

**Compounder:**
Revised position: rank by compounding value. Memory layer (Supabase + RAG) compounds fastest. Routing intelligence compounds second. Workflow library (n8n) compounds third. Dashboard (Open WebUI) compounds fourth. Drop Qdrant. Defer Gmail/Drive integrations. The strongest counter-argument is that the Product Strategist wants the dashboard earlier — and I concede that visibility enables compounding by letting Phill see what's working and double down. Move the dashboard to Phase 2. I've adjusted.

**Moonshot:**
Revised position: "autonomous triage engine with human-gated execution" is the right frame for V1. The 10x version — where the local model makes business decisions — is the Phase 4+ aspiration, gated on demonstrated accuracy of the triage layer. The strongest counter-argument is the Contrarian's point that a 14B model lacks the judgment for commercial decisions. I concede this for V1. But I maintain that by Phase 4, with 3 months of triage data + business memory in Supabase, the local model will have enough context to make increasingly autonomous decisions. The architecture should be designed to enable that upgrade path, even if V1 doesn't exercise it.

**Custom Oracle:**
Revised position: the one-time setup script is the single most important deliverable in Phase 0. It should configure: macOS auto-restart on power failure, launchd agents for Ollama (with health check and auto-restart), Docker Compose with restart: always for n8n (and later containers), a /health endpoint aggregating all service statuses, a Telegram health-check ping every 5 minutes with self-recovery logic. Without this script, "24/7/365" is a promise. With it, it's an engineering reality. The strongest counter-argument is that launchd configuration is fiddly on macOS — true, but it's a one-time cost and the Custom Oracle has done it at three companies. I hold this position.

**Contrarian:**
Revised position: I still believe the board is overestimating the reliability improvement from local-first. But I concede three things. One: the self-healing setup pattern (launchd + restart: always + health-check + Telegram alerting) meaningfully addresses the maintenance cost concern. Two: the "avoided losses" ROI framing is stronger than "API savings." Three: the Technical Architect's revised footprint (Ollama native + Supabase cloud + n8n Docker only) is dramatically simpler than the original 5-container proposal. My remaining objection is scope: six phases is still too many. Commit to Phase 0 (self-healing setup) + Phase 1 (Ollama + n8n + Supabase cloud) + Phase 2 (Telegram integration + Open WebUI). Call that the MVP. Gate everything else on 14 days of clean operation. If the Mac Mini can't run for 14 consecutive days without Phill intervening, the remaining phases are built on sand.

And I'll repeat: fix the ZTE scoring. A platform that reports 60/60 while autonomy.py is dead and RestoreAssist PROD is down 76h+ is a platform that lies to its owner. That's worse than no score at all.

---

## STAGE 4 — CONSTRAINT CHECK

**Technical Architect:**

*Feasibility verdict:* The revised architecture (Ollama native + Supabase cloud free tier + n8n Docker + Open WebUI deferred to Phase 2) is feasible on the Mac Mini M4 Pro 24GB. Memory budget: Qwen 3 14B ~8GB + macOS ~4GB + n8n Docker ~0.5GB + KV cache headroom ~3GB = ~15.5GB used, ~8.5GB free. Comfortable.

*Timeline reality:*
- Phase 0 (self-healing setup): 1 day. macOS energy settings, launchd agents, UPS, health-check script.
- Phase 1 (Ollama + n8n + Supabase cloud): 3-5 days. Install Ollama, pull Qwen 3 14B, configure n8n with Linear polling + Telegram webhook workflows, connect to Supabase cloud project.
- Phase 2 (Open WebUI + Telegram integration): 3-5 days. Install Open WebUI, configure as dashboard, wire Telegram bot to local model for command interface.
- Phase 3 (Claude API routing): 3-5 days. Intent classifier prompt on Qwen 3 14B, n8n routing logic, cost tracking.
- Total MVP (Phases 0-2): 7-11 days. Total with routing (Phase 0-3): 10-16 days.

*Fatal constraints:* None for Phases 0-2. One caution for Phase 3: the Claude API routing logic must have a fallback — if Qwen 3 14B's classification is uncertain (confidence below threshold), default to Sonnet 4.6 (the safe middle), never to Haiku. Misrouting a complex task to Haiku is worse than overspending on Sonnet.

*Dependencies:*
- Supabase cloud project must be created (free tier, 5 minutes).
- Ollama must be installed on Mac Mini (brew install, 2 minutes).
- n8n Docker container needs port 5678 exposed for the workflow editor.
- Telegram bot token (@piceoagent_bot) already exists — reuse it.
- UPS must be purchased or confirmed present.

**Revenue:**

*Commercial viability verdict:* Infrastructure cost is near-zero. Supabase free tier: $0/month. Ollama: $0. n8n self-hosted: $0. Docker: $0. Electricity: ~$5-10/month for Mac Mini running 24/7. Total: ~$10/month.

*Payback period:* The architecture pays for itself if it prevents one missed deadline per month. Based on the overnight incident (DR-529 missed, DR-528 nearly missed, RestoreAssist down 76h+), the current system is missing multiple deadlines per week. Even a 50% improvement in autonomous triage justifies the investment.

*Success metric for 14-day gate:* The Mac Mini local brain must autonomously triage at least 10 Linear ticket state changes (Backlog → Todo promotions, priority re-rankings, deadline alerts) and deliver at least 1 Telegram escalation that Phill acts on within 2 hours. If it can't do that in 14 days, Phase 3+ is deferred.

**Fatal constraints raised:** None. One prerequisite: UPS for the Mac Mini (without it, "24/7/365" is not achievable). Estimated cost: $80-150 AUD for a basic unit.

---

## STAGE 5 — FINAL STATEMENTS

**Revenue:** Ship Phase 0-2 in 11 days, gate Phase 3+ on the 14-day clean-operation metric, and measure ROI in avoided losses — not API savings.

**Product Strategist:** The product is the single-pane-of-glass dashboard that replaces 18 unread Slack heartbeats — everything else is infrastructure that enables that view.

**Technical Architect:** Ollama native, Supabase cloud, n8n Docker only, drop Qdrant, add a UPS and launchd self-healing — that's the architecture, everything else is scope creep until the MVP proves itself.

**Market Strategist:** The architecture is market-standard for 2026, the timing is right, and differentiation comes from the portfolio coordination layer — not from the infrastructure — so ship the infra fast and invest in the intelligence on top.

**Compounder:** Memory compounds fastest, routing second, workflows third, dashboard fourth — build in that order within each phase and every week the system gets smarter.

**Moonshot:** Build the triage engine now, but architect it as a decision engine that grows into autonomous business operations by Phase 4 — the 10x version is a local model that runs the business with human exception handling.

**Custom Oracle:** The Phase 0 self-healing setup script is the difference between "24/7/365" as marketing and as engineering reality — ship it before touching anything else.

**Contrarian:** Commit to Phase 0-2 only, gate everything else on 14 days of uninterrupted operation, and fix the ZTE scoring so the platform stops lying about its own health.

---

## STAGE 6 — THE MEMO

```
═══════════════════════════════════════════════════════════════
THE MEMO
Date: 2026-04-12
From: CEO (Pi-CEO Board, synthesising nine perspectives)
To: Phill
Re: Pi-CEO Enhanced — should we build a local always-on AI brain
    on the Mac Mini, and what goes into Linear on Monday?
═══════════════════════════════════════════════════════════════

DECISION

Approved. Build Pi-CEO Enhanced in three committed phases (0, 1, 2)
targeting a 11-day delivery to MVP. Phase 0 is the self-healing
infrastructure layer (1 day). Phase 1 is Ollama + Qwen 3 14B + n8n
+ Supabase cloud (5 days). Phase 2 is Open WebUI dashboard +
Telegram command interface (5 days). Phases 3-6 are approved in
principle but gated on a 14-day clean-operation metric: the Mac
Mini must run for 14 consecutive days without manual intervention
before we invest further. Architecture: Ollama native (not Docker),
Supabase cloud free tier (not local Docker), n8n as the sole Docker
container, Qdrant dropped entirely. UPS required before Phase 1
begins.

RATIONALE

The overnight failure proved that cloud-dependent scheduling is
fragile when it depends on a human to push commits, set env vars,
or keep a laptop awake. The previous board recommended GH Actions
as the scheduler — and that recommendation stands for CI/CD and
test-truth. But GH Actions cannot run a 24/7 monitoring brain with
local memory and sub-minute response times. The Mac Mini fills that
gap. It is not a replacement for Railway or GH Actions — it is the
third leg of the stool: Railway for deployment, GH Actions for
test-truth, Mac Mini for always-on intelligence.

The board's strongest consensus was on scope discipline. The
original 6-phase, 8-10 week roadmap was unanimously judged too
broad for a solo founder who just experienced a catastrophic
overnight failure. The revised plan commits to 3 phases in 11 days,
with a hard gate before expanding. The Technical Architect's
revised footprint (Ollama native + Supabase cloud + n8n Docker
only) won universal support because it reduces the Docker memory
footprint from ~4GB (four containers) to ~0.5GB (one container)
while maintaining all critical capabilities.

The Contrarian's most valuable contribution was forcing the board
to price Phill's time. The resolution: a Phase 0 self-healing
setup script that configures launchd auto-restart, Docker restart
policies, macOS power settings, and a health-check Telegram
alerter. This converts "2 hours/week maintenance" into "quarterly
update check." Without Phase 0, the rest of the architecture is
built on the same human-dependency that caused the overnight
failure.

THE DISSENT THAT ALMOST CHANGED MY MIND

The Contrarian's argument that local-first doesn't inherently solve
the reliability problem came closest to blocking this decision. The
overnight failure was caused by operator errors (unpushed commits,
missing env vars), not infrastructure failures. A Mac Mini doesn't
fix operator errors. What swung me: the self-healing setup pattern
(Phase 0) specifically addresses operator dependency. If the Mac
Mini reboots after a power failure and everything comes back
automatically — Ollama, n8n, health checks, Telegram alerts — then
the operator dependency is genuinely reduced, not just relocated.
The Contrarian's concern is preserved as the 14-day gate: if the
system can't run for 14 days unattended, the operator dependency
hasn't been solved and we stop building.

The second-closest dissent: the Contrarian's point that ZTE 60/60
is a vanity metric while autonomy.py is dead and RestoreAssist is
down 76h+. This is correct and requires action. The ZTE scoring
methodology must be revised to include operational health checks
(not just feature completeness) before the next board review.

WHAT WOULD CHANGE THIS DECISION

1. If the Mac Mini cannot run for 14 consecutive days without Phill
   manually restarting a service, rebooting the machine, or fixing
   a configuration — Phase 3+ is cancelled and we fall back to the
   GH-Actions-only architecture from the previous board decision.

2. If Qwen 3 14B's triage accuracy (measured by "tickets correctly
   promoted" vs. "tickets incorrectly promoted or missed") falls
   below 80% over the first 14 days — the local model is demoted
   to a pure router (no triage decisions) and all triage moves to
   Claude Haiku via API.

3. If Supabase cloud free tier hits rate limits or storage limits
   before Phase 3 — migrate to local Docker Supabase at that point,
   not before. Don't pre-optimise for a problem we don't have yet.

NEXT ACTIONS

1. Phase 0 — Self-Healing Setup (Day 1, Monday Apr 13)
   Owner: Pi-CEO autonomous session
   Done when: Mac Mini auto-restarts after simulated power cycle,
   Ollama is running via launchd, n8n Docker has restart: always,
   /health endpoint returns 200, Telegram health-check ping
   is arriving every 5 minutes.

2. Phase 1 — Local Brain Online (Days 2-6, Tue Apr 14 - Sat Apr 18)
   Owner: Pi-CEO autonomous session + Phill for Mac Mini access
   Done when: Qwen 3 14B responds to prompts via Ollama API,
   n8n has a Linear polling workflow running on 5-min cron,
   Supabase cloud project has the memory schema deployed,
   first autonomous triage event is logged.

3. Phase 2 — Dashboard + Command Interface (Days 7-11, Sun Apr 19 - Thu Apr 23)
   Owner: Pi-CEO autonomous session + Phill for Open WebUI config
   Done when: Open WebUI shows a portfolio health dashboard,
   Telegram /status command returns live system health,
   Phill can see overnight activity in a single view without
   reading Slack.

RISK TO WATCH

The single most dangerous assumption is that Qwen 3 14B at Q4_K_M
quantisation is "good enough" for autonomous triage. The model has
not been tested against Pi-CEO's specific triage logic (charter
priorities, scan severity mapping, deadline proximity scoring). If
the model hallucinates priority levels, misclassifies severity, or
fails to escalate when it should — the system will silently
underperform and Phill won't know until a deadline is missed. The
mitigation: every triage decision in the first 14 days must be
logged with the model's reasoning, and Phill must review the log
daily for the first week. Automation of the review can happen in
Phase 3.

═══════════════════════════════════════════════════════════════
```

---

## LINEAR TICKET PACKAGE

Below are the exact tickets to be filed in Linear, organised by phase, with title, description, priority, and acceptance criteria.

### Phase 0 — Self-Healing Setup (1 day)

**ENH-001: Configure Mac Mini auto-restart on power failure**
Priority: Urgent
Description: System Settings > Energy > "Start up automatically after a power failure" enabled. Verify by simulating power cycle (unplug and replug).
Acceptance: Mac Mini boots to login screen automatically after power loss. No manual intervention required.

**ENH-002: Install and configure Ollama with launchd auto-restart**
Priority: Urgent
Description: Install Ollama via Homebrew. Pull Qwen 3 14B Q4_K_M model. Create a launchd plist that starts Ollama on boot and restarts it if it crashes. Set default context window to 8192 tokens (expandable per-task).
Acceptance: `ollama run qwen3:14b` responds after a fresh reboot. launchd restarts Ollama within 30 seconds of a kill -9.

**ENH-003: Deploy n8n Docker container with restart policy**
Priority: Urgent
Description: Docker Compose file with n8n service, restart: always, port 5678 exposed, persistent volume for workflow data. Based on Cole Medin's local-ai-packaged template (stripped to n8n only).
Acceptance: n8n UI accessible at localhost:5678 after Docker restart. Workflows persist across container restarts.

**ENH-004: Create /health aggregation endpoint + Telegram health-check ping**
Priority: Urgent
Description: A lightweight health-check script (Python or shell) that pings Ollama API, n8n API, and Supabase cloud. Runs every 5 minutes via launchd. Reports to Telegram @piceoagent_bot. Self-recovery: if Ollama or n8n is down, attempt restart before alerting.
Acceptance: Telegram receives health status every 5 minutes. If Ollama is killed, Telegram reports the outage within 5 minutes and confirms auto-recovery.

**ENH-005: Purchase/confirm UPS for Mac Mini**
Priority: Urgent
Description: Confirm UPS is present or purchase a basic unit (APC BE425M or equivalent, ~$80-150 AUD). Connect Mac Mini + router to UPS. Test: pull wall power, confirm Mac Mini stays on for at least 10 minutes.
Acceptance: Mac Mini survives a 5-minute power outage without rebooting. Phill-gated (physical purchase).

### Phase 1 — Local Brain Online (5 days)

**ENH-006: Create Supabase cloud project for Pi-CEO memory**
Priority: High
Description: Create a Supabase project (free tier). Deploy schema: sessions table, lessons table, triage_log table, memory_embeddings table with pgvector extension enabled. Connect n8n to Supabase via Postgres credentials.
Acceptance: n8n can write to and read from all four tables. pgvector similarity search returns results on test embeddings.

**ENH-007: Build n8n Linear polling workflow (5-min cron)**
Priority: High
Description: n8n workflow that polls Linear API every 5 minutes for all Pi-Dev-Ops, DR-NRPG, CCW, and RestoreAssist teams. Detects new issues, status changes, and approaching deadlines. Writes state delta to Supabase triage_log.
Acceptance: New Linear issue created → detected by n8n within 5 minutes → logged in Supabase with timestamp and delta.

**ENH-008: Build Qwen 3 14B triage prompt + n8n integration**
Priority: High
Description: System prompt for Qwen 3 14B that takes a Linear state delta as input and outputs: (a) priority classification (P0/P1/P2/P3), (b) recommended action (escalate/monitor/defer), (c) reasoning. n8n workflow calls Ollama API with this prompt for each state delta.
Acceptance: Given a test Linear delta (new Urgent security finding), Qwen 3 14B correctly classifies as P0, recommends escalate, provides coherent reasoning. Response logged in Supabase.

**ENH-009: Build n8n Telegram escalation workflow**
Priority: High
Description: n8n workflow triggered by Qwen triage output. If priority = P0 or recommended_action = escalate, send formatted message to Telegram @piceoagent_bot with issue details, reasoning, and suggested action. Include a "snooze 1h" and "acknowledge" inline button.
Acceptance: P0 triage event → Telegram message within 60 seconds with correct formatting and inline buttons.

**ENH-010: Migrate heartbeat crons from Cowork scheduled-tasks to n8n**
Priority: High
Description: Replicate the SPM, CTO, Scout, Orchestrator, and CFO heartbeat cron schedules in n8n. Each heartbeat becomes an n8n workflow triggered on its existing schedule. Heartbeats call Claude API (existing prompts) and post to Slack #general and Telegram.
Acceptance: All five heartbeat types fire on schedule from n8n. Slack and Telegram receive heartbeats. Cowork scheduled-tasks for heartbeats can be disabled.

### Phase 2 — Dashboard + Command Interface (5 days)

**ENH-011: Install and configure Open WebUI**
Priority: High
Description: Install Open WebUI (Docker or native Python). Connect to Ollama as the backend model provider. Configure with Pi-CEO system prompt. Enable API access for n8n integration.
Acceptance: Open WebUI accessible at localhost:3000. Chat with Qwen 3 14B works. System prompt loaded.

**ENH-012: Build portfolio health dashboard view in Open WebUI**
Priority: High
Description: Open WebUI custom page or n8n-generated HTML dashboard showing: (a) all monitored repos with latest scan status, (b) Linear board state (Todo/In Progress/Done counts per team), (c) active deadlines with countdown, (d) last heartbeat timestamps, (e) triage log from last 24h. Auto-refreshes every 5 minutes. Data sourced from Supabase.
Acceptance: Phill opens dashboard at 7am → sees overnight activity in a single view → can identify what needs his attention without reading Slack.

**ENH-013: Build Telegram command interface**
Priority: High
Description: Telegram bot commands via n8n webhook: /status (system health + active deadlines), /triage (last 10 triage decisions with reasoning), /build [ticket-id] (trigger a build session for a specific Linear ticket), /escalate [ticket-id] (promote ticket to P0), /snooze [ticket-id] [duration] (suppress alerts for duration). Qwen 3 14B handles free-form messages as natural language commands.
Acceptance: /status returns formatted system health. /triage returns last 10 decisions. Free-form "what happened overnight?" returns a coherent summary.

**ENH-014: Build Claude API routing logic (Phase 2.5 / early Phase 3)**
Priority: Medium
Description: n8n routing workflow: Qwen 3 14B classifies incoming task by complexity (simple/medium/complex). Simple → Qwen handles locally. Medium → Claude Haiku 4.5. Complex → Claude Sonnet 4.6. Strategic/multi-step → Claude Opus 4.6. Confidence threshold: if Qwen's classification confidence < 70%, default to Sonnet. Log all routing decisions to Supabase with cost tracking.
Acceptance: 10 test tasks of varying complexity → correct routing for 8/10. Cost per routed task logged. Monthly cost projection available.

### Gating & Governance

**ENH-015: Define 14-day clean-operation gate criteria**
Priority: High
Description: Document the exact criteria for the 14-day gate: (a) Mac Mini uptime > 99.5% (max 1 hour cumulative downtime), (b) Ollama crash-and-recover events < 3, (c) n8n workflow execution success rate > 95%, (d) triage accuracy > 80% (reviewed by Phill daily for week 1), (e) zero incidents requiring manual SSH/terminal intervention. Log all metrics in Supabase. Dashboard shows gate progress.
Acceptance: Gate criteria documented in .harness/ENHANCED-GATE-CRITERIA.md. Supabase tables for uptime and triage metrics exist. Dashboard shows gate progress as percentage.

---

## RESEARCH ADDENDUM — Critical Findings (Post-Deliberation)

Deep research conducted after the board adjourned surfaced five findings that materially affect the build plan. The CEO has incorporated these into the final ticket package.

### Finding 1: Qwen 3 14B has critical Ollama compatibility issues
Tool calling is **completely non-functional** in Qwen 3 on Ollama (format mismatch — GitHub issue #14493). Structured JSON output via Ollama is unreliable due to penalty sampler bugs (repeat/presence/frequency penalties silently ignored). **Recommendation from research: use Llama 3.3 8B as the default triage model — lower risk, proven on M4 Pro, sufficient for classification/routing. Reserve Qwen 3 14B for when tool-calling is fixed or use vLLM instead of Ollama for structured output.**

> **CEO ruling:** ENH-008 (triage prompt) is updated to test BOTH Llama 3.3 8B and Qwen 3 14B in the first week. The model that produces more reliable structured triage output wins the permanent slot. The board paper's commitment to "Qwen 3 14B committed" is softened to "Qwen 3 14B preferred, Llama 3.3 8B as fallback."

### Finding 2: Mac Mini M4 auto-restart after power failure has KNOWN ISSUES
Apple Community reports confirm that the "Start up automatically after power failure" setting **does not work reliably on M4 Mac Minis** (works on M2, fails on M4, same macOS Sequoia version). This is hardware-specific.

> **CEO ruling:** UPS is upgraded from "recommended" to **mandatory prerequisite**. ENH-005 is now a blocking dependency for Phase 1. The UPS must support macOS USB signaling for graceful shutdown. The auto-restart setting should still be enabled but cannot be relied upon as the sole recovery mechanism.

### Finding 3: n8n misses scheduled executions if the Mac sleeps
n8n documentation explicitly states that scheduled workflows miss executions if the host machine sleeps. n8n themselves recommend managed cloud hosting for reliable 24/7 cron.

> **CEO ruling:** Phase 0 must include `caffeinate -s` (or equivalent) configured via launchd to prevent Mac Mini from sleeping. ENH-001 is expanded to include sleep prevention. Additionally, n8n workflows must include a "heartbeat watchdog" that detects missed executions and self-corrects.

### Finding 4: Docker Desktop reserves 4GB RAM by default
Even with zero containers running, Docker Desktop on macOS M4 Pro reserves 4GB of unified memory for its Linux VM. This significantly tightens the memory budget.

> **CEO ruling:** Docker Desktop memory limit must be configured to 2GB in Phase 0 (sufficient for n8n). This is added to ENH-003. Memory budget revised: Qwen 3 14B ~10-12GB (model + KV cache) + macOS ~4GB + Docker ~2GB = ~18GB used, ~6GB free. Tighter than the board estimated but still workable.

### Finding 5: Ollama health monitoring endpoints confirmed
Ollama exposes `GET /` ("Ollama is running"), `GET /api/tags` (lists loaded models), and `GET /api/version`. No formal `/health` endpoint, but `/api/tags` is the best check because it confirms models are loaded and responsive, not just that the process is alive.

> **CEO ruling:** ENH-004 health check script uses `/api/tags` as the primary Ollama check, not just process-alive detection.

### Finding 6: Cole Medin's second-brain-starter confirmed viable
Heartbeat pattern: Python gathers data → Claude reasons → notifications (~$0.05/run). Hybrid RAG: FastEmbed (local ONNX) + Postgres with 70% vector + 30% keyword search. Memory persists in markdown files. n8n has **native Ollama nodes** (not just HTTP Request) — configure base URL to `http://localhost:11434` (native) or `http://host.docker.internal:11434` (Docker-to-host).

> **CEO ruling:** n8n Ollama integration uses the native Ollama node, not HTTP Request. Cole Medin's second-brain-starter heartbeat pattern is the template for ENH-010. The ~$0.05/run cost for Claude-backed heartbeats is acceptable at 5 heartbeats × 24 runs/day = ~$6/day, and can be reduced by routing routine heartbeats through the local model once triage accuracy is proven.

---

**ENH-016: Revise ZTE scoring to include operational health**
Priority: High
Description: Current ZTE score (60/60) measures feature completeness only. Revise to include: (a) service uptime (autonomy.py, n8n, Ollama), (b) triage response time, (c) unresolved P0 count, (d) fleet heartbeat delivery rate. A platform with dead services cannot score above 40/60 regardless of feature count. Update the ZTE scorecard calculation and re-score current state honestly.
Acceptance: New ZTE methodology documented. Current score reflects operational reality (expected to drop significantly from 60/60). Dashboard shows real-time ZTE score.
