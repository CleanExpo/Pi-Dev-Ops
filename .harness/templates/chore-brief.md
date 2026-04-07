# ADW Template — Chore / Maintenance

**Intent:** `chore`
**PITER keywords:** chore, cleanup, refactor, rename, update deps, upgrade, lint, format, migrate, move

---

## Workflow Steps

```
WORKFLOW: Chore
1. APPLY: Make the maintenance change (refactor, rename, upgrade)
2. LINT: Run linters and formatters
3. TEST: Verify nothing broke
4. COMMIT: Stage with conventional commit (chore: ...)
```

---

## Brief Template

```
Chore: [Short description — refactor X, rename Y, update Z]

Scope:
- Files affected: [list files or directories]
- Change type: refactor | rename | upgrade | cleanup | format | migrate

Why now:
- [Technical debt reason, compliance requirement, or maintenance window]

Constraints:
- Must not change external behaviour
- Must not break existing tests
- [Any other constraints]
```

---

## Skills Injected (auto, via `skills_for_intent("chore")`)
- `tier-worker` — mechanical implementation
- `agent-workflow` — ADW phase sequencing

---

## Commit Convention
```
chore: <description of what was maintained>
```

Examples:
- `chore: add pg devDependency (used for migration scripting)`
- `chore: reset CLAUDE.md to minimal stub template`

---

## Safety Checks
- [ ] No functional behaviour changed (pure refactor)
- [ ] All imports still resolve after rename
- [ ] Server starts cleanly after upgrade
- [ ] Smoke test checklist passes end-to-end
