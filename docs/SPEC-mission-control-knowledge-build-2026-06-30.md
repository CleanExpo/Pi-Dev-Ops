---
title: "Mission Control — Knowledge-Driven Build Update"
status: spec — ready for slicing
source: 2nd Brain Sources ingest (10 most-recent, 2026-06-30) → STORM 5-lens Board synthesis
method: source-ingest → distill → STORM multi-viewpoint (Technical Architect, Revenue, Product Strategist, Contrarian, Compounder) → Senior-PM synthesis
created: 2026-06-30
owner: Pi-CEO / Mission Control (Pi-Dev-Ops dashboard)
---

# Mission Control — Knowledge-Driven Build Update

## How to use this spec

This is a **hardening update to the existing agentic substrate** (agentic-loop, dispatcher-core,
claude-runtime, kill-switch-binding, ~118 skills, OpenRouter-backed Hermes) — not a rebuild. Each
item below is sliceable to one Linear ticket. Build order is strict priority: **P0 → P1 → P2**.
Every recommendation is grounded in a stored source (`2nd Brain/Sources/Completed/`, indexed in
`Sources/SOURCE-LIBRARY.md`) and tagged by credibility tier. **Tier-3 sources are directional
only — never quote their figures as fact** (see Guardrails).

Each item carries: **What** (the build), **Why** (grounded), **Instructions of use** (how the
operator/agent invokes it), **Acceptance** (ship-it bar), **Effort**, **Lenses** (which Board
viewpoints back it).

## Executive summary

All five Board lenses converge on one verdict: this is a HARDENING update to an already-working agentic substrate (agentic-loop, dispatcher-core, claude-runtime, kill-switch-binding, ~118 skills, OpenRouter-backed Hermes), NOT a rebuild and NOT a chase of the corpus's tier-3 shiny objects. The single idea every lens independently endorses is model-stack resilience: closed models can be rug-pulled overnight (Fable precedent cited in the GLM-5.2/MiniMax-M3 source) and memory confirms the live risk is real today (Anthropic org out of API credit, service OAuth token unprovisioned), so a single Anthropic outage silently halts every autonomous loop. Anthropic Max stays the mandated, non-negotiable workhorse; GLM-5.2/MiniMax-M3 become a registered failover tier, never a default. The second cross-lens convergence is a skill-provenance/security gate: with ~118 skills and an open check-out/check-in model, an unvetted third-party skill is a direct exfil path from an agent holding live portfolio credentials. The strongest-grounded recommendation (the only one resting on verified tier-2 evidence rather than tier-3 video hype) is to codify CARSI's shipped posture empire-wide: LLMs as bounded assistants over a deterministic core, with an independent-verifier and append-only audit layer guarding auth/payments/deploy/enrolment. Revenue adds the highest-leverage NEW surface: a per-client Stripe x Linear x CI panel that turns invisible completed work into collectable cash. The Contrarian's discipline holds throughout: eight of ten source records are tier-3 anecdote or tier-2 context, star counts are vanity (Nous Hermes ~200k, Matt Pocock skills ~143k are implausible/inflated), and the obvious reading — adopt OpenMontage/Hyperframes/Higgsfield, oh-my-codex orchestration, local GLM GPUs, KDP income plays — is mostly wrong or mandate-violating. Recommendation: ship the failover circuit breaker and skill gate first (P0), codify the bounded-assistant contract and revenue panel next (P1), and treat repo-intelligence and the URL-to-ad offer as measured pilots (P2), never faith-based deploys.


## P0 — build first (resilience + safety, blocks autonomy reliability)

### [P0 · M] Model-resilience circuit breaker: Max-primary workhorse with registered, dormant OpenRouter failover (GLM-5.2 then MiniMax-M3)

