# Open-source capability catalog — verified 2026-07-10

What exists in the open ecosystem for build/design/generate work, what license it carries, and how it lands on a Pi-Dev-Ops node. The Agent Skills standard lives at agentskills.io; skills.sh indexes distributions.

## Tier 1 — install on every node

**anthropics/skills** (~160k★) — the official Agent Skills repo.
- Creative/design: `frontend-design`, `canvas-design`, `theme-factory`, `brand-guidelines`, `algorithmic-art`, `web-artifacts-builder` — Apache 2.0.
- Documents: `docx`, `pptx`, `xlsx`, `pdf` — source-available (production skills behind Claude's file creation), reference-grade.
- Meta: `skill-creator`, `mcp-builder`, `internal-comms`.
- Install: `/plugin marketplace add anthropics/skills` → `document-skills` + `example-skills`. Already native on claude.ai paid plans.

**obra/superpowers** (~250k★) — the elicitation prior art.
- `brainstorming` is the canonical "grill-me": hard gate before implementation, one question at a time, multiple-choice preferred, 2–3 approaches with a recommendation, spec self-review, explicit user approval gate.
- creative-director deliberately **compresses** this: their 9-step interview suits software specs; our one-screen checkbox grill suits creative deliverables. Borrow the gate + multi-choice mechanics, not the length.
- Also worth pulling: `writing-plans`, TDD/debugging skills for the engineering fleet.

## Tier 2 — persona & division library (cherry-pick)

**msitarzewski/agency-agents** (~130k★, MIT) — 230+ persona agents with personality, workflow, and deliverables per agent.
- Design division maps straight onto our style/persona layer: UI Designer, Brand Guardian, Visual Storyteller, Whimsy Injector, Image Prompt Engineer, Inclusive Visuals Specialist, **Persona Walkthrough Specialist** (persona-driven cognitive walkthroughs — the QA twin of our step 2).
- Also useful: Document Generator, Reality Checker (evidence-based release gate), Executive Summary Generator, PR & Comms Manager.
- Install: `./scripts/install.sh --tool claude-code --division design` (their installer is itself a checkbox UI). MIT = adapt freely; keep attribution as courtesy.

**garrytan/gstack** (~120k★) — 23 role tools (CEO / Designer / Eng Manager / QA / Release / Docs). Same role-lens philosophy as our `launch-review`; mine it for lens prompts rather than installing wholesale.

**mattpocock/skills** (~160k★) — engineering-craft skills; fleet-relevant, not creative-pipeline-relevant.

**affaan-m/ECC** (~230k★) — agent-harness optimisation (skills, instincts, memory, security). Relevant to Pi-Dev-Ops meta-layer, not to this pipeline; evaluate separately.

## Generation surface

**artlist-mcp** (in-house skill, official remote server `https://mcp.artlist.io/mcp`) — 100+ image/video models (Nano Banana, Seedance 2.0, Kling, Gemini Omni Flash). No open-source alternative exists (re-verified this date); credit spend gated by charter. This is the only sanctioned media-generation surface in the stack.

## Adoption rules

1. Nothing above is forked into consuming repos — install via each source's mechanism; wrap behaviour differences in thin Pi-Dev-Ops skills like this one.
2. License check before commercial embedding: Apache 2.0 and MIT are clear; anthropics document skills are source-available reference — use the shipped product capability, don't redistribute the source.
3. Re-verify this catalog quarterly; the ecosystem moved from ~500 to >10,000 public servers/skills inside a year, so staleness is the default.
