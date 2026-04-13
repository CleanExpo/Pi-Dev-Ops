# CCW-CRM Code Quality Remediation — 2026-04-13

**Repo:** `CleanExpo/CCW-CRM`  
**Score:** 50/100 → target 90/100  
**Findings:** 50 ruff lint violations  
**Source:** Pi-SEO scan 2026-04-12-code_quality.json  
**Linear:** RA-690

---

## Finding breakdown

| Code | Count | Description | Fixable |
|------|-------|-------------|---------|
| E501 | 26 | Line too long (>100 chars) | Manual wrapping |
| UP007 | 9 | Use `X \| Y` for type annotations (Python 3.10+) | `ruff --fix` |
| I001 | 5 | Import block un-sorted | `ruff --fix` |
| E402 | 3 | Module-level import not at top | Manual |
| UP035 | 3 | Import from `collections.abc` instead of `collections` | `ruff --fix` |
| F403 | 2 | Wildcard import (`import *`) | Manual removal |
| E741 | 1 | Ambiguous variable name `l` | Manual rename |
| W291 | 1 | Trailing whitespace | `ruff --fix` |

---

## Remediation brief for Pi-CEO build session

```
Repo: https://github.com/CleanExpo/CCW-CRM
Intent: chore

Fix all 50 ruff code quality violations detected by Pi-SEO scanner on 2026-04-12.

AUTOMATED FIXES (run first):
  ruff check . --select=UP007,I001,UP035,W291 --fix
  ruff check . --select=E501 --fix --line-length=100

MANUAL FIXES (after automated):
1. E402 (3 occurrences): Move module-level imports to the top of each file.
   Common cause: imports inside try/except blocks or after sys.path manipulation.
   Fix: move the import up, or add # noqa: E402 if the position is intentional.

2. F403 (2 occurrences):
   - src/db/demo_models.py: replace `from src.db.demo_models import *` with explicit imports
   - src/db/inventory_models.py: replace wildcard import with explicit imports
   Run `ruff check --select=F403 .` to find exact locations.

3. E741 (1 occurrence): rename ambiguous variable `l` to a descriptive name.

4. E501 remaining: wrap lines > 100 chars that ruff cannot auto-fix
   (typically long strings, URLs, or complex expressions).

QUALITY GATE:
After all fixes, run:
  ruff check . --select=E,F,W,I
The output must be empty (zero violations) before committing.

Target: score 90+/100 on next Pi-SEO scan cycle.
```

---

## Expected score after remediation

| Type | Current | Fixed | Target |
|------|---------|-------|--------|
| Auto-fixable (UP007, I001, UP035, W291) | 18 violations | 0 | done |
| Manual (E402, F403, E741) | 6 violations | 0 | done |
| E501 (partial auto-fix) | 26 violations | ~5 | <5 remaining |
| **Overall** | **50/100** | — | **90/100** |
