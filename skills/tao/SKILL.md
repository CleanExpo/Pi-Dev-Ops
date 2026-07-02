---
name: tao
description: The Tao is the autonomous execution engine that ties self-direction with governance. It orchestrates /nexus (routing), /tao-loop (iterate-generate-deploy), /tao-judge (iterative-evaluator-calibrator), and /session-handoff (continuity/escrow) into a single cohesive autonomous mission-runner. The Tao handles autonomous overnight execution for complex projects.
allowed-tools: Read, Grep, Glob, Bash, Agent, delegate_task, skill_view, hermes_cli
---

# tao — Autonomous Execution Engine

The Tao is the synthesis of four subsystems:
- **/nexus** — Master dispatch router: decides what skill should handle a task
- **/tao-loop** — Iterate, generate, deploy with persistent checkpointing
- **/tao-judge** — Iterative evaluator / calibrator / grader-gate
- **/session-handoff** — Continuity / escrow for state persistence across sessions

## When to invoke

- The user says "run this autonomously" or "handle this overnight"
- A task spans >1 skill or >1 domain and requires closed-loop execution
- Prior work exists that needs resumption via /resume-from-handoff
- The user grants 100% authority for exhaustive autonomous action

## Invocation Contract

Input: `{prayer.field, prayer.layer, prayer.operator, prayer.objective, prayer.subject, prayer.context}`
Derivation from user request:
- `field`: work_area_group (e.g., "RestoreAssist", "Unite-Hub", "Marketing", "Portfolio")
- `layer`: execution_depth (routine | complex | board-critical)
- `operator`: action_type (build | audit | research | deploy | maintain)
- `objective`: primary_deliverable (e.g., "ship the auth refactor", "audit all env vars")
- `subject`: target_entity (project, repo, feature, or "across all projects")
- `context`: freeform constraints, prior handoff ID, budget, timeline

## Execution Algorithm

Define: `tao(prayer)`

### Phase 1 — Initiation (TAO-Start)

1. **Hydrate state** — check for prior handoff via /resume-from-handoff
2. **Classify** — /nexus routes the prayer to the primary skill(s)
3. **Load** — `skill_view(primary_skill)` to calibrate output contracts
4. **Budget** — estimate tokens, set TERMINAL TRIGGER, COMPACTION THRESHOLD
5. **Emit prayer hash** — `prayer_hash = sha256(prayer)` for audit trace

### Phase 2 — Execution Loop (TAO-Loop)

While prayer.layer not satisfied:

1. **ACT** — Execute the next step using the routed skill(s)
2. **CHECKPOINT** — Persist state: files written, git state, tokens consumed, evidence URLs
3. **JUDGE** — /tao-judge evaluates the ACT output
4. **TERMINAL TRIGGER CHECK**
   - If judge_score >= threshold AND all must-haves pass → Phase 3
   - If max_loops reached → Phase 3 (with partial flag)
   - If anomaly detected AND anomaly_score >= 0.4 → Phase 4 (ESCROW)
   - If token budget critical (<10%) → COMPACT + continue

### Phase 3 — Conclusion (TAO-End)

1. **EMIT** — Final deliverable in the format requested (or the skill's native format)
2. **AUDIT** — /audit-emit produces the structured JSON audit trace
3. **HANDOFF** — /session-handoff captures:
   - What was done
   - What shipped
   - What remains
   - Exact pickup point for next session
   - Verification commands
4. **IMPROVE** — Every execution produces improvement instructions:
   - What worked well
   - What was slow / expensive
   - What the skills got wrong
   - Recommended patches to relevant skill SKILL.md files
5. **QUEUE** — Improvement instructions stored in `tao_improvement_queue` for periodic review via /meta-curator

### Phase 4 — Escrow (TAO-Stop)

Triggered by: anomaly_score >= 0.4, external stop, manual intervention request, or unresolvable contradiction.

1. **HALT** all execution immediately
2. **PAUSE** state: preserve checkpoints, context canvas, evidence URLs
3. **ESCALATE** to /boardroom with full trace
4. **HANDOFF** the pause state for human review
5. **LOCK** the prayer hash; resume requires explicit re-invocation

## Self-Improvement Loop

The Tao is not just an executor — it is a learner.

After every TAO-End:
1. **Analyse** the execution trace for patterns
2. **Extract** skill-specific improvement notes (e.g., "/judge missed this edge case")
3. **Batch** improvement notes per skill
4. **When** a skill accumulates >3 improvement notes → auto-emit a patch proposal to /meta-curator
5. **When** a patch is accepted → update the skill SKILL.md and increment the skill version
6. **When** >5 patches accepted in a session → emit a Tao system upgrade note

## Observability Contract

Every Tao session emits:

```json
{
  "tao_session_id": "",
  "prayer_hash": "sha256",
  "phases": [
    {"phase": "TAO-Start", "timestamp": "", "duration_seconds": 0.0},
    {"phase": "TAO-Loop", "timestamp": "", "loops": 0, "avg_judge_score": 0.0, "duration_seconds": 0.0},
    {"phase": "TAO-End", "timestamp": "", "duration_seconds": 0.0},
    {"phase": "TAO-Improvement", "timestamp": "", "improvements_queued": 0}
  ],
  "primary_skill": "",
  "skills_invoked": [],
  "files_changed": [],
  "git_commits": [],
  "audit_trace_hash": "",
  "handoff_id": "",
  "improvement_queue": [],
  "terminal_reason": "success | max_loops | anomaly | manual_stop",
  "tokens_total": 0,
  "cost_estimate_aud": 0.0
}
```

## Cross-Model Fallbacks

If the primary model fails during Tao execution:
- Routine steps → fallback to Sonnet/Haiku
- Judge reviews → fallback to deeper model (Opus/Claude-4)
- MOA disagreements → fallback to Boardroom
- Escrow → always uses the strongest available model

## Autonomy Rules

1. The Tao NEVER asks "what should I do next?" — it decides and reports
2. The Tao ALWAYS handoffs before stopping — never lose state
3. The Tao ALWAYS emits an audit trace — every execution is accountable
4. The Tao ALWAYS queues improvements — every execution makes the system better
5. The Tao ALWAYS respects the CEO Board and Pi governance gate on external outputs
6. The Tao ALWAYS runs destructive operations through /judge first
7. The Tao NEVER auto-executes financial transactions, contract signings, or production deployments without explicit pass-through approval
8. The Tao treats dirty-tree / mega-diff as a trigger for lane-splitting via Kanban/cron, not a reason to stop

## References
- /nexus — Master dispatch router
- /tao-loop — Iterate-Generate-Deploy loop
- /tao-judge — Iterative evaluator
- /session-handoff — State escrow
- /resume-from-handoff — State retrieval
- /boardroom — Escalation panel
- /audit-emit — Structured audit formatter
- /meta-curator — Skill lifecycle management
