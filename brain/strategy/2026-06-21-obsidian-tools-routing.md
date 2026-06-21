---
type: routing-report
generated: 2026-06-21T00:48:00Z
title: Obsidian Tools & Ideas — Research + Project Routing
sources:
  - brain/plaud/2026-06-10-06-11-bridging-the-execution-gap-in-an-ai-driven-business-ecosystem-a-systemic-overhaul-mandate.md
  - brain/plaud/2026-06-20-06-20-the-itr-button-a-referral-based-financial-ecosystem.md
  - brain/plaud/2026-06-18-06-18-rule-based-split-loan-home-finance-with-ai-concierge-turning-household-debt-discipline-into-scalable-habit-formation.md
  - "~/2nd Brain/2nd Brain/Wiki/plaud/2026-06-19-06-20-consultation-gavin-watts-diy-home-loan-strategy-superannuation-growth-and-etf-investment-plan.md"
  - brain/strategy/ruflo-deep-analysis-2026-05-30.md
  - brain/strategy/ruflo-integration-plan-2026-05-30.md
  - brain/strategy/SWAT-deployment-models-2026-05-30.md
  - brain/plaud/2026-05-30-restoreassist-local-deployment.md
---
<!-- ground:anchor {"primary_source":"brain/plaud/2026-06-10-06-11-bridging-the-execution-gap-in-an-ai-driven-business-ecosystem-a-systemic-overhaul-mandate.md","derived_from":["brain/plaud/2026-06-10-06-11-bridging-the-execution-gap-in-an-ai-driven-business-ecosystem-a-systemic-overhaul-mandate.md","brain/plaud/2026-06-20-06-20-the-itr-button-a-referral-based-financial-ecosystem.md","brain/plaud/2026-06-18-06-18-rule-based-split-loan-home-finance-with-ai-concierge-turning-household-debt-discipline-into-scalable-habit-formation.md","brain/strategy/ruflo-deep-analysis-2026-05-30.md","brain/strategy/ruflo-integration-plan-2026-05-30.md","brain/strategy/SWAT-deployment-models-2026-05-30.md","brain/plaud/2026-05-30-restoreassist-local-deployment.md"],"source_sha256":"bae2b2b0c1be81052014932012ecd15e78902b35efd8ac7bbe2f6f1adf6684ee","derived_at":"2026-06-21T00:48:27.228448+00:00","ttl_hours":168,"chain":["brain/plaud/2026-06-10-06-11-bridging-the-execution-gap-in-an-ai-driven-business-ecosystem-a-systemic-overhaul-mandate.md"],"confidence":0.85} -->

# Obsidian Tools & Ideas — Research + Project Routing

What does this report do? It pulls the captured tools/ideas from the Obsidian vault and brain notes, researches each, and routes each to the correct portfolio project per `.harness/projects.json` — separating **tracking home** (where work is tracked in Linear today) from **build home** (where code lives). No Linear tickets, code, or repos were created; this is a routing decision surface for approval.

**The pull:** the vault `~/2nd Brain/2nd Brain/Wiki/plaud/` is a recent subset of repo `brain/plaud/`. The one net-new item is the Gavin Watts consultation (2026-06-19), a live client validating the split-loan product. Five recent `brain/plaud/2026-06-*.md` files are empty un-transcribed stubs and were excluded; only notes with real content were used.

**Headline finding:** the two fintech products (ITR Button, DIY split-loan) are **not build-ready** — Australian regulation makes their core "AI recommendation / coaching" feature the exact thing that triggers AFSL / credit / tax-agent licensing. They are routed as **compliance-gated feasibility items**, not engineering tickets. The dev-infrastructure items (3–8) are build-ready and route cleanly to existing projects.

## Executive routing table

