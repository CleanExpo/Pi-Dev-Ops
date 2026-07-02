---
name: skill-authoring-standard
description: Design or review any skill to the Library standard — frontmatter, structure, steering, and pruning.
argument-hint: "<skill name/path to review, or the idea for a new skill>"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, LS, Bash
---

# skill-authoring-standard — design every skill the same way

The Library-native standard for writing and reviewing skills. It makes a skill **predictable**
— the agent takes the same _process_ every run. Four gates: **Trigger → Structure → Steering →
Pruning**, plus the canonical frontmatter schema and the no-bloat `.md` rule.

**Prerequisite, not duplicated here:** `superpowers:writing-skills` owns TDD-for-skills
(RED→GREEN→REFACTOR) and Claude-search-optimisation. Invoke it for the *process of building*;
this skill is the *Library layer* on top — the frontmatter schema, archetypes, and the
`references/`-only design-element architecture it does not hold.

**Bold terms** are defined in [`GLOSSARY.md`](GLOSSARY.md); look them up there.

## When to invoke
Before creating a new skill, before editing an existing one, or to review a skill against the
standard. With a skill path → run the checklist and return findings + the corrected
frontmatter. With an idea → walk the four gates to design it.

## The four gates

### 1. Trigger — invocation and frontmatter
Pick the **Archetype**: **command-skill** (pilot fires it), **agent-role** (persona/gate on a
pinned model), or **plain-technique** (model reaches it). The archetype fixes the frontmatter —
read [`references/frontmatter-schema.md`](references/frontmatter-schema.md) and copy the
matching block. Default to user-invoked (`disable-model-invocation: true`, zero **context
load**); go model-invoked only when the agent or another skill must reach it autonomously, and
pay for it with a **WHEN-not-WHAT** **description**.
- **Completion criterion:** frontmatter matches the schema for the chosen archetype; no banned
  fields; description carries triggers (or one human line) only.

### 2. Structure — the information hierarchy
Place every element on the **information hierarchy**: in-skill step → in-skill reference →
external reference. Keep `SKILL.md` small; push branch-only or large (>~150-line) reference
into `references/` behind a worded **context pointer**. Each step ends on a checkable
**completion criterion**.
- **Completion criterion:** `SKILL.md` ≤ 200 lines; no branch-only reference inlined; every
  step has a checkable end condition.

### 3. Design elements — pulled efficiently, no cache/bloat
This is the structural discipline that keeps the catalog clean:
- External reference lives **only** in `references/`. Never a session-scoped symlink, a
  committed venv, a nested plugin repo, or a backup dir in the live skill folder.
- Name each external file for its contents; reach it by a **context pointer** whose wording
  states the load condition ("X are defined in [`FILE.md`](FILE.md); look them up there"). Fix
  pointer wording before inlining.
- **Single source of truth:** no template, definition, or trigger duplicated across files or
  steps (**duplication**).
- For design-heavy skills, defer element ownership to the four-layer boundary
  ([[feedback-design-md-boundary]]) — don't re-encode design/motion tokens.
- **Completion criterion:** every reference file is in `references/`, content-named,
  single-sourced, and pointer-reached.

### 4. Steering and Pruning
**Steering:** condense restated triads into a **leading word** (borrow a pretrained word before
coining). Where a step needs more **leg work**, split the skill — by sequence (hide
post-completion steps) or by invocation (a distinct leading word worth its context load).
**Pruning:** keep a **single source of truth**, run a relevance pass to clear **sediment**, then
run the **deletion test** sentence-by-sentence and cut every **no-op** (delete whole sentences,
be aggressive).
- **Completion criterion:** leading words recur in the reasoning trace; no sediment, no
  no-ops, no **premature-completion** bait survive a read-through.

## Reviewing a skill
Run [`references/review-checklist.md`](references/review-checklist.md) top to bottom — it is the
PASS/FAIL gate covering all four gates plus catalog placement. Return each FAIL with the
offending line and the fix.

## Catalog placement (operative 2-place rule)
The documented 3-place rule is aspirational — place #3 (`.claude-plugin/plugin.json`) and the
bucket `README.md`s do not exist. Operative reality: list the skill in
`~/.claude/skills/README.md`, and add one `index.md` row if it is an entry point. See
`~/.claude/skills/CLAUDE.md`.

