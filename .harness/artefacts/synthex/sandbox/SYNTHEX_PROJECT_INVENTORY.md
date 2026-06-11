# Synthex project inventory

Generated: 2026-05-24
Sandbox SSOT: `/Users/phillmcgurk/Pi-CEO/.harness/artefacts/synthex/sandbox`
Active repo: `/Users/phillmcgurk/Pi-CEO/.harness/artefacts/synthex/sandbox/Synthex`
Remote: `https://github.com/CleanExpo/Synthex.git`
Branch at inventory: `main`
HEAD at inventory: `b1beb11dc34a`

## Consolidation result

`/shipit` consolidation has been executed as a local sandbox process:

- 5,913 Synthex-related records found across available local roots.
- 5,908 files copied into the sandbox consolidation area.
- 1,955 files matched by Synthex content, not just filename/path.
- Consolidated scattered-file store: `/Users/phillmcgurk/Pi-CEO/.harness/artefacts/synthex/sandbox/_consolidated_scattered`
- Full manifest: `/Users/phillmcgurk/Pi-CEO/.harness/artefacts/synthex/sandbox/SYNTHEX_CONSOLIDATION_MANIFEST.json`

Skipped items are manifest-only, not copied, when they are environment/secret-like files or unsafe to duplicate. No secret values were preserved in this report.

## Project map

Tracked source files in canonical Synthex repo: 5,515.

Major areas:

- `app/` — 1,102 files. Next.js app router, pages, server routes, dashboards, marketing, product flows.
- `components/` — 779 files. UI, analytics, AI studio, campaign, dashboard, onboarding, editor, billing, and workflow components.
- `lib/` — 736 files. Shared application services, Supabase/Prisma helpers, integrations, security, telemetry, analytics, billing, and utility logic.
- `.claude/` — 637 files. Prior automation state, agent/task context, and implementation traces.
- `.planning/` — 553 files. Roadmaps, backlog, fix manifests, state, route reference, credential/audit notes.
- `tests/`, `__tests__/`, specs, and test-like files — 411 files discovered.
- `public/` — 217 files. Static assets and media.
- `scripts/` — 162 files. Validation, migration, backup, routing, media, setup, health, and release utilities.
- `docs/` — 145 files. API, integration, deployment, recovery, monitoring, and operating documentation.
- `supabase/` — 94 files. SQL migrations, RLS coverage, schema support.
- `board-cron/` — 80 files. Scheduled board/audio/video session pipeline.
- `brand-intelligence/` — 20 files. Python brand intelligence/orchestration service.
- `synthex-bayesian-service/` — 18 files. Bayesian/ML support service.
- `marketing-studio/` — 10 files. Marketing agency/studio extension.
- `prisma/` — 25 files. Prisma schema/migrations/client generation source.

Application surface:

- App router route handlers: 656 tracked `app/api/**/route.*` files.
- App pages/layouts: 198 tracked page/layout files.
- Package scripts: build, lint, test, type-check, env validation, Prisma validation, integration tests, e2e, Storybook, security audit, release check, RLS checks, and deployment helpers.

Raw machine-readable inventory:

- `/Users/phillmcgurk/Pi-CEO/.harness/artefacts/synthex/sandbox/SYNTHEX_INVENTORY_RAW.json`

## Finished / green at baseline

Previously established in this sandbox before this inventory pass:

- `npm ci` completed.
- Prisma client generation completed via postinstall.
- `npm run type-check` passed.
- `npm test -- --runInBand` passed.
- `npm run lint` passed.
- `npm run build` passed when provided safe placeholder env values.

This pass additionally resolved the production dependency audit finding:

- `npm audit --omit=dev` now reports 0 vulnerabilities.
- The change is limited to `package-lock.json`.

## Broken / blocking findings

Current blocker removed:

- Production dependency audit previously failed on transitive `qs` vulnerability. Fixed with `npm audit fix`; production audit is now clean.

Known non-blocking external/developer-only findings:

- Full `npm audit` still reports dev/transitive findings requiring breaking force downgrades/upgrades (`prisma` dev chain and `@storybook/nextjs` transitive crypto stack). These are not production blockers under the project's existing `audit` script because the project gates production audit with `npm audit --omit=dev`. A forced fix would be breaking and is not applied autonomously.

External blockers that cannot be completed locally without credentials/services:

- Live Supabase connectivity and real database writes need valid Supabase credentials.
- Live OpenRouter/AI provider calls need provider credentials.
- Live Vercel/Railway deployment verification needs account access and environment secrets.
- Production auth/session checks need valid deployment URL and auth credentials.

## Stubbed, partial, or promised-but-not-completed surface

The codebase contains many historical planning and placeholder markers:

- 3,699 source markers matched terms such as TODO/FIXME/TBD/stub/placeholder/skipped/disabled outside generated/dependency folders.
- 7,239 planning/doc mentions matched future/planned/roadmap/pending/phase/gap/incomplete/remaining language.

Classification:

1. Test mocks and fixtures: expected and not blockers when tests pass.
2. Historical planning/backlog references: not automatically merge-blocking unless they correspond to failing code or current release scope.
3. Real blocking gaps: only items that fail current gates, production audit, typecheck, lint, build, tests, or local integration health checks.

The raw inventory records the first 500 marker lines and first 500 planning mentions for follow-up triage without flooding the terminal.

## Merge-readiness standard for this objective

The Synthex sandbox is merge-ready only when these local gates are green:

- `npm ci`
- `npm run validate:env` with safe local placeholder environment where required
- `npm run type-check`
- `npm run lint`
- `npm test -- --runInBand`
- `npm audit --omit=dev`
- `npm run build` with safe local placeholder environment where required
- `git status --short` shows only intentional merge-ready artifacts

Live service checks are classified as external blockers unless credentials are present and usable in the current shell.