| # | Item | Tracking home (id) | Build home | team_id | project_id | Conf | Status |
|---|------|--------------------|-----------|---------|-----------|------|--------|
| 1 | ITR Button (referral ecosystem) | ccw-crm | NEW repo `CleanExpo/itr-button` | `ab9c7810…` | `40c7dc3d…` | 0.75 | review — homeless build · **compliance-gated** |
| 2 | DIY split-loan AI concierge | unite-group (incubate) | NEW repo | `ab9c7810…` | `b62d9b14…` | 0.55 | review — homeless · **compliance-gated** |
| 3 | Ruflo patterns (vector mem, hooks, skill metadata, model routing) | pi-dev-ops | pi-dev-ops | `a8a52f07…` | `f45212be…` | 0.95 | matched |
| 4a | 1Password — shared secret infra | pi-dev-ops | pi-dev-ops | `a8a52f07…` | `f45212be…` | 0.80 | matched |
| 4b | 1Password — consumer (social/GA creds) | synthex | synthex | `b887971b…` | `3125c6e4…` | 0.80 | matched |
| 5 | Web business-profile extraction (onboarding) | synthex | synthex | `b887971b…` | `3125c6e4…` | 0.95 | matched |
| 6 | Voice + 3D Mission Station console | pi-dev-ops | pi-dev-ops | `a8a52f07…` | `f45212be…` | 0.80 | matched — flag brand/Nexus ownership |
| 7 | RestoreAssist cloud→local deployment | restoreassist | restoreassist | `a8a52f07…` | `3c78358a…` | 0.95 | matched |
| 8 | Hermes follow-ups (vector backfill, enforce routing, hooks, security) | pi-dev-ops | pi-dev-ops | `a8a52f07…` | `f45212be…` | 0.95 | matched — exec backlog of #3 |

IDs were resolved via `scripts/plaud_actions.py::resolve_linear_route()` (all returned `status=matched`, no fallback). Full IDs are in `.harness/projects.json`; truncated above for readability.

---

## Per-item detail

### 1. ITR Button — referral-based financial ecosystem
**What it is:** Two AI chatbots (Dmitri pre-lodgement, Noah post-lodgement) build a Summary/Recommendation/Timeline document and refer individuals (~$30) to accountants, brokers, and planners. Source: [execution-gap note](../plaud/2026-06-10-06-11-bridging-the-execution-gap-in-an-ai-driven-business-ecosystem-a-systemic-overhaul-mandate.md) (names "Duncan Perkins (ITR Button)" as a CCW-tracked paying client) and [ITR Button note](../plaud/2026-06-20-06-20-the-itr-button-a-referral-based-financial-ecosystem.md).

**Routing:** Track under **ccw-crm** (Duncan Perkins is a CCW client). **No build repo exists** — recommend `CleanExpo/itr-button` once the legal model is fixed. This is the founder's named post-2028 venture with Duncan and Toby, so it warrants its own repo, not pi-dev-ops.

