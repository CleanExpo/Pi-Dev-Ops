# Generator Agent — Tier 2 Specification

**Role:** Worker. Executes individual `TaskSpec` items via `claude -p` subprocess. Produces code, commits, and `TaskResult` objects.

**Model:** `claude-sonnet-4-6` (speed + capability balance for implementation tasks)

**Responsibilities:**
1. Receive a `TaskSpec` with description, context, and expected_output
2. Build a structured prompt incorporating:
   - ADW workflow steps for the intent
   - Relevant skills from the skill registry (via `skills_for_intent()`)
   - Repo-specific context from CLAUDE.md
3. Spawn `claude -p {spec} --model sonnet --output-format stream-json` in the workspace
4. Parse stream-json events and populate `TaskResult`
5. Stage and commit changes with conventional commit message
6. Return `TaskResult` to orchestrator

**Inputs:**
- `TaskSpec` (from Planner)
- Workspace path (cloned repo directory)
- Skill context (injected by brief.py)

**Outputs:**
- `TaskResult` with content, success flag, tokens_used, duration_seconds
- Git commit in workspace

**Constraints:**
- Max token budget: set by `BudgetTracker` allocation
- Must never run outside a sandboxed workspace directory (RA-468)
- On failure: return `TaskResult(success=False)` — never retry autonomously more than once

**Config reference:** `.harness/config.yaml` tier: `generator`
