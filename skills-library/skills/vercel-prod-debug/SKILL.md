---
name: vercel-prod-debug
description: Use when a Vercel-hosted app (esp. Next.js App Router) is misbehaving in production — all /api routes 500 while pages 200, a deployment URL returns 401, a CLI deploy "succeeds" but the live domain still serves an old/broken build, or smoke tests fail against the prod alias. A live-incident diagnostic runbook (not a pre-deploy checklist — for that use curator-deployment).
owner_role: deployment-engineer
status: active
---

# vercel-prod-debug

## Why this exists

DR-NRPG production hit a cluster of Vercel failures that *looked* like an app outage but were really deployment/config faults, and they recurred across multiple commits (Deploy Production failed on 6 consecutive `main` pushes before anyone isolated the cause). Each has a precise external signature you can read with `curl` + `gh` + `vercel` before touching code. This skill turns that forensic session into a repeatable runbook so the same class never costs a full investigation again.

Sources verified against `vercel.com/docs` (Feb–Jun 2026). Pair with `curator-deployment` (which prevents config mistakes pre-merge); this skill diagnoses them *after* they reach prod.

## First move: read the external signature (no dashboard needed)

```bash
# Scope the blast radius — pages vs API, alias vs custom domain vs fresh deploy
for u in "https://<alias>.vercel.app" "https://<alias>.vercel.app/api/health" \
         "https://<custom-domain>" "https://<custom-domain>/api/health"; do
  echo "$u -> $(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$u")"
done
curl -sI "https://<alias>.vercel.app/api/health" | grep -iE "x-vercel|x-matched-path|server"
```

The response headers are the diagnosis. Decision tree:

| Signature | Cluster | Meaning |
|---|---|---|
| `x-matched-path: /500`, HTML 500, `server: Vercel`, pages 200 | **1** | Function cold-start crash — almost always a missing **Production**-scoped env var |
| `401` on the generated `*.vercel.app` URL | **2** | Deployment Protection (Vercel Authentication) |
| CLI deploy logged success but custom domain serves old build | **3** | Production alias didn't promote |
| Plain (non-Next.js) `404 - Not Found` on custom domain `/api/*` | **3b** | Custom domain points at a *different host/build* than the Vercel app |

## Cluster 1 — all `/api/*` 500, pages 200

A serverless function entered invocation and **crashed before responding** (`FUNCTION_INVOCATION_FAILED`). Pages survive because the crashing code only loads in the API bundle. Root causes, in order:

1. **Missing Production-scoped env var read at import/cold-start** by a shared module (`lib/db`, `lib/auth`, Stripe/Sentry client, a secret-validating constructor). Env vars are baked **per-environment** — a var set only for Preview is absent in Production. **This is the #1 cause.**
2. **Node API in an Edge route** (`export const runtime = 'edge'` + `fs`/`pg`/node `crypto`).
3. **Uncaught exception** in the handler with no try/catch.

Diagnose:
```bash
vercel logs --environment production --status-code 500 --source serverless --expand --since 1h
vercel env ls production          # confirm every prod-scoped var the API needs exists
vercel inspect <deployment-url>   # runtime, regions, bundle
```
Dashboard: Project → Logs (Source=Serverless, Status=500), or Deployment → Runtime Logs.
Code-side rule-out before blaming infra: grep for module-level (outside the handler) `process.env.` reads and secret-reading constructors in any module imported by API routes/middleware. Make those **lazy** (read inside the handler) — see the `csrf.ts` lazy-proxy pattern in DR-NRPG.
Docs: `vercel.com/docs/errors/FUNCTION_INVOCATION_FAILED` · `/docs/cli/logs` · `/docs/environment-variables/system-environment-variables`

## Cluster 2 — fresh deployment URL returns 401

**Deployment Protection.** Has a *method* (Vercel Authentication / Password / Trusted IPs) and a *scope* (Standard / All Deployments / Trusted IPs).
- **Standard Protection** = everything **except** production domains → previews locked, prod public. This is the default that keeps customer prod open while `*.vercel.app` generated URLs 401.
- To let CI smoke tests hit a protected URL: Project → Settings → Deployment Protection → **Protection Bypass for Automation** → generates `VERCEL_AUTOMATION_BYPASS_SECRET`. Send header `x-vercel-protection-bypass: $SECRET`:
```bash
curl -H "x-vercel-protection-bypass: $VERCEL_AUTOMATION_BYPASS_SECRET" \
     https://<deployment>.vercel.app/api/health
```
Keep production public → use **Standard Protection** scope, not "All Deployments". Regenerating the secret invalidates old deployments (redeploy to refresh).
Docs: `vercel.com/docs/deployment-protection` · `/docs/deployment-protection/methods-to-bypass-deployment-protection/protection-bypass-automation`

## Cluster 3 — custom domain serves an older build than the alias

Deployments are immutable; the production alias is a pointer. `vercel deploy --prod` *usually* builds **and** auto-assigns the apex — but the alias does **not** promote when `--skip-domain` was used, auto-assign is off, or the promote step failed after a successful build. Net: CLI prints a new URL (build OK) but the apex still points at the old/broken deployment.
```bash
vercel ls                       # which deployment is "Current"/prod
vercel alias ls                 # what the apex points to
vercel inspect <new-url>        # confirm the new build is healthy
vercel promote <new-url>        # instant re-point, no rebuild  ← the fix
# or: vercel alias set <new-url> <custom-domain>
```
**3b — plain non-Next.js 404 on the custom domain's `/api/*`:** the apex resolves to a *different host* (static export, another platform, or an old project) than the Vercel app. Check DNS / domain assignment in Project → Settings → Domains, and confirm the apex is attached to *this* project.
Docs: `vercel.com/docs/cli/deploy` · `/docs/cli/promote` · `/docs/cli/alias` · `/docs/deployments/promoting-a-deployment`

Note: `--prebuilt` deploys lack System Environment Variables at build time — frameworks needing them at build can misbehave; prefer Git-based deploys or drop `--prebuilt`.

## CI gotcha that masks all of the above

A `Deploy Production` workflow whose deploy *job* uses `vercel deploy` (success) but whose `smoke-test`/`performance` jobs hit a **fixed alias** will report the alias's health, not the fresh deploy's. Two failure shapes seen in DR-NRPG:
- `performance-check` ran `lhci` which shells to `pnpm` without `pnpm/action-setup` → `pnpm: not found` (exit 127). Fix: add the pnpm + node setup steps (mirror the deploy job).
- The smoke test correctly went red because the alias's API was 500 — **do not weaken the smoke test to force green**; it's the canary. Fix the deployment, not the test.

## One-glance triage

401 → Deployment Protection (bypass header). API-only 500 + `x-matched-path:/500` → cold-start crash, look for a missing Production env var read at import. Stale apex despite "success" → `vercel promote <url>`. Plain 404 on custom-domain API → domain points at the wrong host.
