# Improvement Proposal: Architecture

**Generated:** 2026-04-10  
**Source:** lessons.jsonl — 5 entries (0 warnings)  
**Proposed action:** Create a SKILL.md entry  
**Target:** new skill file: `skills/ARCHITECTURE.md`

## Recurring Lessons (5 occurrences)

- ℹ️ **[architecture-review]** CLAUDE.md is loaded into every future Claude session. Keeping it accurate and detailed (file map, conventions, smoke tests) eliminates all ramp-up time for AI sessions and is the highest single-leverage documentation fix.
- ℹ️ **[architecture-review]** Pi Dev Ops is a split-screen companion: Left = Claude Desktop CLI writing code; Right = Pi Dev Ops orchestrating, tracking, and pushing to Linear. It is NOT a standalone IDE. Every architectural decision should serve this companion model.
- ℹ️ **[cycle-3-audit]** All Priority 1+2 items (13 issues) completed in a single overnight session. Pattern: full-clearance sprint with no authority gates produces 10x throughput vs issue-by-issue execution.
- ℹ️ **[cycle-3-audit]** ZTE score moved 35→50 in two sprints (P1+P2). The highest leverage actions were: CLAUDE.md population (+4 pts total across sessions), evaluator tier (+2), PITER+ADW (+4), webhook triggers (+2).
- ℹ️ **[cycle-3-audit]** The sandbox IS the workspace directory (app/workspaces/{session_id}/). Each session gets an isolated clone. Sandbox enforcement = verify workspace exists before Phase 4 and refuse to run claude -p outside it.

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
```

## Review Required

This proposal was auto-generated. A human must review and apply it.
Close this Linear ticket when applied or explicitly rejected.