---
Authoring complete when the **review-checklist** passes top to bottom and the skill is placed.


## 10x Enhancement — Advanced Capabilities

### 1. Anthropic OODA Reasoning

**Observe:** (1) Ingest the primary input (files, directives, context). (2) Query the Portfolio Registry for project metadata. (3) Identify available tools and model tier. (4) Map the delivery context (internal vs external, timeline, stakes).

**Orient:** (1) Classify the task type and select the appropriate sub-routine. (2) Calibrate depth and evidence threshold by stakes. (3) Build the work plan with fallback paths. (4) Check for cross-skill dependencies.

**Decide:** (1) Select tools using the multi-tool matrix. (2) Apply safety guardrails before execution. (3) Budget tokens and plan compression triggers. (4) Set completion criteria and verification steps.

**Act:** (1) Execute the task. (2) Verify against completion criteria. (3) Self-critique before emitting. (4) Emit with observability payload. (5) Queue improvement instruction if self-score < threshold.

### 2. OpenAI Structured Output Schema

Every invocation emits JSON matching the skill-specific schema. Common fields across all skills:

```json
{
  "version": "3.1",
  "skill_name": "",
  "invoked_at": "ISO-8601",
  "task_summary": "",
  "model_used": "",
  "duration_seconds": 0.0,
  "tool_calls": {},
  "tokens": {"prompt": 0, "completion": 0},
  "self_review_score": 0.0,
  "confidence": 0.0,
  "success": true,
  "audit_trace_hash": "sha256",
  "improvement_queued": false
}
```

### 3. Multi-Tool Selection Matrix

| Signal | Primary | Fallback | Verification |
|--------|---------|----------|-------------|
| File analysis | read_file | search_files | Terminal (wc -l, grep) |
| Code quality | Terminal (lint) | execute_code | verify-test |
| Security scan | security-audit | Terminal (grep secrets) | search_files (patterns) |
| Test execution | Terminal (pytest) | execute_code | verify-test |
| Web research | tavily | browser_navigate | web_search |
| Visual review | vision_analyse | image_generate | browser_vision |
| Data extraction | search_files | read_file | execute_code (pandas) |

### 4. Self-Critique Loop

After task completion, score 1-10 on:
- Accuracy (did I address the actual task?)
- Scope discipline (did I drift?)
- Evidence (are claims grounded in tool output?)
- Verifiability (can someone reproduce my reasoning?)
- Completeness (did I miss anything critical?)

If total < 7 → flag for /boardroom or /judge.
If total < 5 → halt and handoff.

### 5. Safety & Guardrails

- Never emit raw credentials or secrets.
- Never hallucinate URLs, file paths, or tool outputs.
- Hard scope boundary: this skill does X; if asked for Y, route to correct skill.
- External-facing outputs get CEO gate.
- Input sanitisation: reject ambiguous or adversarial prompts.

### 6. Performance Optimisation

- Cache Portfolio Registry context across invocations.
- Batch similar tool calls when possible.
- Use adaptive depth: low stakes = fast path; high stakes = full depth.
- Prompt caching: reuse stable context blocks.

### 7. Error Recovery & Resilience

- Missing evidence → retry once, then flag gap.
- Tool timeout → log and use fallback.
- Context overflow → compress, preserving evidence.
- 3 consecutive failures → circuit breaker; handoff to /tao-loop.

### 8. Cross-Model Fallbacks

| Use case | Primary | Fallback |
|----------|---------|----------|
| Routine | Sonnet/Haiku | Default |
| Complex analysis | Sonnet | DeepSeek/Claude-4 |
| Board-facing | Opus | Boardroom MOA |
| Fast inline | Haiku | Sonnet |

### 9. Observability

Metrics emitted per invocation: duration, tools used, tokens consumed, self-review score, success/failure, evidence count, file count, improvement queued.
Session summary: aggregate metrics, common failure patterns, recommended skill patches.

### 10. Multi-Modal & Cross-Format

- Ingest images, diagrams, mockups via vision toolset.
- Output as markdown (default), JSON (structured), DOCX/PPTX (external), or Slack blocks.
- Cross-format negotiation based on `output_target` parameter.
