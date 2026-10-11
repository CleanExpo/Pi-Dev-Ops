Moved from SKILL.md. Read when closing out or re-verifying the runner, or checking what is out of scope.

## Verification (Wave 5 #1 close-out)

1. **Compile + import smoke** — `python -m py_compile app/server/sandcastle_runner.py` green.
2. **Dry-run mode** — invoke with `dry_run=True, sandbox="noSandbox", agent="claudeCode"`. Sandcastle must:
   - return `status="ok"`
   - produce `branch` non-empty
   - have ≥1 entry in `commits`
   - leave ZERO env-var names in `session.logs` after a `grep -E '[A-Z_]+_(KEY|TOKEN|SECRET|PASSWORD)\s*[=:]'`
   - emit ≥3 audit rows (`started`, `env_resolved`, `ok`)
3. **Kill-switch refusal** — set `TAO_SANDCASTLE_ENABLED=0`, call `run_sandcastle()` → returns `status="skipped"`, `skip_reason="sandcastle_disabled"`. No subprocess launch.
4. **Concurrency cap** — fire 4 simultaneous calls → first 3 launch, 4th returns `status="skipped"`, `skip_reason="concurrency_cap"`.
5. **Timeout** — set `timeout_minutes=0.05` (3 s), kick off a long-running prompt → returns `status="timeout"`, subprocess gone within 8 s of timeout fire.
6. **Stdout secret-strip** — synthetic Sandcastle stdout containing `ANTHROPIC_API_KEY=sk-ant-fake-key-for-test` → after `regex_strip_secrets`, the line in `session.logs` reads `ANTHROPIC_API_KEY=***=[REDACTED]` or equivalent. ZERO key-shape strings in logs.

## Out of scope for Wave 5 #1

- Real Vercel-sandbox-provider wire-up (Wave 5 #2 manifest needs to land first)
- TMPFS / FIFO secret injection design details (Wave 5 #3 — `_resolve_env_manifest` is a stub here that returns `{}` until #2/#3 land)
- Margot bridge (Wave 5 #4)
- session_phases.run_build branch point (Wave 5 #6)

This skill ships the contract + the subprocess + the audit. The plumbing on either side comes in subsequent tickets.