**What:** Wrap the existing Anthropic Max workhorse call in Hermes/Margot routing (the ${VAR} env-ref pattern already in use) with a failover ladder: primary = Anthropic Max (unchanged default), fallback registered but dormant. Add a Mission Control panel showing per-role (Margot, Hermes routes, PM-Core, dispatcher) current binding, tier, and a read-only 'fallback reachable?' health ping to the OpenRouter-hosted workhorse WITHOUT switching to it. Failover engagement is edge-triggered on sustained Anthropic 401/quota/5xx, emits exactly ONE Telegram alert on tier state-change, and keeps the kill-switch above the whole ladder. Credential-bearing or client-confidential loops require a manual confirm before crossing to OpenRouter; non-critical steps (status summaries, triage drafts) may auto-engage. Scrub/scope what crosses the third-party boundary.

**Why:** Substitutability is the only durable, mandate-compatible signal in the entire corpus (GLM/MiniMax source, tier-3, used for FRAMING not benchmark fact). Memory confirms the rug-pull risk is live now (anthropic-api-key-state: org out of credit, service token unprovisioned). A registered-but-dormant fallback converts an extinction risk into degraded-mode while honoring feedback-anthropic-first (Max is the workhorse) and feedback-alert-noise-edge-trigger (state-change alerts only).

**Grounded in:** GLM-5.2 vs MiniMax-M3 source (tier-3, directional only); memory: anthropic-api-key-state, feedback-anthropic-first, feedback-alert-noise-edge-trigger, reference-openrouter-keys, reference-llm-max-plans

**Lenses backing this:** Technical Architect, Revenue / Growth, Product Strategist, Contrarian, Compounder

**Acceptance (ship bar):** the change is committed behind the existing kill-switch, emits state-change-only telemetry (no per-cycle alerts), has a test or smoke-check proving the happy path AND the failure path, and a one-line entry in the Mission Control changelog. Tier-3-derived items additionally require a pilot-and-measure step before any default/auto behaviour is trusted.

### [P0 · M] Skill-provenance & security vetting gate before any skill enters the ~118-skill substrate

**What:** Add a pre-install/check-in gate in the Library check-out/check-in flow that scans every new or updated third-party skill (and any new MCP server) for prompt-injection / data-exfil / privilege-escalation / supply-chain patterns, records a provenance + scan verdict, and blocks auto-apply on a fail. Surface a PASS/REVIEW 'skill trust' badge in the dashboard skill registry. Execute the gate with our OWN Anthropic-native tooling (curator-security + opus-adversary + Anthropic cybersecurity-skills framing), using SkillSpector's 65-pattern/16-category taxonomy as a DIRECTIONAL reference checklist only — do NOT vendor the unverified tier-3 scanner into the trust path. Complementary to secrets_check.py (which misses sk-ant-oat/AIza shapes).

**Why:** The corpus itself warns agent skills are now an attack surface (Nvidia SkillSpector). With an open check-out model and an agent holding live portfolio credentials, one poisoned skill compromises every loop that loads it. This is low-regret hardening of an existing asset — and it must land BEFORE the MCP/skill-adoption pilots widen the surface.

**Grounded in:** 12 open-source AI projects source — SkillSpector / Anthropic Cybersecurity Skills (tier-3, directional); memory: pi-dev-ops-skills-agentic-substrate, skills-library-architecture, secret-redaction-gaps; skills: curator-security, opus-adversary

**Lenses backing this:** Technical Architect, Product Strategist, Contrarian, Compounder

**Acceptance (ship bar):** the change is committed behind the existing kill-switch, emits state-change-only telemetry (no per-cycle alerts), has a test or smoke-check proving the happy path AND the failure path, and a one-line entry in the Mission Control changelog. Tier-3-derived items additionally require a pilot-and-measure step before any default/auto behaviour is trusted.


## P1 — build next (codify proven patterns + revenue surface)

### [P1 · M] Codify CARSI's bounded-assistant / deterministic-core + independent-verifier + audit pattern as the empire-wide agentic contract

**What:** Promote CARSI's shipped posture to a Mission Control compliance principle applied to the dashboard's own agentic action path first: money/auth/billing/enrolment/CI-gate/deploy and any irreversible op stay deterministic application logic; LLMs are bounded assistants over them; every autonomous action passes an independent-verifier step (the src/lib/agents/independent-verifier.ts analog) and writes to an append-only audit layer. Add a per-repo 'AI boundary' status to the dashboard. Roll out REPORT-ONLY first (the pattern is verified for CARSI, only inferred for other repos).

