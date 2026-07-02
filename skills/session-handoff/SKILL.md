---
name: session-handoff
description: Durable session handoff (/session-handoff). Generate a precise handoff before stopping, switching terminals, opening a PR, handing work to another agent, or resuming later. Read-only — captures what was done, where it started, decisions locked, what shipped, key files, running state, verification commands, deferred/open questions, exact pickup point, risk notes, and a handoff quality check.
owner_role: Tier-Architect (end-of-session handoff; read-only reporter)
status: active
automation: manual
---

# session-handoff — Durable Session Handoff

Review/report only — `/session-handoff` never edits, commits, pushes, deploys, migrates,
modifies tickets, or changes external systems. It produces a handoff so another terminal
or agent can resume without rereading the whole conversation. Any mutation may only follow
a separate, explicit user request after the handoff.

Companion to `judge`: `/judge` decides *whether to build*; `/session-handoff` records
*what happened and where the next agent picks up*. Distinct from `tao-judge` (machine
loop-termination scorer).

## Input scope

Handoff scope is supplied as `$ARGUMENTS` (a ticket, branch, PR, feature, or repo area).
If empty, infer scope from the current branch, git status, recent commits, current diff,
recently changed files, conversation context, and the CLAUDE.md / AGENTS.md guidance.

## Read-only inspection

```bash
git branch --show-current
git status --short
git log --oneline -n 8
git diff --stat
git diff --name-only
```

Only run tests if the user explicitly asks for verification execution; otherwise report
the commands to run. Do not modify anything.

## Required output — Session Handoff

Produce a handoff with this exact structure (see `.session-handoff/report-template.md`):

1. Summary of what was done (attempted / completed / partial / not touched)
2. Where it started (request, branch, files, problem, constraints; `Unknown from available context` if unclear)
3. Decisions locked + what shipped (separate decisions from implementation; if nothing committed/pushed, say `Nothing shipped yet. Current work is local/session-only.`)
4. Key files (table; Status ∈ Created / Modified / Deleted / Read-only inspected / Needs review / Deferred / Unknown)
5. Running state (never claim a process is running unless verified)
6. Verification — exact commands (backend / dashboard / smoke / skill check)
7. Deferred + open questions (two separate lists, each with Owner / Blocking / Why)
8. Pick up here (`Start here` steps, `Do not redo`, and an explicit `First command to run`)
9. Risk notes (unverified assumptions, failed commands, stale context, secrets/env gaps)
10. Handoff quality check

End with: `Handoff complete. Next safe action: <one sentence>.`

## Quality rules

- Do not claim tests passed unless they were actually run.
- Do not claim anything shipped unless commit/push/merge evidence exists.
- Do not claim a process is running unless verified.
- Clearly separate completed work from deferred work.
- Always provide the first command the next agent should run.


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
