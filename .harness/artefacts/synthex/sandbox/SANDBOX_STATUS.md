# Synthex Sandbox Status

Updated: 2026-05-24T05:46:35Z

## Scope boundary

All active work for this lane is constrained to:

`/Users/phillmcgurk/Pi-CEO/.harness/artefacts/synthex/sandbox/`

No changes are to be made outside the Synthex sandbox folder unless explicitly approved.

## Hydrated repo

- Repo path: `/Users/phillmcgurk/Pi-CEO/.harness/artefacts/synthex/sandbox/Synthex`
- Remote: `https://github.com/CleanExpo/Synthex.git`
- Branch: `main`
- HEAD: `b1beb11d`
- Working tree before status note: clean

## Package/setup baseline

- Node: `v22.22.3`
- npm available locally: `10.9.8`
- packageManager declared by repo: `npm@11.8.0`
- `npm ci`: PASS
- Prisma client generation during postinstall: PASS

## Verification baseline

- `npm run type-check`: PASS
- `npm test -- --runInBand`: PASS
  - 221 passed suites, 10 skipped suites
  - 3566 passed tests, 201 skipped, 27 todo
- `npm run lint`: PASS
- `npm audit --omit=dev --json`: 1 production vulnerability
  - moderate: transitive `qs`
- Build-shape verification with safe placeholder env values: PASS
  - Command used placeholder values only for required build-time envs.
  - Build completed successfully.
  - Expected warnings appeared for missing Redis/Twitter/live service credentials.

## Current safe next lanes

1. Investigate and remediate the remaining production `qs` audit finding.
2. Align npm runtime with repo-declared `npm@11.8.0` if exact package-manager parity is required.
3. Work on `/dashboard/sandbox` or sandbox campaign workflow issues, using the current passing test/type/lint/build baseline.
4. Avoid production writes, deployments, secret reads, or env mutation without explicit approval.