**Why:** This is the ONLY trust pattern the verified tier-2 sources independently converge on (CARSI explicit; CCW's approvals/approval_steps + audit tables echo it). It is what keeps a cheaper failover-tier model's mistake from reaching production — the safety counterpart to recommendation 1 — and prevents the recurring 'agent did something irreversible' class. Strongest-grounded rec in the corpus.

**Grounded in:** CARSI README (tier-2, VERIFIED — 'LLMs are bounded assistants, NOT source of truth', independent-verifier.ts, audit/); CCW-CRM docs README approvals + audit (tier-2); memory: feedback-autonomy, unite-group-margot-evidence-logs

**Lenses backing this:** Technical Architect, Revenue / Growth, Product Strategist, Compounder, Contrarian

**Acceptance (ship bar):** the change is committed behind the existing kill-switch, emits state-change-only telemetry (no per-cycle alerts), has a test or smoke-check proving the happy path AND the failure path, and a one-line entry in the Mission Control changelog. Tier-3-derived items additionally require a pilot-and-measure step before any default/auto behaviour is trusted.

### [P1 · M] Per-client Revenue & Delivery panel (Stripe milestones x Linear status x CI/deploy)

**What:** Add a Mission Control panel joining each client (CARSI, CCW, RestoreAssist) to open/paid Stripe milestones, their Linear project status, and latest CI/deploy state, with 'billable now', 'blocked', 'shippable' badges. Rails already exist (stripe-milestone-invoice skill, mcp-linear in CCW, reference-linear memory). The billing-state logic MUST sit behind the deterministic core + audit guardrail from rec 3 — a wrong 'paid'/'billable' badge could trigger incorrect client invoicing. Do not present partial/gated module capabilities (READMEs say maturity 'varies by module') as production-ready revenue.

**Why:** Revenue is currently invisible in the cockpit. Both CARSI and CCW already bill through Stripe; surfacing which completed work is deliverable-but-unbilled is the fastest path from work-done to cash-collected — the highest-leverage NEW surface, built on rails that already exist.

**Grounded in:** github-carsi-tech-stack (Stripe + test:stripe-webhook, tier-2 verified); github-ccw-crm README (quote-to-cash, mcp-linear, tier-2 verified); skills: stripe-milestone-invoice; memory: reference-linear

**Lenses backing this:** Revenue / Growth, Product Strategist

**Acceptance (ship bar):** the change is committed behind the existing kill-switch, emits state-change-only telemetry (no per-cycle alerts), has a test or smoke-check proving the happy path AND the failure path, and a one-line entry in the Mission Control changelog. Tier-3-derived items additionally require a pilot-and-measure step before any default/auto behaviour is trusted.

### [P1 · S] Standardize the connector substrate on Composio + mcp-linear (with Desktop-MCP fallback documented)

**What:** Codify CCW-CRM's proven wiring (@composio/core ^0.6.3 + mcp-linear ^0.1.8 as runtime deps) as the canonical Mission Control connector pattern per the connector-routing skill: Composio as the cross-environment default for cloud routines/portfolio integrations (Linear, GitHub, Slack, Gmail), mcp-linear for board ops, claude.ai cloud connectors only where unavoidable. Document the MCP-as-custom-connector onboarding step (URL-registered server, restart-to-load). Keep the Desktop-MCP fallback documented since Composio account-binding is known-fragile.

**Why:** CCW (tier-2, verified) shows the exact stack working in a live client build. Reusing it removes the recurring per-account Gmail/connector fragility memory repeatedly flags and gives one audited connector plane. Reusable substrate decision that pays off on every future integration.

**Grounded in:** CCW-CRM package.json (tier-2, VERIFIED — @composio/core, mcp-linear runtime deps); SaaS Ad Studio MCP-as-connector pattern (tier-3, directional); memory: project-composio-substrate; skill: connector-routing

**Lenses backing this:** Technical Architect, Compounder

**Acceptance (ship bar):** the change is committed behind the existing kill-switch, emits state-change-only telemetry (no per-cycle alerts), has a test or smoke-check proving the happy path AND the failure path, and a one-line entry in the Mission Control changelog. Tier-3-derived items additionally require a pilot-and-measure step before any default/auto behaviour is trusted.

### [P1 · S] Guardrail ADR: no Codex in autonomous loops, no brand-video substrate swap, no silent model auto-switch

**What:** Commit a short ADR/guardrail in the Mission Control repo stating: (a) oh-my-codex and any Codex-CLI multi-agent orchestration are excluded from the autonomous substrate — Codex stays precision-only; (b) the brand-video pipeline stays ElevenLabs+Nano-Banana(margot)+ffmpeg — Higgsfield/Hyperframes/OpenMontage are evaluated only as optional renderers behind a flag, never a default rip-and-replace; (c) the failover tier never becomes silent active routing — every tier flip is human-visible.

**Why:** oh-my-codex (source 10, already forked into CleanExpo) is exactly the kind of thing that gets quietly wired into a loop; feedback-anthropic-first forbids it. An explicit written 'don't' is far cheaper than undoing a substrate swap or mandate violation later. Defensive, low-effort, prevents the corpus's biggest traps.

**Grounded in:** oh-my-codex (source 10) + Higgsfield (source 3) + OpenMontage/Hyperframes (source 1), all tier-3; constrained by memory: feedback-anthropic-first, faceless-video-substrate

**Lenses backing this:** Contrarian, Technical Architect, Compounder

**Acceptance (ship bar):** the change is committed behind the existing kill-switch, emits state-change-only telemetry (no per-cycle alerts), has a test or smoke-check proving the happy path AND the failure path, and a one-line entry in the Mission Control changelog. Tier-3-derived items additionally require a pilot-and-measure step before any default/auto behaviour is trusted.


## P2 — backlog (pilots; measure before trust)

### [P2 · L] Portfolio repo-intelligence index + per-project stack cards (PILOT, measure before trust)

**What:** Pilot a single fast structural index across the heterogeneous portfolio repos (Pi-Dev-Ops, CARSI = Next16/React19/Prisma7/Postgres15/Stripe; CCW = Next16.2.6 + FastAPI/Postgres+pgvector/Composio; Unite-Group Nexus; RA) so any agent can query 'where is auth / where is the migration / what stack' without re-grepping. Render per-project stack cards from CAPTURED package.json/README (not memory), tagged with capture-date and tied to a refresh job to prevent drift. Stand up Codebase Memory MCP as the candidate engine but MEASURE the claimed sub-1ms query / 120x token reduction against real pm-core runs before trusting it; grant it no broad filesystem/credential scope until vetted via rec 2.

**Why:** Repo context is the quality ceiling for autonomous code agents and knowledge is currently re-discovered every session (the corpus itself is package.json/README captured by hand). A shared index compounds across every future loop. But tier-3 benchmark claims (28M LOC in 3 min) are unverified — pilot-and-measure, don't deploy on the star count. Grounding cards in captured truth also fixes the two-command-surfaces conflation bug.

**Grounded in:** 12 open-source AI projects — Codebase Memory MCP / Deus Data (tier-3, directional); CARSI + CCW package.json/READMEs (tier-2, verified stack facts); memory: pi-dev-ops-skills-agentic-substrate, two-command-surfaces

**Lenses backing this:** Technical Architect, Compounder, Product Strategist

**Acceptance (ship bar):** the change is committed behind the existing kill-switch, emits state-change-only telemetry (no per-cycle alerts), has a test or smoke-check proving the happy path AND the failure path, and a one-line entry in the Mission Control changelog. Tier-3-derived items additionally require a pilot-and-measure step before any default/auto behaviour is trusted.

### [P2 · M] Skill/Source intake lane with tier-badged inflow feed

**What:** Surface the 2nd Brain Sources/ ingestion stream as a Mission Control feed: each card shows title, tier badge (tier-2 verified vs tier-3 directional), one-line relevance, key entities. Tier-3 cards are visually marked 'directional — not citable' and CANNOT be promoted to a fact/decision without a verification step. A candidate skill/tool moves discovered -> vetted -> adopted/rejected, where 'vetted' invokes the rec-2 security gate. This is the UI layer that enforces no-false-reporting and the governed install path.

**Why:** Phill actively pulls untrusted tools from YouTube curation into Sources/; today there is no governed path from 'saw it in a video' to 'vetted and adopted/rejected'. One move fixes signal surfacing (tier-aware feed), adoption workflow (governed install), and KB integration (Sources/ rendered in dashboard). Folds naturally onto rec 2's gate.

**Grounded in:** All 10 records carry explicit tier fields (tier-2 CARSI/CCW vs tier-3 Berman/Hummus/Rogoff/IndyDevDan); memory: feedback-no-false-reporting, source-library-ingest, skills-library-architecture

**Lenses backing this:** Product Strategist

**Acceptance (ship bar):** the change is committed behind the existing kill-switch, emits state-change-only telemetry (no per-cycle alerts), has a test or smoke-check proving the happy path AND the failure path, and a one-line entry in the Mission Control changelog. Tier-3-derived items additionally require a pilot-and-measure step before any default/auto behaviour is trusted.

### [P2 · L] Productize 'URL → cinematic UI ad' as a billable offer (PILOT behind a flag, model the margin first)

**What:** Wrap the EXISTING brand-video/Hyperframes pipeline (ElevenLabs+Nano-Banana+ffmpeg, NOT the Higgsfield sponsor stack) into a Mission Control action: client SaaS URL -> brand-DNA extraction -> 3 concepts -> shot list -> UI-reveal promo. Treat the 'GPT image model over Nano-Banana for on-screen text fidelity' as a narrow A/B test, not a substrate change. Model per-asset margin (third-party credit cost) BEFORE selling fixed-price. Sell as a recurring deliverable only after the pilot proves quality.

**Why:** Net-new high-margin revenue from a capability Pi-CEO already owns, for UI-heavy SaaS where the product IS the screen. BUT the Contrarian is right that this is tier-3 sponsor-driven inspiration and non-compounding — so it is a flagged pilot reusing the locked substrate, not a P0/P1 build cycle, and never quotes tier-3 income figures to clients.

**Grounded in:** SaaS Ad Studio URL->ad walkthrough (tier-3, directional); brand-video skill; memory: faceless-video-substrate (locked stack), notebooklm-video-house-style

**Lenses backing this:** Revenue / Growth, Product Strategist

**Acceptance (ship bar):** the change is committed behind the existing kill-switch, emits state-change-only telemetry (no per-cycle alerts), has a test or smoke-check proving the happy path AND the failure path, and a one-line entry in the Mission Control changelog. Tier-3-derived items additionally require a pilot-and-measure step before any default/auto behaviour is trusted.


## Guardrails — what we explicitly will NOT do

- Will NOT integrate Codex (oh-my-codex / Codex-CLI orchestration) into any autonomous loop — Codex stays precision-only per feedback-anthropic-first.
- Will NOT make GLM-5.2 or MiniMax-M3 a default or active routing model — Anthropic Max remains the sole mandated workhorse; the open-weight tier is dormant insurance only, never a routing default, never silently activated.
- Will NOT rip out the proven brand-video substrate (ElevenLabs + Nano-Banana/margot + ffmpeg) for Higgsfield, Hyperframes, or OpenMontage — those are at most optional renderers behind a flag.
- Will NOT pursue local GLM-5.2 GPU ownership — the source itself says usable local needs ~$50-100k hardware and is realistic only ~mid-2027; hosted-via-OpenRouter already exists.
- Will NOT quote any tier-3 figure as fact: star counts (Nous Hermes ~200k, Matt Pocock skills ~143k are implausible/inflated), Artificial Analysis GLM/MiniMax benchmarks, or Shane Hummus / Glassdoor / KDP / affiliate income numbers — directional inspiration only, never client-facing ROI.
- Will NOT pursue KDP/affiliate/passive-income plays — non-compounding, off-substrate, anecdotal.
- Will NOT swap the locked image substrate (Artist.io/margot/Nano-Banana) for a GPT image model — the text-preservation tip is a narrow A/B test, not a substrate change.
- Will NOT vendor unverified tier-3 scanners (SkillSpector) or MCP servers (Codebase Memory) into the trust path or grant them broad credential/filesystem scope until vetted by our own gate.
- Will NOT treat tier-2 repo snapshots (CARSI/CCW) as a feature roadmap — their value is confirming the deterministic-core / bounded-assistant pattern and supplying ground-truth stack cards, not a to-build list.
- Will NOT fire failover or any alert per-cycle — edge-triggered on state change only, per the zero-tolerance alert-noise rule.


## Live tensions (unresolved design splits to decide during slicing)

- AUTO-FAILOVER vs BREAK-GLASS (the central split): Technical Architect and Revenue want the failover ladder to auto-engage on Anthropic 401/quota/5xx so loops never die. Contrarian, Product Strategist, and Compounder insist it stay DORMANT — read-only health tile, manual confirm, never silent active routing — because feedback-anthropic-first mandates Max as the workhorse and silent activation would violate it. Resolution adopted: edge-triggered, human-visible state change always; auto-engage permitted ONLY for non-critical/non-credential steps; manual confirm required for credential-bearing or client-confidential loops.
- FAILOVER IS ITSELF AN EXFIL SURFACE: The Technical Architect's own risk list notes that routing to third-party OpenRouter hosts (GLM/MiniMax) sends portfolio source/secrets across a boundary — directly tensioning the resilience push. This is why failover must scrub/scope payloads and may be inappropriate for credential-bearing loops, and why the skill/MCP security gate (P0) must precede broad adoption.
- VENDOR SkillSpector vs ANTHROPIC-NATIVE GATE: Technical Architect proposes piloting Nvidia SkillSpector's scanner; Contrarian and Product Strategist say do NOT vendor an unverified tier-3 scanner into the trust path — use SkillSpector's taxonomy as a directional checklist but execute with curator-security + opus-adversary + Anthropic cybersecurity-skills. Converged: adopt the pattern/taxonomy, not the tool.
- PRODUCTIZE URL-TO-AD: Revenue and Product Strategist call it the highest-margin new line; Contrarian flags it as sponsor-driven tier-3 hype that burns build cycles on a non-compounding win and contradicts the locked image substrate. Resolved by demoting it to a flagged P2 pilot on the existing substrate with margin modeled first.
- CODEBASE MEMORY MCP — PILOT vs TRAP: Technical Architect and Compounder see durable repo-intelligence leverage; Contrarian sees a sub-12k-star tier-3 tool that expands the supply-chain surface the corpus warns about. Resolved: pilot in isolation, measure benchmarks against real runs, no broad credential/filesystem scope until vetted.
- COMPOSIO CONCENTRATION: Compounder and Technical Architect want to standardize on Composio; both also note its cross-environment account-binding is known-fragile (memory). Standardizing concentrates risk — mitigated only by keeping the Desktop-MCP fallback documented.


## Evidence that would change this plan (re-evaluate triggers)

- If Anthropic provisions the long-lived service OAuth token (CLAUDE_CODE_OAUTH_TOKEN) AND restores org API credit, the failover circuit breaker drops from P0 to a lower-urgency resilience hedge — the live-outage risk that makes it P0 would be neutralized.
- Measured failover output quality: running GLM-5.2/MiniMax-M3 against real pm-core/QA ticket tasks. If quality is adequate, auto-engage scope can widen; if poor, failover stays strictly non-critical-step / manual-confirm only.
- Whether credential-bearing and client-confidential loop payloads can be reliably scrubbed/scoped before crossing the OpenRouter boundary — if not, those loops are excluded from failover entirely regardless of uptime cost.
- Independent verification of Codebase Memory MCP's benchmark claims (28M LOC in 3 min, sub-1ms query, 120x token reduction) in an isolated pilot against real portfolio repos — determines whether the repo-intelligence index graduates from P2 pilot to adopted substrate.
- Whether Anthropic ships a native skill-security scanner (or SkillSpector is independently verified) — would change WHICH tool executes the skill-provenance gate, though not whether the gate exists.
- A margin model for the URL-to-cinematic-ad offer (per-asset third-party credit cost vs sellable price) — a viable margin promotes it from flagged pilot toward a real revenue line; thin margin keeps it parked.
- If the bounded-assistant contract, rolled out report-only, produces false-positive compliance failures on repos that legitimately differ from CARSI's posture — would force per-repo tailoring before any enforcement.
- If Composio's cross-environment account-binding fragility recurs in testing, the standardization decision narrows and the Desktop-MCP fallback becomes primary for affected integrations.


## Provenance

- **Corpus:** 10 most-recent `2nd Brain/Sources/*.md` (ingested 2026-06-30), now in `Sources/Completed/`, indexed in `Sources/SOURCE-LIBRARY.md`.
- **Wiki pages written:** `open-source-ai-tooling-2026-06`, `claude-income-strategy-2026-06`, `claude-code-cinematic-ads-2026-06`, `model-stack-glm-minimax-2026-06`, `oh-my-codex-orchestration-2026-06`; confirmed-stack appends to `carsi.md`, `ccw.md`.
- **Tier split:** 6 tier-2 (CARSI ×2, CCW-CRM ×3, oh-my-codex) = verified; 4 tier-3 (Berman tools, Hummus income, cinematic-ads, GLM/MiniMax) = directional.
- **Synthesis:** 5 independent Board lenses + Senior-PM convergence (STORM). Full lens viewpoints retained in the run record.

## Readiness gate (2026-06-30)

**Verdict: spec is READY to slice into Linear tickets. Two P0 design decisions must be made before P0 code merges; P1 work can start immediately.**

| Item | Slice-ready? | Merge-ready? | Blocker before merge |
|---|---|---|---|
| P0-1 Model-resilience failover | ✅ | ❌ | Decide **auto-failover vs break-glass** (live tension #1) AND define the **credential-scrubbing boundary** before any payload crosses to OpenRouter (open question). Keys exist (`reference-openrouter-keys`). |
| P0-2 Skill-security gate | ✅ | ❌ | Decide **tooling**: pilot Nvidia SkillSpector (tier-3, unverified) vs an Anthropic-native/own-built scanner. Contrarian vetoes vendoring an unvetted scanner into the trust path. |
| P1-1 CARSI bounded-assistant contract | ✅ | ✅ | None — strongest-grounded (tier-2 verified). Roll out **report-only** first to avoid false-positive compliance failures. |
| P1-2 Per-client revenue panel | ✅ | ✅ | None blocking — rails exist (`stripe-milestone-invoice`, `mcp-linear`). Read-only join first. |
| P1-3 Composio connector standard | ✅ | ⚠️ | Document the **Desktop-MCP fallback** for Composio's known account-binding fragility before standardising. |
| P1-4 Guardrail ADR | ✅ | ✅ | None — write it now; it's the cheapest item and unblocks the others by settling won't-do. |
| P2-1/2/3 Pilots | ✅ | ❌ | Pilot-and-measure only; no merge-to-default until benchmarks verified in isolation. |

**Recommended build order:** (1) **P1-4 Guardrail ADR** first — codifies the won't-do list, settling the mandate boundary cheaply. (2) **P1-1 CARSI contract (report-only)** — lowest risk, highest grounding. (3) Resolve the two P0 design tensions (auto-vs-break-glass; scanner tooling), then ship **P0-1** and **P0-2**. (4) P1-2/P1-3. (5) P2 pilots last, measured.

**Hard gate on P0-1:** failover must NOT carry credential-bearing or client-confidential loop payloads across the OpenRouter boundary until scrubbing/scoping is proven — otherwise the resilience fix becomes a data-exfil surface (the Technical Architect's own risk #1).
