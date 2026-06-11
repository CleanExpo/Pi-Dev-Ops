# What's Actually Available — and What's Real vs. Hype

**Deep research: tools and techniques to move Pi-Dev-Ops from "completes the brief" to "plans ahead and verifies its own completeness"**

Date: 2026-06-07
For: Phill McGurk
Method: five parallel research angles (fan-out web search + primary-source fetch), then independent verification of the load-bearing claims against original sources.

---

## How to read this, and how confident I am

Every recommendation below is tied to a primary source with a date. Two of the most surprising claims I verified myself by fetching the original pages (noted inline). The rest comes from sourced research; where a claim is weak, unverified, or marketing, I say so. Where the honest answer is "no tool does this reliably yet," I say that too.

The single most important finding, up front, because it directly answers your fear that you're being told things that aren't true:

> **The honest test of whether software is "done" is whether real checks pass — tests, type-checks, a live request returning the right answer — NOT a model judging its own work. This is not opinion; it's the consistent finding of the 2024–2026 research. Your instinct to distrust "it says it's done" is correct, and the fix you've already started (coverage_check.py, which counts only what it can actually verify) is the right one.**

You are not behind. On three of the four areas you asked about, your existing design already matches what the most credible practitioners had to learn the hard way. The gap is narrow and specific, and it's the one we already identified.

---

## Area 1 — Self-verification / Definition of Done (your core problem)

**State of the art, honestly: the popular "spec-driven" tools are scaffolding, not verification. They will not stop an agent from falsely reporting "done."**

The reason is structural and was confirmed by a careful hands-on review from Thoughtworks (Birgitta Böckeler, 15 Oct 2025): the checklists and specs these tools generate are *interpreted by the same LLM that can ignore them*. Her section heading says it plainly — **"False sense of control?"** — after she repeatedly watched the agent not follow its own generated instructions. ([martinfowler.com](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html))

The tools, rated against your filters (open-source, fits your stack, solo-maintainable, production-real):

