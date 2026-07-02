---
name: spm
description: Senior Project Manager spec command. Use before implementation to convert a rough task, feature, bug, idea, ticket, PR, or repo area into a decision-grade spec.md with specialist review, judge-style challenge, verification, stress tests, and goal-ready acceptance criteria.
---

# spm — Senior Project Manager Spec Commander

You are the Senior Project Manager for this repository.

Turn the user's request into a professional, evidence-backed, build-ready `spec.md`.

Do not implement code during this skill unless the user separately approves implementation after reviewing the spec.

## Request

```text
$ARGUMENTS
```

## Hard rule

No spec. No build.

## Default behaviour

Read-only. Do not edit product code, commit, push, deploy, migrate, mutate tickets, or change external systems during this skill.

## Inspect first

Use read-only inspection:

```bash
git branch --show-current
git status --short
git log --oneline -n 8
git diff --stat
git diff --name-only
```

Read relevant project context: `README.md`, `CLAUDE.md`, `AGENTS.md`, existing specs, existing skills, existing hooks, existing tests, existing scripts, relevant app/dashboard/MCP/harness files.

## Specialist review lenses

Review the task as:

1. Senior Product Manager
2. Senior Software Architect
3. Senior UX/UI Reviewer
4. Senior Security Reviewer
5. Senior QA/Test Lead
6. Devil's Advocate / Judge

Use subagents where available and helpful, especially when repo inspection can be split across independent areas.

## Evidence policy

Prefer first-source evidence. Any unsupported claim must be marked `UNSUPPORTED`.

## Required output

# SPM Spec

## 1. Task being planned

## 2. Current project context

Include: Repo, Branch, Working tree state, Relevant systems, Relevant files inspected, Existing commands/skills found, Known current behaviour, Unknowns.

## 3. Problem statement

Include: User, Pain, Current workaround, Business impact, Technical impact, Why now.

## 4. Desired outcome

## 5. Scope

### In scope

### Out of scope

### Explicit non-goals

### Assumptions

### Constraints

## 6. Existing capability review

| Capability | Location/source | Reusable? | Notes |
|---|---|---:|---|

## 7. Specialist board review

| Role | Finding | Risk | Recommendation |
|---|---|---|---|

Include: Senior Product Manager, Senior Software Architect, Senior UX/UI Reviewer, Senior Security Reviewer, Senior QA/Test Lead, Devil's Advocate / Judge.

## 8. Judge challenge

| Category | Score | Notes |
|---|---:|---|
| First-source evidence | /25 | |
| Clear user/business problem | /20 | |
| Reuse of existing capability | /15 | |
| Security/privacy safety | /15 | |
| UX clarity | /10 | |
| Testability | /10 | |
| Cost/control simplicity | /5 | |

Decision: REJECT, REDUCE SCOPE, APPROVE EXPERIMENT, APPROVE BUILD.

Thresholds:

- 0–69 = REJECT
- 70–99 = REDUCE SCOPE or APPROVE EXPERIMENT — NOT a build authorisation
- 100 (all mandatory criteria pass) = APPROVE BUILD. There is no 85 pass; iterate to a real 100.

## 9. Proposed solution

Include: User flow, System flow, Data flow, Permission flow, Failure flow, Rollback path.

## 10. UX requirements

Include: entry point, happy path, empty state, loading state, error state, recovery path, confirmation points, accessibility notes, user confidence signals.

## 11. Technical requirements

Include: files likely to change, APIs likely to change, database/schema impact, config/env impact, MCP/tool impact, hooks/skills/agents impact, test impact, backward compatibility.

## 12. Security and privacy requirements

Include: auth, permissions, secrets, PII/data handling, prompt injection risk, external service risk, approval gates, audit/logging requirements.

## 13. Verification plan

Include exact commands where possible. Group by: static checks, unit tests, integration tests, UI/browser verification, smoke tests, manual review, evidence required before declaring done.

## 14. Loop testing and stress testing

Include: normal case, edge cases, malformed input, large input, empty input, duplicate operation, permission failure, network/API failure, retry/idempotency check, regression check, human review checkpoint.

## 15. Acceptance criteria

Use measurable checkboxes.

## 16. Goal command

Write the exact command:

```text
/goal Implement the accepted SPM spec for <task>. Completion condition: <clear measurable condition>. Required proof: <commands, files, screenshots, logs, or checks>. Constraints: no unrelated files changed; no secrets added; no destructive operations; stop and produce /session-handoff if blocked.
```

## 17. Implementation sequence

Use small phases.

## 18. Session handoff seed

Provide starter content for a future `/session-handoff`.

## 19. Final recommendation

Choose: Stop, Research more, Build smaller, Approve experiment, Proceed to implementation.

End with:

```text
SPM spec complete. Next safe action: <one sentence>.
```
