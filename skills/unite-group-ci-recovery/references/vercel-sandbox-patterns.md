> Moved from SKILL.md. Read when a Vercel build or sandbox fails (JWT_SECRET at build, OOM exit 137, vercel pull missing Sensitive vars, rootDirectory).

## 2 — Vercel sandbox patterns

The Unite-Group org has TWO Vercel projects per repo: `<repo>` (production) and `<repo>-sandbox` (preview/sandbox). Sandboxes have a documented history of brittleness — 5 of them were broken at the start of this session per memory item SBX.

### 2.1 JWT_SECRET required at build time

Synthex's `/api/auth/oauth/github/callback` route reads `process.env.JWT_SECRET` at module init. Next.js's "Collecting page data" phase executes that module, so **`npm run build` will fail without JWT_SECRET set** with:

```
Error: JWT_SECRET must be set in production environment
  ... in app/api/auth/oauth/github/callback/route.ts
```

Fixes:
- **For local builds**: `JWT_SECRET=any-string npm run build` (the value isn't validated, only its presence)
- **For Vercel project**: add `JWT_SECRET` env var via Vercel Dashboard → project → Settings → Environment Variables (Production scope). User added it to `synthex-sandbox` 2026-05-25 — was the JWT_SECRET fix that turned the sandbox green on PRs #296, #297, #299.

If a NEW Vercel project gets created (sandbox spin-up for a new repo), this gap will re-appear.

### 2.2 OOM (exit 137) on sandbox builds

Symptom in Vercel logs:
```
Error: Command "npm run build:vercel" exited with 137
At least one "Out of Memory" ("OOM") event was detected during the build.
```

Cause: sandbox projects use the default build machine size which has less RAM headroom than production. `NODE_OPTIONS=--max-old-space-size=7680 next build --webpack` plus TypeScript checking on the full Synthex codebase can saturate it. Production builds succeed because they use a larger machine.

What to do:
1. If sandbox OOMs and production passed: it's environmental — document it with log evidence in a PR comment and report it as a founder gate (never admin-merge; merge stays with Phill per `pr-release-gate`)
2. Permanent fix is "Enable Enhanced Builds" in Vercel project settings (UI work, not code). Tracked in [DR-852](https://linear.app/unite-group/issue/DR-852) per memory item SBX.

### 2.3 `vercel pull` skips Sensitive vars

GHA workflows that do `vercel pull && vercel build` will SILENTLY miss env vars marked Sensitive in the Vercel project. The Vercel native git integration handles them fine; the CLI doesn't. Often misdiagnosed as "missing env vars" — actually the workflow architecture is wrong. Per memory `reference_vercel_pull_skips_sensitive`.

### 2.4 `vercel.json` `rootDirectory` is ignored

`rootDirectory` is project-level only — must be set in Vercel UI, never in `vercel.json`. Sandbox projects often inherit a default `rootDirectory` that doesn't match the app subdirectory. Per memory `reference_vercel_rootdirectory_project_level`.
