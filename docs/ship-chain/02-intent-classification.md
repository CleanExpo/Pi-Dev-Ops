# 02 — Intent Classification

Before Pi-CEO writes a single line of code, it classifies the brief into one
of five categories. The category determines which workflow template Claude
follows — and therefore which steps appear in the generator prompt.

---

## PITER categories

| Intent | What it means | Example briefs |
|--------|--------------|----------------|
| `hotfix` | Production is broken right now | "site is down", "p0 crash", "emergency" |
| `bug` | Defect to diagnose and fix | "login fails on mobile", "crash in checkout" |
| `chore` | Maintenance: cleanup, upgrade, rename | "upgrade lodash", "rename UserService" |
| `spike` | Research, prototype, benchmark | "investigate redis caching", "compare libraries" |
| `feature` | New behaviour to build | "add dark mode", "implement OAuth", "create report" |

---

## How classification works

`classify_intent()` checks the brief against keyword lists in priority order:

```
hotfix → bug → chore → spike → feature
```

Priority matters. "feature" keywords (`add`, `build`, `create`) appear in
everyday language — if checked first they would swallow chore and spike briefs.
Checking them last makes "feature" a safe fallback.

```python
# app/server/brief.py

_INTENT_KEYWORDS = {
    "hotfix": ["hotfix", "urgent fix", "production down", "p0", "emergency"],
    "bug":    ["bug", "fix", "broken", "error", "crash", "regression", ...],
    "chore":  ["chore", "refactor", "rename", "upgrade", "lint", "migrate", ...],
    "spike":  ["research", "investigate", "explore", "prototype", "benchmark", ...],
    "feature":["add", "implement", "create", "build", "new", "feature", ...],
}
```

---

## ADW workflow templates

Each category maps to an Agent Developer Workflow (ADW) template. The template
generates the `WORKFLOW:` section in the generator prompt.

**Feature:**
```
1. DECOMPOSE  — break the feature into discrete sub-tasks
2. BUILD      — implement each sub-task with clean, tested code
3. TEST       — run existing tests, add new tests for the feature
4. REVIEW     — self-review for correctness, security, style
5. PR         — stage changes with a clear commit message
```

**Bug:**
```
1. REPRODUCE  — identify the exact failure condition
2. DIAGNOSE   — trace root cause — read logs, check recent changes
3. FIX        — apply minimal, targeted fix
4. VERIFY     — confirm the fix resolves the issue without regressions
5. COMMIT     — stage with conventional commit (fix: ...)
```

**Hotfix** is identical to Bug but with `PRIORITY: URGENT` prepended,
signalling that speed > perfection.

**Chore:** APPLY → LINT → TEST → COMMIT  
**Spike:** RESEARCH → SUMMARISE → RECOMMEND (writes to `.harness/spike-<topic>.md`)

---

## Brief complexity tier (RA-681)

After intent classification, the brief is also classified for complexity:

| Tier | When triggered | What changes |
|------|---------------|--------------|
| `basic` | Trivial keywords (typo/rename) AND <30 words | Minimal 500-token spec, simple checklist |
| `detailed` | Default | Standard 1200-token spec with skills + lessons |
| `advanced` | Architecture/security/migration keywords, or >100 words | Extended 1800-token spec with confidence target + risk register |

This controls how much context is prepended — basic briefs don't need 3000
tokens of strategic intent injected before Claude can fix a typo.

Source: `app/server/brief.py::classify_brief_complexity()`

---

## Next

[03 — The Evaluator](03-the-evaluator.md): how the second-pass scoring works,
what the four dimensions measure, and how confidence routing extends pass/fail.
