# Sandbox policy — verification isolation for /spm specs

`policy_version: 1.0` · calibrated 2026-07-10

This policy governs the **spec that /spm emits**, not spm itself (spm is read-only and
executes nothing). It binds the verification plan (§13) and loop/stress testing (§14) that
the emitted `/goal` will execute: **verification runs in isolation — containers, sandboxes,
shadow resources — never against production.**

## Mandate by tier

- **T2+**: §13–14 must state where verification runs and why that environment cannot touch
  prod (distinct URL/port/credentials, ephemeral lifecycle).
- **T3**: §13–14 **must name the container strategy explicitly** (which image/compose file/
  branch-DB mechanism), including the guard that makes a prod connection impossible
  (e.g. "globalSetup hard-fails unless DATABASE_URL port = 5499").
- Any verification step that must touch prod (e.g. a live smoke after deploy) is
  autonomy-ladder **L3** → it becomes a human-gated acceptance criterion in §15, never an
  autonomous step.

## Decision table — pick by project shape

| Project shape | Isolation strategy |
|---|---|
| Has Dockerfile / docker-compose | Ephemeral compose env (dedicated `*.test.yml`, non-default ports, tmpfs data, healthchecks; `--wait` then run; `down -v` after) |
| Node service, no compose | testcontainers (or a dedicated test compose added by the spec) for pg/redis/queues; unit layer mocks stay as-is |
| DB migration involved | Shadow/branch database (Supabase branch, throwaway container DB, or `db push` into an ephemeral instance); NEVER `migrate`/`db push` against a live URL; migration files land create-only, apply is a human gate |
| Frontend / web app | Preview deploy (never the prod alias) + Playwright against the preview URL; visual/e2e evidence attached |
| CLI / library | Temp-dir sandbox (`$TMP`-scoped fixtures), no writes outside the sandbox path |
| External APIs (social, payment, LLM) | Recorded fixtures / mock server in tests; live-key smoke only as an L3 human-gated criterion |

## Escape hatch — when no sandbox is possible

If genuinely no isolation exists for a step (rare), the spec must say so explicitly and:
1. classify every claim that step would have proven as `observed, not proven`
   (proof-discipline classes), never `proven`;
2. gate the affected acceptance criteria on a human-run check in §15;
3. have the judge seat treat the gap as a standing must_fix — APPROVE BUILD 100/100
   requires either the sandbox or the explicit human gate, never silence.

## Receipt

§13 states, in one line each: environment name, isolation mechanism, prod-impossibility
guard, teardown. The qa-verification-lead seat owns checking this at T2+; ops-cost-realist
checks teardown/cost.