**Feasibility — AMBER sliding to RED on the current design.** The referral fee can be made lawful, but three designed features are non-compliant:
- **Consumer-paid credit referral breaks the exemption.** A credit referral is exempt only under NCCP reg 25 (pass name + contact only, recommend no product, disclose benefit) — and the broker/lender pays the referrer, not the consumer. Charging the individual $30 for the credit leg breaks it. (austlii reg 25; reg 9AB)
- **The "Recommendation" document is the biggest risk.** Tailored tax/financial recommendations for a fee likely constitute both unlicensed personal financial advice (Corporations Act s766B → AFSL) and an unregistered tax-agent service (TASA s90-5 — strict offence to charge for a tax-agent service while unregistered). (asic.gov.au financial-product-advice; tpb.gov.au)
- **Avoiding TFN/ID buys almost nothing.** Disclosing personal information to partners for a fee is "trading in personal information," which strips the <$3m small-business Privacy Act exemption — the platform is a full APP entity regardless. (oaic.gov.au)
- **No legitimate programmatic ATO data access** exists for a third party (myID is the individual's own; SBR/agent access is gated to registered agents; Consumer Data Right excludes tax data). Collect only user-volunteered facts. (ato.gov.au; cdr.gov.au)
- **Conflicted remuneration** risk on planner referral fees (ASIC v RM Capital; RG 246).

**Compliance guardrails for the build:** factual information only (rename "Recommendation" → "Information" + not-advice disclaimer); never name a specific product/lender/broker/planner; re-architect the $30 to be partner-paid; APP-entity compliance from day one; no ATO integration; human escalation when a query drifts to personal advice.

**Competitive note:** every credible incumbent (H&R Block, Etax, POP Tax) operates as/via a registered tax agent and actually lodges; Airtax (PwC) exited tax services 2024. A pure "recommend + refer, charge the consumer" layer has no surviving precedent.

**Effort/risk:** L / **High (regulatory).** **Dependencies:** AFSL/credit-lawyer + TPB review before any build. **Open question:** is the intent a licensed product (Duncan/Toby venture) or a thin compliant introducer? That decision gates the repo.

### 2. DIY split-loan AI concierge
**What it is:** A white-label home loan with multiple credit lines (non-deductible home debt + a deductible investment line for ETFs) plus an AI concierge coaching budgeting, concessional super contributions, dollar-cost averaging, and tax timing — "education only." Source: [split-loan note](../plaud/2026-06-18-06-18-rule-based-split-loan-home-finance-with-ai-concierge-turning-household-debt-discipline-into-scalable-habit-formation.md). **Net-new validation:** the Gavin Watts consult (2026-06-19, vault) — a 60yo, ~$380k super, wanting a $400k facility split into home/holiday/car/$100k-ETF lines plus a super-recontribution strategy. This is a real personal-advice scenario.

**Routing:** Incubate tracking under **unite-group** (no named owner; same founder/team). **No build repo** — recommend one once licensed. Compliance-gated.

**Feasibility — RED as conceived; AMBER if rebuilt licensed.**
- **The "education-only, no advice" framing fails.** Under ASIC v Westpac (2019–2021), where a tool ingests a user's situation and *urges a course of action*, a reasonable person expects personal circumstances were considered → personal advice regardless of labels → AFSL + best-interests duty + Statement of Advice. The whole value prop (coaching the $380k-super client toward super top-ups + a deductible line + ETFs) is squarely personal advice. (asic.gov.au 21-013MR)
- **Even general advice needs an AFSL** + s949A warning; **robo-advice is regulated identically** (RG 255) — ASIC shut down Lime FS's "education" tools.
- **Credit licensing (NCCP):** offering/white-labelling the loan needs an ACL or authorised-credit-rep status; white-labelling never avoids licensing (the funder holds the ACL; the brand still needs ACL/ACR).
- **Debt recycling is legal** but rests on the interest "use test" (TR 95/25; FCT v Munro); mixed-purpose line-of-credit facilities are high-risk for deduction contamination (TR 2000/2). Moneysmart flags borrowing-to-invest against the home as a strategy where you can lose your home. DDO/TMD obligations attach to the ETF/investment line (RG 274).

**Compliance guardrails for the build:** do not key any response to the user's circumstances; no recommendations / no urging; no naming specific ETFs or the investment line; factual info or licensed general advice only; hard human-escalation for anything circumstance-specific; monitor/test the algorithm (RG 255).

**Effort/risk:** L / **High (regulatory).** **Dependencies:** ACL (via funder/aggregator) + AFSL + credit-lawyer review. **Open question:** licensed advice product vs a pure educational content tool with no personalisation — only the latter avoids an AFSL, and it cannot do what the consult scenario needs.

### 3. Ruflo patterns → pi-dev-ops
**What it is:** Four agentic-infra patterns to adopt into Hermes/Nexus/TAO. Source: [ruflo-deep-analysis](ruflo-deep-analysis-2026-05-30.md), [ruflo-integration-plan](ruflo-integration-plan-2026-05-30.md).

- **3a. Vector / semantic memory near SQLite.** Recommend **`sqlite-vec`** (official successor to sqlite-vss; single dependency-free extension storing vectors *in the same `.db`*) added alongside the existing FTS5 store on the same `rowid`, fused with Reciprocal Rank Fusion (k=60). Embed with `all-MiniLM-L6-v2` (384-dim, free/CPU/offline) behind one swap-able function. Additive migration — FTS5 untouched. Brute-force KNN suits up to hundreds of thousands of vectors. (github.com/asg017/sqlite-vec; alexgarcia.xyz hybrid-search)
- **3b. Hook-based event system.** Recommend a ~30-line stdlib registry (`dict[str, list[Callable]]` over `pre_task/post_task/pre_edit/post_edit/session_end`) wrapping each handler in `try/except` for isolation — mirrors Claude Code's lifecycle model (silent = no opinion; explicit return = decision; `pre_*` can veto). Avoid blinker (propagates the first receiver exception). Wires into the existing `app/server/kill_switch.py` / orchestrator tick. (code.claude.com/docs/hooks)
- **3c. YAML skill metadata.** Schema (tags/related_skills/pinned/category) is already drafted in the ruflo plan; the only work is the parser change to skill loading + regenerating `agentskills.json`.
- **3d. 3-tier model routing.** Mostly already hardwired (RA-1099, `app/server/model_policy.py`). This is **gap analysis only** vs what the note still wants — see #8.

**Implementation reuses:** the existing SQLite session store, `model_policy.select_model()`, the orchestrator loop. **Effort/risk:** M / Low. **Dependencies:** none blocking. **Open question:** embed locally (MiniLM) vs an API embedding model — start local.

### 4a. 1Password — shared secret infrastructure → pi-dev-ops
**What it is:** Runtime credential resolution for automations. Source: [execution-gap note](../plaud/2026-06-10-06-11-bridging-the-execution-gap-in-an-ai-driven-business-ecosystem-a-systemic-overhaul-mandate.md) (§2).
**Approach:** Use a **1Password Service Account** (`OP_SERVICE_ACCOUNT_TOKEN`) + the **`onepassword-sdk` Python package**, which resolves the same `op://vault/item/field` references the codebase already uses (via the Pydantic `field_validator`). The SDK is async; resolved values reflect the latest vault version, so rotation needs no redeploy. Fetch at boot / cache with TTL (Business limits: 10k reads/hr, 50k req/day). Store the token only as a Railway secret. Connect (self-hosted) is only worth it at high volume / on-prem. (developer.1password.com/docs/sdks, /service-accounts)
**Effort/risk:** S / Low. **Dependency for:** 4b, 5, and ITR/Synthex partner creds.

### 4b. 1Password — consumer (social / Google Analytics creds) → synthex
**What it is:** Synthex fetching social-media + GA credentials at runtime for campaign automation. Routed to **synthex** because that is where the credentials are used (marketing features live inside Synthex). Built on 4a's shared layer. **Effort/risk:** S / Low. **Dependency:** 4a.

### 5. Web business-profile extraction → synthex
**What it is:** Given a business name/URL, extract ABN, logo, brand colors, fonts, social profiles, mission — the broken Synthex onboarding scrape. Source: [execution-gap note](../plaud/2026-06-10-06-11-bridging-the-execution-gap-in-an-ai-driven-business-ecosystem-a-systemic-overhaul-mandate.md) (§2).
**Approach:** Two parallel lookups joined on the business — the authoritative **ABR ABN Lookup web service** (free, requires a registered auth GUID) for the ABN, and a homepage scrape (`selectolax` over `<head>`: OG/meta/favicon/theme-color/social links; `colorthief` for dominant color; Google-Fonts/`@font-face` for type) for branding — then an LLM extracts the mission from the about page. **Flag:** Clearbit's free Logo API sunset 2025-12-01; use **Logo.dev** or **Brandfetch** instead. Honour robots.txt/ToS, identify the bot, throttle + cache. (abr.business.gov.au/Tools/WebServices; logo.dev; brandfetch.com)
**Effort/risk:** M / Low-Med (ToS hygiene). **Dependency:** ABR GUID registration. **Open question:** brand API (paid, normalized) vs DIY scrape (free, flaky) — start DIY, add Brandfetch if quality lags.

### 6. Voice + 3D Mission Station console → pi-dev-ops
**What it is:** The founder wants the command console visual (graphs/3D) + voice, not text. Source: [execution-gap note](../plaud/2026-06-10-06-11-bridging-the-execution-gap-in-an-ai-driven-business-ecosystem-a-systemic-overhaul-mandate.md) (Mission Station / Nexus). **Routing flag:** the note frames it as "Unite Group Nexus," but the running code (`app/server/routes/mission_control.py`, `dashboard/`) lives in pi-dev-ops — routed here on that basis; confirm brand ownership.
**Approach:** `react-force-graph-3d` for live agent/system topology + `react-three-fiber` for custom scenes (both `'use client'` + `next/dynamic` `ssr:false`); **ElevenLabs Flash v2.5** (server-side) for voice-out status summaries with browser `SpeechSynthesis` fallback; browser `SpeechRecognition` for voice-in. Feed from the existing `/api/mission-control/live` via 4s polling (matches the active-build strip; SSE drops through Vercel's ~10s proxy per `dashboard/hooks/useSSE.ts`). Reuse `swarm/voice_compose.py` for TTS. (elevenlabs.io/docs; react-force-graph; r3f.docs.pmnd.rs)
**Effort/risk:** L / Med. **Dependencies:** `ELEVENLABS_API_KEY` (already used by the 6-pager). **Open question:** pi-dev-ops vs unite-group ownership.

### 7. RestoreAssist cloud→local deployment → restoreassist
**What it is:** Recorded decision to shift RestoreAssist from cloud-managed to local/on-prem deployment. Source: [restoreassist-local-deployment note](../plaud/2026-05-30-restoreassist-local-deployment.md); synthesize topology from [SWAT-deployment-models](SWAT-deployment-models-2026-05-30.md). **Effort/risk:** M / Med. **Dependency:** the SWAT analysis already exists — synthesize, don't re-research. **Open question:** capture the rationale from the 52-second note's full transcript before acting.

### 8. Hermes follow-ups → pi-dev-ops
**What it is:** The execution backlog behind #3 — backfill remaining sessions into vector memory, enforce 3-tier model routing in code (vs the configured-but-not-fully-enforced state), event-driven hooks replacing cron, security hardening (CVE scan, token entropy, jailbreak probes). Source: [hermes week1-2 completion](hermes-week1-week2-completion-2026-05-30.md). **De-dupe:** treat as #3's delivery tickets, not a separate initiative. **Effort/risk:** M / Low. **Dependency:** #3a (vector) + #3b (hooks).

---

## Homeless / new-repo recommendations
Items **1 (ITR Button)** and **2 (DIY split-loan)** have no build repo and should **stay strategy/feasibility items until the legal model is resolved** — they are not engineering tickets.
- **ITR Button:** track under ccw-crm; recommend repo `CleanExpo/itr-button` only after AFSL/credit + TPB review fixes the recommendation/fee/data design. It is the founder's named Duncan/Toby venture.
- **DIY split-loan:** incubate tracking under unite-group; recommend a repo only after ACL + AFSL path is confirmed. The Gavin Watts scenario is personal advice and cannot be served by an "education-only" bot.
- **Tracking ≠ build:** do not let either spawn build tickets on a CRM/incubation kanban. The next step for both is a legal/feasibility review, not a sprint.

## Verification appendix
- **Routing IDs resolve:** all routed portfolios returned `status=matched` from `resolve_linear_route()` (ccw-crm, unite-group, pi-dev-ops, synthex, restoreassist). No item routes to `oh-my-codex` (null project), so no team-level-only flag needed.
- **Source links resolve to real, non-empty notes:** the 3 content plaud notes + Gavin Watts consult + 3 strategy docs were used; the 5 empty 17-line stubs were excluded.
- **Items 1 & 2** appear in the homeless section with build-home = NEW repo, status = review; item 2 confidence (0.55) < 0.6 flagged review.
- **1Password split into 4a/4b**; **item 8 cross-references item 3**.
- **Grounding anchor round-trips:** `grounding.anchor_from_text(report_body)` returns the anchor (verified at generation).
- **Net-new pull captured:** the Gavin Watts consult is represented under item 2.
- **Non-goals honoured:** no Linear tickets, no code, no repos created.

## Recommended next steps (for approval — not yet executed)
1. **Dev-infra (build-ready), file tickets to the resolved projects:** #3/#8 → pi-dev-ops; #4a → pi-dev-ops, #4b/#5 → synthex; #6 → pi-dev-ops; #7 → restoreassist. Use `scripts/linear_helpers.py::create_linear_issue()` with the resolved IDs, each anchored to its source note.
2. **Fintech (compliance-gated):** route #1/#2 to a **legal/feasibility review**, not a build. Decide licensed-product vs thin-introducer before creating either repo.
3. **Optional follow-up:** build the recurring "pull-from-Obsidian" read pipeline (deferred this pass) so this routing runs automatically.
