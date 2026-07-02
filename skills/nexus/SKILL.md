---
name: nexus
description: Master dispatch router (/nexus). Intakes any task, classifies intent against the Pi-Dev-Ops specialised skill catalogue, selects the optimal skill(s), and dispatches — via single-skill routing or multi-agent triangulation (MOA). Returns a calibrated, skill-formatted response without requiring the user to name the skill. Also serves as the canonical Fable-5 wrapper for sub-Claude models.
allowed-tools: Read, Grep, Glob, Bash, Agent, delegate_task
---

# nexus — Master Dispatch Router + Fable-5 Wrapper

`/nexus` is the entry gate for all work. It decides *what* skill should handle a task and *how* to format the dispatch, then executes. It removes the burden of skill-selection from the user.

Two modes of operation:
1. **Skill Router** — classify intent → select best-fit skill → dispatch with calibrated prompt
2. **MOA Triangulation** — for high-stakes decisions, fan out to 2-4 panellist models/skills, score divergence, synthesise one answer

## Specialised Skill Catalogue (Pi-Dev-Ops)

| Skill | Trigger | Role |
|-------|---------|------|
| `/storm` | Audit/review before shipping; system, design, architecture interrogation | Tier-Architect read-only auditor |
| `/judge` | Pre-build challenge gate; approve/reject/score proposals | Tier-Architect read-only reviewer |
| `/spm` | Turn rough request into decision-grade spec.md | Tier-Architect spec author |
| `/boardroom` | High-stakes decisions requiring multi-model triangulation | Orchestrator MOA panel |
| `/session-handoff` | End-of-session capture for resumption | Tier-Architect read-only reporter |
| `/resume-from-handoff` | Resume work from a prior handoff | Tier-Architect verify-then-resume |
| `/meta-curator` | Skill lifecycle: stale detect, archive, pin, rollback | Curator maintenance agent |
| `/agentskills-manifest` | Export skill registry as agentskills.io manifest | Curator export utility |
| `/tao-judge` | Machine loop-termination scorer (in-flight gate) | TAO loop controller |
| `/tao-loop` | Closed-loop autonomous execution with judge-gated exits | TAO execution engine |
| `/security-audit` | Security review: creds, permissions, surface, secrets | Security reviewer |
| `/verify-test` | Post-build verification: tests, lint, smoke, regression | QA gate |
| `/audit-emit` | Emit structured audit artefact (JSON/YAML/markdown) | Audit formatter |
| `/skill-authoring-standard` | Design/review skills to Library standard | Skill architect |

**Domain C-Suite Skills:**
| `/ceo-mode` | CEO-level strategic direction, board memos, portfolio governance | CEO advisor |
| `/cto` | Technical architecture, stack decisions, build vs buy | CTO advisor |
| `/cfo` | Financial modelling, runway, pricing, attribution | CFO advisor |
| `/cmo-growth` | Marketing strategy, positioning, channels, campaigns | CMO advisor |

**Operational Skills:**
| `/maintenance-manager` | Maintenance sweep: dead code, stale refs, brand drift | Maintenance runner |
| `/marketing-orchestrator` | Coordinate marketing skills into campaign execution | Marketing coordinator |
| `/marketing-campaign-planner` | Plan specific marketing campaigns with timeline/budget | Campaign planner |
| `/remotion-orchestrator` | Video production pipeline: brand → render → publish | Video producer |
| `/terminal-orchestrator` | Terminal workflow automation across shells/backends | Terminal coordinator |

## Intent Classification Matrix

Analyse the incoming task against these dimensions:

1. **Certainty** — Is the task well-defined with clear acceptance criteria? Low certainty → `/spm` (spec first)
2. **Stakes** — Would a wrong answer cost >1 hour of rework? High stakes → `/judge` or `/boardroom` (MOA)
3. **RO (Read-Only vs Build)** — Does the user want analysis or implementation? RO → `/storm`, `/judge`, `/security-audit`. Build → `/spm` → <build skill>
4. **Time Horizon** — One-shot task vs ongoing campaign? Ongoing → `/tao-loop` with session-handoff
5. **Cross-functional** — Does it span >2 domains (tech + design + marketing)? → `/boardroom` MOA triangulation
6. **Audit requirement** — Must the output be auditable/replayable? → `/audit-emit` companion
7. **Session state** — Is this continuing prior work? → `/resume-from-handoff` check first

