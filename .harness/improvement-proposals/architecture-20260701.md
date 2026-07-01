# Improvement Proposal: Architecture

**Generated:** 2026-07-01  
**Source:** lessons.jsonl — 9 entries (2 warnings)  
**Proposed action:** Create a SKILL.md entry  
**Target:** new skill file: `skills/ARCHITECTURE.md`

## Recurring Lessons (9 occurrences)

- ℹ️ **[architecture-review]** CLAUDE.md is loaded into every future Claude session. Keeping it accurate and detailed (file map, conventions, smoke tests) eliminates all ramp-up time for AI sessions and is the highest single-leverage documentation fix.
- ℹ️ **[architecture-review]** Pi Dev Ops is a split-screen companion: Left = Claude Desktop CLI writing code; Right = Pi Dev Ops orchestrating, tracking, and pushing to Linear. It is NOT a standalone IDE. Every architectural decision should serve this companion model.
- ℹ️ **[cycle-3-audit]** All Priority 1+2 items (13 issues) completed in a single overnight session. Pattern: full-clearance sprint with no authority gates produces 10x throughput vs issue-by-issue execution.
- ℹ️ **[cycle-3-audit]** ZTE score moved 35→50 in two sprints (P1+P2). The highest leverage actions were: CLAUDE.md population (+4 pts total across sessions), evaluator tier (+2), PITER+ADW (+4), webhook triggers (+2).
- ℹ️ **[cycle-3-audit]** The sandbox IS the workspace directory (app/workspaces/{session_id}/). Each session gets an isolated clone. Sandbox enforcement = verify workspace exists before Phase 4 and refuse to run claude -p outside it.
- ℹ️ **[orchestration-pattern]** Parallel agent dispatch beats sequential by ~8x for independent tasks. Dispatch multiple Agent tool calls in a single message rather than waiting for each to return. Constraint: agents must not share target files (partition by file ownership).
- ⚠️ **[orchestration-pattern]** Writing charters and plans without first reading the real system state produces orphan work. Always run a reconnaissance swarm against the actual .harness/ state BEFORE drafting new project plans. The 2026-04-11 Pi-SEO swarm lost ~2 hours to a parallel /Pi-CEO/Pi-SEO/ folder that duplicated existing .harness/ content.
- ⚠️ **[RA-1043-1049-review]** 1Password secret references (op://vault/item/field) in .env files are only resolved when the process is launched via . Python dotenv reads them as literal strings. Add a Pydantic field_validator that treats op:// values and empty strings as None so they fall through to fallback auth rather than passing an obviously-invalid credential to an API client.
- ℹ️ **[sprint-12-review]** When using 'gh pr merge' to merge a PR with branch protection, use '--merge' flag (not '--auto'). The '--auto' flag requires the repo to have 'enablePullRequestAutoMerge' setting enabled (org-level setting). '--merge' triggers an immediate merge attempt and returns a clear error if required status checks are still pending, making the failure visible and actionable.

## Proposed Content

Add a new skill or expand an existing one covering these architecture patterns:

```markdown
# SKILL: Architecture Best Practices

## When to apply
Whenever code touches architecture-related logic.

## Rules
- CLAUDE.md is loaded into every future Claude session. Keeping it accurate and detailed (file map, conventions, smoke tests) eliminates all ramp-up time for AI sessions and is the highest single-leverage documentation fix.
- Pi Dev Ops is a split-screen companion: Left = Claude Desktop CLI writing code; Right = Pi Dev Ops orchestrating, tracking, and pushing to Linear. It is NOT a standalone IDE. Every architectural decision should serve this companion model.
- All Priority 1+2 items (13 issues) completed in a single overnight session. Pattern: full-clearance sprint with no authority gates produces 10x throughput vs issue-by-issue execution.
- ZTE score moved 35→50 in two sprints (P1+P2). The highest leverage actions were: CLAUDE.md population (+4 pts total across sessions), evaluator tier (+2), PITER+ADW (+4), webhook triggers (+2).
- The sandbox IS the workspace directory (app/workspaces/{session_id}/). Each session gets an isolated clone. Sandbox enforcement = verify workspace exists before Phase 4 and refuse to run claude -p outside it.
- Parallel agent dispatch beats sequential by ~8x for independent tasks. Dispatch multiple Agent tool calls in a single message rather than waiting for each to return. Constraint: agents must not share target files (partition by file ownership).
- Writing charters and plans without first reading the real system state produces orphan work. Always run a reconnaissance swarm against the actual .harness/ state BEFORE drafting new project plans. The 2026-04-11 Pi-SEO swarm lost ~2 hours to a parallel /Pi-CEO/Pi-SEO/ folder that duplicated existing .harness/ content.
- 1Password secret references (op://vault/item/field) in .env files are only resolved when the process is launched via . Python dotenv reads them as literal strings. Add a Pydantic field_validator that treats op:// values and empty strings as None so they fall through to fallback auth rather than passing an obviously-invalid credential to an API client.
- When using 'gh pr merge' to merge a PR with branch protection, use '--merge' flag (not '--auto'). The '--auto' flag requires the repo to have 'enablePullRequestAutoMerge' setting enabled (org-level setting). '--merge' triggers an immediate merge attempt and returns a clear error if required status checks are still pending, making the failure visible and actionable.
```

## Review Required

This proposal was auto-generated. A human must review and apply it.
Close this Linear ticket when applied or explicitly rejected.