- **GitHub Spec Kit** — MIT, Python, ~106k stars, very active (verified via GitHub API, May 2026). Genuinely the most popular. But it's a *prompting discipline*: its "definition of done" checklists are advisory text, not machine-checked gates. Useful as input structure; cannot stop false completion. ([github.com/github/spec-kit](https://github.com/github/spec-kit))
- **OpenSpec** — MIT, ~52k stars, lightweight, repo-native, enforces a proposal→apply→archive state machine. The cleanest pure-OSS option if you want spec scaffolding with less verbosity than Spec Kit. Still LLM-interpreted. ([github.com/Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec))
- **Amazon Kiro** — has the best-in-class acceptance-criteria format (EARS: GIVEN/WHEN/THEN) and requirement→task traceability. But it is **proprietary, IDE-only, AWS-coupled** — it cannot be embedded in a headless Python agent loop. Steal the *format*, not the tool. ([kiro.dev](https://kiro.dev/docs/specs/))
- **Tessl** — most ambitious ("spec as the source of truth"), but the framework is in closed beta and the same reviewer verified it produces *different code from the same spec on re-runs*. Not adoptable today. ([tessl.io](https://tessl.io/))
- **BMAD-METHOD** — popular persona/prompt framework (~48k stars) but a non-standard license and, more importantly, it's "more agents reviewing more documents" — the same self-verification weakness, amplified.

**The peer-reviewed core finding** (this is the one to internalise): *LLMs Cannot Self-Correct Reasoning Yet* (Google DeepMind, ICLR 2024). When a model critiques its own answer with no external signal, performance gets **worse**, not better — GPT-4 on a maths benchmark fell from 95.5% to 91.5% to 89.0% over two self-correction rounds. Prior "self-correction works" results had quietly used a ground-truth signal to decide when to stop. ([arxiv.org/abs/2310.01798](https://arxiv.org/abs/2310.01798)) Your bug — terminating on a per-task self-judge — is exactly the failure this paper warns about.

**The tool you hoped for — something that diffs your intended spec against the code and lists what's missing — does not exist as a mature product.** It's an active research area (e.g. UserTrace, ReqToCode, 2025–2026), not a download. That part is genuinely DIY — and `coverage_check.py` is the start of it.

---

## Area 2 — Autonomous build loops: how reliable, really?

**State of the art, honestly: far less reliable than the marketing, and the headline benchmark everyone quotes is officially discredited.**

I verified this one directly. On **23 February 2026, OpenAI published "Why SWE-bench Verified no longer measures frontier coding capabilities"** and stopped reporting the metric. Their audit found **59.4% of the hard problems had flawed tests** that reject correct solutions, and that frontier models (GPT-5.2, Claude Opus 4.5, Gemini 3 Flash) can **reproduce the exact answer patches from memory** — i.e. the scores are partly memorisation. ([openai.com — verified by direct fetch](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)) An independent academic critique ("The SWE-Bench Illusion," arXiv 2506.12286) found the same.

What that means in plain terms: when a vendor says "92% resolve rate," treat it as marketing. On harder, less-contaminated tasks (SWE-bench Pro) the best agents land **~46–54%** — and that's single, well-scoped bug fixes with hidden tests, not building features. For genuinely *unattended, end-to-end* real work, the honest figure is roughly **15–40%**, and only with (a) tasks small enough to fit one context window, (b) machine-checkable success criteria, and (c) a human reviewing the result. The original Devin "~15% without human intervention" number remains directionally honest.

**The dominant production failure mode has a name, and it is exactly your experience:** *silent partial success* — the build is green, the endpoint returns 200, but the feature doesn't actually work. The agent "fails expensively rather than loudly." (Your own CLAUDE.md "Manual Verification Mandate" exists because of this — you'd already diagnosed it.) The other two documented failure modes are *looping* and *cost runaway* — there are public postmortems of overnight agent runs costing **$437** and an 11-day recursion costing **$47,000**.

The credible open-source engines, against your filters:

- **OpenHands** (formerly OpenDevin) — MIT, ~74k stars, Python, the most active and best-funded OSS coding-loop platform; ships a production-aimed SDK. The strongest "real" option. ([github.com/All-Hands-AI/OpenHands](https://github.com/All-Hands-AI/OpenHands))
- **SWE-agent** (Princeton) — MIT, Python, model-agnostic; a clean research-grade loop. Its 100-line `mini-swe-agent` is a good reference for how little code an honest loop needs. ([github.com/SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent))
- **Aider** — Apache-2.0, reliable *because* it stays human-in-the-loop with reviewable git diffs. Honest about not being fire-and-forget. ([github.com/Aider-AI/aider](https://github.com/Aider-AI/aider))
- **Cline** / **Goose** — real, well-funded, but deliberately approval-gated (Cline) or general-purpose (Goose). The gating is the honest admission that unsupervised autonomy isn't trustworthy yet.
- **Avoid: GPT-Engineer, GPT-Pilot, Devika** — the 2024 "AI software engineer" hype wave. High stars, now abandoned or commercialised. Do not build on them.

**"Ralph"-style loops** (fresh context each iteration, filesystem as memory) — which your system already implements — are confirmed by public writeups as the pattern that actually survives in production, but *only* with hard iteration/cost caps, stasis circuit-breakers, and bounded scope. You already have `TAO_MAX_ITERS`, `TAO_MAX_COST_USD`, and a `HARD_STOP` file. That's the right architecture.

---

## Area 3 — Planning & lookahead (your forward-planner)

**State of the art, honestly: the simple planning patterns work and are cheap; the fancy tree-search ones are mostly academic and too expensive for a live loop.**

- **Worth doing (verified, low-fragility):** *Plan-and-Execute* (plan upfront, execute, re-plan at a checkpoint) combined with *hierarchical decomposition* (an orchestrator splits work to sub-agents) and *parallel fan-out* for independent sub-tasks. Verified wins include 3–6× cost/latency savings (ReWOO, LLMCompiler) and a real **security bonus**: fixing the plan before untrusted tool output is seen prevents prompt-injection from hijacking the goal mid-run (arXiv 2509.08646). This is precisely what `forward-planner` does and what the Claude Agent SDK is naturally good at.
- **Avoid as overkill:** *Tree of Thoughts* and *Graph of Thoughts* in a live build loop — token-hungry, brittle, and their gains are mostly relative to each other, not to simple decomposition. *Language Agent Tree Search (LATS)* has the highest accuracy ceiling but is "not ideal in production" by practitioner consensus — use it offline if at all.
- **Distrust:** widely-shared blog stats like "Plan-Execute 92% vs ReAct 85%" — they trace to a single unsourced post. Not evidence.

Anthropic's own guidance ("Building Effective Agents") lands here too: the best production agents use **simple composable patterns**, not heavy planning frameworks. `forward-planner` is aligned with the real state of the art. Don't add tree-search machinery.

---

## Area 4 — Multi-agent orchestration (your swarm)

**State of the art, honestly: don't adopt a framework. Your custom swarm already follows the rule the experts converged on.**

I verified the foundational source: Cognition's **"Don't Build Multi-Agents"** (Walden Yan, 12 Jun 2025) argues, with the now-famous Flappy Bird example, that parallel agents making independent writes produce conflicting, incoherent results. Its two principles: *share full context* and *actions carry implicit decisions*. ([cognition.ai — verified by direct fetch](https://cognition.ai/blog/dont-build-multi-agents))

Anthropic's "How we built our multi-agent research system" (13 Jun 2025) seems opposite but isn't: multi-agent beat single-agent by 90% **on research** (a read-only, parallelisable task), while costing **~15× the tokens** — and Anthropic explicitly notes it does *not* work well for coding, which needs one consistent set of decisions. Cognition's April 2026 follow-up confirms the consensus: **keep writes single-threaded; extra agents contribute intelligence (analysis, review), not parallel actions.**

The frameworks (LangGraph, CrewAI, AutoGen/AG2, OpenAI Agents SDK, Microsoft Agent Framework, Google ADK) are real, but:
- All except partially CrewAI **fail your "solo non-coder maintainable" filter** — they're engineer-first, low-level, and add code surface rather than removing it.
- Most fight your stack (OpenAI SDK → OpenAI; ADK → Gemini/Google Cloud; MS Agent Framework → .NET/Azure).
- They **don't solve your hard problems** (context transfer, when to escalate) — those are prompt/training problems no framework fixes.

**The high-value thing to *steal* (zero new dependencies):** a *clean-context reviewer* — a verifier agent with **no shared context** that reviews the builder's output. Cognition reports it catches ~2 bugs per PR and works *better* without shared context. That's a natural, cheap addition to your existing swarm.

---

## What's missing — the direct answer to "I don't know what I don't know"

The missing piece is **not** a tool you haven't found or a framework you're behind on. The research is unambiguous: no off-the-shelf product reliably makes an agent's "done" trustworthy or diffs a spec against code to find gaps. The missing piece is a capability you have to assemble — and you've already started it. Concretely, what's missing is:

**Executable verification wired to a project-level Definition of Done** — every requirement maps to a real check (a test, an HTTP smoke assertion, a database assertion), and "done" means *all those checks pass*, judged by code, not by a model. `coverage_check.py` is the honest seed of this; right now it checks existence/registry facts, and the next step is to make each requirement carry an *executable* probe.

Everything else you asked about either (a) you already do right (Ralph loops with caps, single-threaded-write swarm, plan-and-execute), or (b) is hype you can safely ignore (benchmark scores, tree-search planners, multi-agent frameworks, spec-as-source tools).

---

## Recommended sequence — grounded in what you already have

Ordered by honest value per unit of effort. Each step produces something you can re-run and see.

1. **Make Definition-of-Done checks executable (highest leverage, you've started it).** Extend `coverage_check.py` so a requirement's probe can be "run this test," "GET this URL, expect this," "this DB row exists." A ticket may only be "done" when every probe is green. This is the one move with peer-reviewed backing (tests as the oracle; self-judge is not). It builds directly on what you have — no new dependency.

2. **Demote the LLM judge to advisory.** Keep `tao_judge`, but never let it be the sole terminator, and have it cite which executable checks passed. Use a *different* model than the one that did the work. (Evidence: self-judges are leniency-biased and can degrade results.)

3. **Add a harness to run the gates and produce a readable pass/fail artifact.** Either **promptfoo** (MIT, YAML config a non-coder can edit, CI exit codes) or **DeepEval** (Apache-2.0, pure Python, sits next to your FastAPI). Both are production-real and fit your stack. Use them to *run* checks, not to judge.

4. **Persist the results so "done" is auditable.** **Langfuse** (MIT, self-hostable with Docker, readable UI) records every gate result alongside your existing Supabase observability. So next time something claims "done," there's a stored trail you can open.

5. **Add a clean-context reviewer agent to the swarm.** No shared context, reviews the builder's output. Cheap, evidence-backed, no new framework.

6. **Keep — do not replace:** `forward-planner` (it matches the real planning SOTA), your Ralph loop with `TAO_MAX_ITERS`/`TAO_MAX_COST_USD`/`HARD_STOP` (this is how production autonomy actually survives), and your single-threaded-write swarm (the architecture the experts converged on). **Do not adopt** LangGraph/CrewAI/etc., tree-search planners, or spec-as-source tools.

The throughline: you stop trusting what the system *says* and start trusting what it can *show* — a passing check, a stored result, a re-runnable number. That's the entire fix, and it's mostly assembling pieces you've already begun, not buying or migrating to anything new.

---

## Sources (primary; dates noted)

Self-verification / DoD:
- Böckeler/Thoughtworks, "Spec-driven development tools" incl. "False sense of control" (15 Oct 2025) — https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html
- GitHub Spec Kit — https://github.com/github/spec-kit ; OpenSpec — https://github.com/Fission-AI/OpenSpec ; Kiro — https://kiro.dev/docs/specs/ ; Tessl — https://tessl.io/
- "LLMs Cannot Self-Correct Reasoning Yet," DeepMind, ICLR 2024 — https://arxiv.org/abs/2310.01798

Autonomous build loops (key claim verified by direct fetch):
- OpenAI, "Why SWE-bench Verified no longer measures frontier coding capabilities" (23 Feb 2026) — https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/
- "The SWE-Bench Illusion" — https://arxiv.org/abs/2506.12286
- OpenHands — https://github.com/All-Hands-AI/OpenHands ; SWE-agent — https://github.com/SWE-agent/SWE-agent ; Aider — https://github.com/Aider-AI/aider ; Cline — https://github.com/cline/cline ; Goose — https://github.com/block/goose

Planning & lookahead:
- Anthropic, "Building Effective Agents" — https://www.anthropic.com/engineering/building-effective-agents
- Control-flow integrity / plan-execute security — https://arxiv.org/abs/2509.08646
- LangGraph (plan-execute, ReWOO, LLMCompiler, LATS implementations) — https://github.com/langchain-ai/langgraph

Multi-agent (key claim verified by direct fetch):
- Cognition, "Don't Build Multi-Agents" (12 Jun 2025) — https://cognition.ai/blog/dont-build-multi-agents
- Cognition, "Multi-Agents: What's Actually Working" (Apr 2026) — https://cognition.ai/blog/multi-agents-working
- Anthropic, "How we built our multi-agent research system" (13 Jun 2025) — https://www.anthropic.com/engineering/multi-agent-research-system

Grounding / verification tooling:
- Self-Preference Bias in LLM-as-a-Judge — https://arxiv.org/abs/2410.21819
- promptfoo — https://github.com/promptfoo/promptfoo ; DeepEval — https://github.com/confident-ai/deepeval ; Langfuse — https://github.com/langfuse/langfuse ; Inspect (UK AISI) — https://github.com/UKGovernmentBEIS/inspect_ai
