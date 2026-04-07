# ADW Template — Feature Build

**Intent:** `feature`
**PITER keywords:** add, implement, create, build, new, feature, enhance, integrate, support

---

## Workflow Steps

```
WORKFLOW: Feature Build
1. DECOMPOSE: Break the feature into discrete sub-tasks
2. BUILD: Implement each sub-task with clean, tested code
3. TEST: Run existing tests, add new tests for the feature
4. REVIEW: Self-review for correctness, security, style
5. PR: Stage changes with a clear commit message
```

---

## Brief Template

```
Feature: [Feature name]

Problem: [What is missing or insufficient today?]

Solution: [What should exist after this is done?]

Acceptance criteria:
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion 3]

Out of scope:
- [What this feature does NOT cover]

Files likely affected:
- [file path 1]
- [file path 2]
```

---

## Skills Injected (auto, via `skills_for_intent("feature")`)
- `tier-architect` — decomposition and interface design
- `tier-worker` — implementation patterns
- `tier-evaluator` — quality gate criteria
- `agent-workflow` — ADW phase sequencing

---

## Commit Convention
```
feat: <description of what was added>
```

Example: `feat: add evaluator tier to build pipeline (RA-454)`