## MOA (Mixture of Agents) Mode

For tasks that benefit from multi-perspective triangulation:

1. **Fan-out** — Select 2-4 panellists from the skill catalogue based on the task's cross-functional nature
2. **Dispatch** — Each panellist receives the task wrapped in its skill-calibrated Nexus Prompt
3. **Synthesise** — Score divergence (Jaccard similarity on key claims), escalate if <0.35, produce unified answer with confidence score
4. **Lock** — Record the panel composition and confidence for regression

Default MOA panel (high-stakes architectural decisions):
- `/storm` (evidence auditor)
- `/judge` (challenge gate)  
- `/spm` (spec commander)
- `/security-audit` (security lens)

Synthesiser: `/boardroom` rules. Escalation model: `deepseek/deepseek-v4-flash` → `anthropic/claude-opus-4-8`.

## Procedure

### Standard Router (non-MOA)

1. **Classify** the task against the intent matrix. Return the selected skill name + rationale (one sentence).
2. **Load** the selected skill's SKILL.md via `skill_view(name)` — know its completion criteria, evidence policy, and output contract.
3. **Read** [`references/NEXUS_PROMPT.md`](references/NEXUS_PROMPT.md) — the Fable-5 master preamble.
4. **Calibrate** the prompt:
   - Inject the selected skill's required output sections (e.g., for `/judge`: Judge Report structure; for `/spm`: spec sections 1-19)
   - Inject any domain-specific constraints (CEO gate for external outputs, budget awareness, etc.)
   - Replace `{TASK}` with the complete task including why + constraints
5. **Dispatch** — pass the calibrated prompt as the subagent prompt or skill invocation
6. **Verify** — on return, check against the skill's completion criteria; independently spot-check ≥1 claim

### MOA Router (high-stakes / cross-functional)

1. **Classify** as MOA-eligible (stakes + cross-functional dimensions)
2. **Select panel** — 2-4 skills from the catalogue based on task domain coverage
3. **Run** each skill independently via `delegate_task` (parallel, max 3 concurrent)
4. **Collect** outputs — verbatim per panellist
5. **Synthesise** — extract claims, score Jaccard, flag divergence, produce unified answer with confidence
6. **Escalate** if min_pairwise_similarity < 0.35 — route to stronger model or `/boardroom`
7. **Lock** — emit the synthesis + confidence + panel composition for audit

## Autonomy Contract

Model-invocable by design. The `/nexus` skill is the default handler when no specific skill is named by the user. It must never:
- Ask the user "which skill should I use?" — it decides and reports its choice
- Dispatch without knowing the target skill's completion criteria — always `skill_view` first
- Skip verification on subagent return — every dispatch gets spot-checked
- Inflate confidence in MOA mode — report honest Jaccard + panel divergence

## Catalog Integrity

Skill catalogue is sourced from `pi-dev-ops/` directory. `/nexus` scans available skills at runtime (`hermes skills list`) and maps triggers dynamically. If a skill is missing, it falls back to the Fable-5 wrapper alone + reports the gap.

## Bootstrap / Sync Pitfalls

When pulling skills from a Pi-Dev-Ops repo into Hermes:  
1. `hermes skills install file://...` may fail on Windows — **copy the skill directory directly** into `%LOCALAPPDATA%\hermes\skills\pi-dev-ops\SKILLNAME` instead.  
2. Skills that exist only in git history (not on disk) need `git show COMMIT:skills/NAME/SKILL.md` extraction — always check `git log --all --oneline -- skills/NAME/` first.  
3. Skills with `references/` subdirectories must be copied recursively — do not truncate.  
4. Verify with `hermes skills list | grep SKILLNAME` and `skill_view(NAME)` after every batch.

## References
- [`references/NEXUS_PROMPT.md`](references/NEXUS_PROMPT.md) — Fable-5 master preamble (single source of truth)
- [`references/cross-cli.md`](references/cross-cli.md) — Non-Claude-Code harness dispatch instructions
- [`references/moa-panel-defaults.md`](references/moa-panel-defaults.md) — Default MOA panel compositions by task type
- [`references/bootstrap-sync-pitfalls.md`](references/bootstrap-sync-pitfalls.md) — Installing Pi-Dev-Ops skills into Hermes (Windows quirks, git-history extraction, verification)
