# ADW Template — Bug Fix

**Intent:** `bug`
**PITER keywords:** bug, fix, broken, error, crash, failing, doesn't work, not working, issue, defect, regression

---

## Workflow Steps

```
WORKFLOW: Bug Fix
1. REPRODUCE: Identify the exact failure condition
2. DIAGNOSE: Trace root cause — read logs, check recent changes
3. FIX: Apply minimal, targeted fix
4. VERIFY: Confirm the fix resolves the issue without regressions
5. COMMIT: Stage with conventional commit (fix: ...)
```

---

## Brief Template

```
Bug: [Short description of the symptom]

Reproduce:
1. [Step 1]
2. [Step 2]
3. Observe: [What goes wrong]

Expected: [What should happen]
Actual: [What currently happens]

Suspected cause: [If known — recent change, specific file, race condition, etc.]

Files to check:
- [file path 1]
- [file path 2]
```

---

## Skills Injected (auto, via `skills_for_intent("bug")`)
- `tier-worker` — targeted fix implementation
- `agentic-loop` — iterative diagnosis
- `tier-evaluator` — regression check

---

## Commit Convention
```
fix: <description of what was broken and how it was fixed>
```

Example: `fix: rate-limit _req_log memory leak — purge stale IPs every 5 min (RA-452)`

---

## Diagnostic Checklist
- [ ] Checked `session.output_lines` for error messages
- [ ] Checked recent commits for the change that introduced the bug (`git log --oneline -10`)
- [ ] Verified fix doesn't break other phases (run smoke test)
- [ ] Added regression scenario to `.harness/qa/regression-checklist.md` if novel
