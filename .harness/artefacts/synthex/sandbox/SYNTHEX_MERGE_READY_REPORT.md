# Synthex merge-ready report

Generated: 2026-05-24
Repo: `/Users/phillmcgurk/Pi-CEO/.harness/artefacts/synthex/sandbox/Synthex`
Branch at report time: `main...origin/main`

## Changes prepared

1. Dependency/security repair
   - Added npm overrides for transitive advisories:
     - `@prisma/dev` -> `@hono/node-server@1.19.14`
     - `node-polyfill-webpack-plugin@4.1.0`
   - `npm audit --omit=dev` now reports `found 0 vulnerabilities`.
   - Note: `npm ci` still reports 7 low severity dev/dependency-tree vulnerabilities and recommends `npm audit fix`; production/omit-dev audit is clean.

2. Readiness health false-positive repair
   - File: `app/api/health/ready/route.ts`
   - Root cause: readiness memory check used `heapUsed / heapTotal`, which is noisy in local/serverless runtimes because V8 grows heapTotal lazily. This caused readiness degradation even when RSS was acceptable.
   - Fix: align readiness memory semantics with main `/api/health`: only RSS against `AWS_LAMBDA_FUNCTION_MEMORY_SIZE` affects memory status; local/no-limit runtimes report memory details but stay healthy.
   - Regression test: `tests/unit/api/health-ready.test.ts`.

## Verification gates run

All completed with exit code 0:

- `npm ci`
- `NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co NEXT_PUBLIC_SUPABASE_ANON_KEY=placeholder-anon-key DATABASE_URL=postgresql://user:pass@localhost:5432/synthex JWT_SECRET=placeholder-jwt-secret OPENROUTER_API_KEY=placeholder-openrouter-key npm run validate:env`
- `npm run type-check`
- `npm run lint`
- `npm test -- --runInBand`
  - Result: 222 passed suites, 10 skipped, 3567 passed tests, 201 skipped, 27 todo.
- `npm audit --omit=dev`
  - Result: `found 0 vulnerabilities`.
- `NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co NEXT_PUBLIC_SUPABASE_ANON_KEY=placeholder-anon-key DATABASE_URL=postgresql://user:pass@localhost:5432/synthex JWT_SECRET=placeholder-jwt-secret OPENROUTER_API_KEY=placeholder-openrouter-key npm run build`
  - Result: Next.js production build completed successfully.

## Runtime smoke

Started built app on port 3018 with placeholder env and checked:

- `GET /api/ping` -> 200, `{"ok":true,...}`
- `GET /api/health/ready` -> expected `not_ready` because placeholder localhost Postgres is unavailable, but memory check is now healthy:
  - `memory.status`: `healthy`
  - `memory.message`: `RSS: 359MB (no limit reported); heap 233MB / 264MB (88%)`

## Known non-code blockers / expected warnings

- Local runtime used placeholder `DATABASE_URL`, so database readiness remains `not_ready`; this is expected without a live Postgres/Supabase database.
- Build logs include fallback warnings for Redis/Twitter/social credentials and Prisma query errors during static-page data collection; build still exits 0.
- No production DB writes, deploys, GitHub push/PR, Vercel env changes, client-facing communications, or billing/payment actions were performed.

## Files changed in repo

- `app/api/health/ready/route.ts`
- `package.json`
- `package-lock.json`
- `tests/unit/api/health-ready.test.ts`

## Commit readiness

This is locally merge-ready after review. Suggested commit message:

`fix: clear production audit and readiness memory false positive`
