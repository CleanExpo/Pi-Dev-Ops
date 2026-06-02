# Security / Secrets Lane Evidence — 2026-06-02

Scope: RA-3034 / RA-3012 security hardening in Pi-Dev-Ops.

## Changes

- Removed a Supabase JWT from `dashboard/index.html` and replaced it with a fail-closed empty key plus an explicit server-side-proxy requirement.
- Hardened `scripts/secrets_check.py` to detect JWT-like service tokens and OpenRouter keys.
- Redacted secret-shaped snippets before printing scanner output, Linear ticket text, or harness logs.
- Hardened `scripts/railway_check.sh` so Railway CLI failure output is masked instead of echoing raw variable lines.
- Added regression coverage in `tests/test_security_secret_guards.py`.

## Verification commands

- `uv run --with pytest python -m pytest -q tests/test_security_secret_guards.py`
- `python scripts/secrets_check.py --dry-run`
- `git grep -n "SUPABASE_KEY = 'eyJ" -- dashboard/index.html || true`
- `git log --all --oneline -- dashboard/index.html | head -20`

## Verification results

- Targeted regression tests: 2 passed.
- Current-worktree secrets scan: PASS — no exposed secrets detected.
- Current `dashboard/index.html` grep for embedded Supabase JWT: no matches.
- 3-loop gate passed: targeted regression tests + secrets dry-run + dashboard JWT grep.
- Python syntax/type-adjacent gate passed: `python -m py_compile scripts/secrets_check.py tests/test_security_secret_guards.py`.
- Shell syntax gate passed: `bash -n scripts/railway_check.sh`.
- Dashboard lint was not run because `dashboard/node_modules` is absent locally; this lane changed only static `dashboard/index.html` and fail-closed JavaScript.
- Linear was updated with evidence comments: RA-3034 and RA-3012 moved to Done; RA-2989 left open for credential rotation.
- Git history shows prior dashboard commits touched `dashboard/index.html`; exposed keys that reached remote history must still be treated as compromised and rotated under RA-2989.

## Senior-engineer recommendation

Do not mark the broader leaked-secret programme complete until credential rotation evidence exists. This lane closes the current worktree exposure and adds prevention gates; RA-2989 remains the owner for rotation / stale-token retirement.
