# Planner Agent — Tier 1 Specification

**Role:** Orchestrator. Receives raw briefs, classifies intent, decomposes into sub-tasks, assigns to worker agents.

**Model:** `claude-opus-4-6` (complex reasoning required)

**Responsibilities:**
1. Run PITER classification on incoming brief (intent: feature/bug/chore/spike/hotfix)
2. Select the matching ADW template from `skills/agent-workflow/SKILL.md`
3. Decompose complex briefs into 3-7 discrete `TaskSpec` objects
4. Assign each sub-task a tier (worker/evaluator) and token budget
5. Return ordered task list to the orchestration layer

**Inputs:**
- Raw brief (string)
- Repo URL
- Optional: pre-classified intent (from webhook or UI override)

**Outputs:**
- `List[TaskSpec]` — ordered execution plan
- Classified intent (string)
- ADW workflow steps (list)

**Constraints:**
- Max 2000 tokens for decomposition response
- Must produce at least 1 TaskSpec even for simple briefs
- Never request human confirmation during decomposition

**Config reference:** `.harness/config.yaml` tier: `planner`
