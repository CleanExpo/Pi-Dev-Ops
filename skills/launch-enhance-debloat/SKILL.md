---
name: launch-enhance-debloat
description: Make existing code stronger, leaner, and more secure without over-engineering — deletion is often the best change. Finds dead weight, weak spots on critical paths, and security issues; proposes a ranked reversible change list and applies only approved changes in a sandbox with tests passing. Use on "clean up", "remove bloat", "strengthen", "secure it", or as step 4 of /ship-it.
owner_role: Builder
status: wave-4
automation: manual
intents: enhance-debloat, debloat, dead-code, strengthen
---

# launch-enhance-debloat

Make the code that already exists get better over time — leaner, sturdier, safer — not bigger.

## Why this exists

Every line added is a line that must be reasoned about later. Following the lean single-file-agent ethos, the best change is often a *deletion*. Its unique contribution is **dead-code / de-bloat hunting** — the repo has no general dead-weight remover. For the adjacent passes it delegates: security → [`security-audit`](../security-audit/SKILL.md); UI distillation → [`design-audit`](../design-audit/SKILL.md) `/distill`. It proposes small reversible changes and applies only approved ones, in a sandbox, with the test oracle green.

## Triggers

- "clean up", "remove bloat", "strengthen", "secure it", "make it better".
- Step 4 of [`ship-it`](../ship-it/SKILL.md) (propose-only at that stage).
- Continuous-improvement cron runs.

## Method

1. **Find dead weight (cheap model).** Unused exports/files/deps — dashboard (TS): `knip`, `ts-prune`, `depcheck`; backend (Python): `vulture`, `ruff`, `deptry`. Plus duplicated logic, dead branches, commented-out code. Propose removals.
2. **Find weak spots.** Missing error handling on critical paths (auth, session lifecycle, Supabase writes), unvalidated input, race conditions, silent failures. Note: `app/server/supabase_log.py` writes must stay non-blocking; `app/server/persistence.py` must keep its atomic write-then-replace.
3. **Security pass — delegate to [`security-audit`](../security-audit/SKILL.md).** Don't re-implement OWASP/secret-scanning here; invoke `security-audit` and act on its CVSS-scored findings (exposed secrets, missing auth checks, cross-user Supabase access, vulnerable deps via `pip-audit`/`npm audit`). Never read or write `.env*` files.
4. **Propose, don't auto-apply.** Output a ranked list: `Change | Type (remove/strengthen/secure) | File | Risk if untouched | Effort`. One concern per change, each small and reversible. Save to `.harness/audits/enhance-<YYYY-MM-DD>.md`.
5. **Apply only approved changes, in a sandbox.** Stay within `max_files_modified: 5`. If a critical path lacks a test, write the test FIRST. Run `python -m pytest tests/ -x -q` (and `npx tsc --noEmit && npm run build` for dashboard) — must exit 0. Commit each change separately. ⚠️-tier files need evaluator ≥ 8/10; 🚫-tier files are never touched without explicit human approval.

## Output

`.harness/audits/enhance-<YYYY-MM-DD>.md` — the ranked change list. Approved changes become commits on a `pidev/auto-{sid[:8]}` branch via PR; never pushed to `main`.

## Safety bindings

- Propose-only inside `/ship-it`; application is a separate, human-approved step.
- Sandbox-first; respects the 5-file ceiling and the boundary matrix tiers.
- Test-first on any untested critical path — no fake-green (RA-1109).
- Honours kill-switch and credential-rejection rails from [`launch-charter`](../launch-charter/SKILL.md).

## Verification

After each change: the test suite still passes, the feature still works on the sandbox/live site, and the diff is *smaller or no larger* than before unless new logic was genuinely required. A security finding is "resolved" only when re-scanned clean (`pip-audit` / `npm audit`).

## Out of scope

- Adding a framework, queue, or microservice to something that worked as a function — that's over-engineering; reject it.
- Bundling ten changes into one commit — small reversible commits are the safety net.
- Build-state mapping and review — see [`launch-project-audit`](../launch-project-audit/SKILL.md) and [`launch-review`](../launch-review/SKILL.md).

## References

- `AGENTS.md` — ✅/⚠️/🚫 tiers and the test/import gates.
- [`security-audit`](../security-audit/SKILL.md), [`design-audit`](../design-audit/SKILL.md) — delegated passes.
- [`tao-loop`](../tao-loop/SKILL.md) / [`tao-judge`](../tao-judge/SKILL.md) — the judge-gated loop that applies approved changes.
- [`launch-charter`](../launch-charter/SKILL.md) — sandbox + reversibility rails.
