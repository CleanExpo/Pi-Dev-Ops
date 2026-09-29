---
name: nexus-connector-doctor
description: Use when a Unite-Group Nexus app (Unite-Hub / Command Centre, RestoreAssist, Synthex, etc.) shows connector/env/auth symptoms — "No API key found in request", a login/OAuth redirect loop, a dev-server restart loop ("Found a change in next.config.js"), "Missing required env vars", ERR_CONNECTION_REFUSED on localhost, EADDRINUSE on the dev port, or Supabase/Vercel keys that work in one environment but not another. Diagnoses and permanently fixes inconsistent Supabase/Vercel/Google connectors across local, preview, and production.
---

# Nexus Connector Doctor

## Core principle
**Read the evidence before theorizing, and check the known gotchas in order.** These symptoms look like a Supabase/key bug but are almost always an **environment-scope inconsistency** or a local artifact. Every loop in the past came from guessing instead of (a) reading the dev-server log / HTTP response **body**, and (b) checking the canonical facts below.

## Evidence-first (do this BEFORE proposing any fix)
1. **Read the running dev server's log**, not just status codes. In Claude Code, start it with `run_in_background` and `Read` the output file. Look for: `Restarting the server`, `Missing required env vars`, `EADDRINUSE`, `Code exchange failed`, and which routes actually get hit.
2. **Read the HTTP response BODY**, not just the code. A 401 may be Vercel SSO ("Authentication Required" page) OR the app's auth redirect OR a raw Supabase `{"message":"No API key found in request"}` — three different causes, same code.
3. **For Supabase REST**, a direct browser/curl hit with **no `apikey` header** ALWAYS returns `{"No API key found in request"}` — that's expected, not a bug. Verify a table exists with: `curl -H "apikey: <anon>" "<url>/rest/v1/<table>?select=id&limit=1"` → `[]` = exists, `PGRST205` = missing.

## Canonical facts (Unite-Group Nexus)
- **Production Supabase = `lksfwktwtmyznckodsau`** (project name "Unite-Group"), region ap-southeast-2. This is the DB the Unite-Hub app + Vercel deployments use (`NEXT_PUBLIC_SUPABASE_URL=https://lksfwktwtmyznckodsau.supabase.co`).
- **FOUR look-alike Supabase projects** — do NOT confuse them: `Unite-Group` (`lksfwktwtmyznckodsau`, prod), `Unite-Group Test` (`xgqwfwqumliuguzhshwv`), `Unite-Group-Project` (`idthodoyefbcdgcyuilf`), `unite-group-ops` (`vgxidmwjdbgybjmjvwbb`). The dashboard SQL-editor picker makes mis-targeting easy → apply migrations by **exact project id** via the Supabase MCP `apply_migration`, never the dashboard picker, then verify by REST.
- **Real env lives in the Vercel PREVIEW scope.** `vercel env pull .env.local --environment=production` returns BLANK Supabase keys; **`--environment=preview`** returns the full populated set (Supabase URL+anon, `ANTHROPIC_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, …). This scope inconsistency is the #1 root cause of "Missing required env vars" / "No API key".
- **AVG antivirus intercepts TLS** with a root not in Node/certifi. Node-based CLIs (vercel) fail "unable to verify the first certificate"; curl fails (use `-k` for read-only checks). Fix: `NODE_EXTRA_CA_CERTS=C:\Users\Disaster Recovery 4\AppData\Local\hermes\hermes-agent\venv\Lib\site-packages\certifi\cacert.pem` (AVG root appended). Same root cause as Hermes's OpenRouter cert issue.
- **Dev port = 3008** (`next dev -p 3008`). Anon key is **public** — get it from Supabase MCP `get_publishable_keys` on the project; never ask the user for keys.

## Symptom → root cause → fix
| Symptom | Root cause | Fix |
|---|---|---|
| Dev server logs `Found a change in next.config.js` forever | An empty **`next.config.js` directory** exists beside `next.config.mjs`; Next watches it and restarts | `rmdir next.config.js` (only `next.config.mjs` should exist) |
| `Missing required env vars: NEXT_PUBLIC_SUPABASE_*` / `{"No API key found"}` in-app | `.env.local` has placeholder/empty keys (a `vercel env pull` from prod scope blanks them, or a redacted file) | `vercel env pull .env.local --environment=preview` (with `NODE_EXTRA_CA_CERTS`); if only Supabase needed, set real anon key+URL from `get_publishable_keys`. **Restart `pnpm dev`** (NEXT_PUBLIC is read at startup). |
| `ERR_CONNECTION_REFUSED` on localhost | No dev server bound (it crashed/looped and never stabilised) | Fix the loop/env first, then `pnpm dev`; verify with curl-retry on `:3008` |
| `EADDRINUSE :3008` when starting | Orphaned prior `node` still holds the port (TaskStop killed the wrapper, not the worker) | `Get-NetTCPConnection -LocalPort 3008 -State Listen | Stop-Process -Id $_.OwningProcess -Force` then restart |
| Google login → **redirect loop**, app log shows NO `/api/auth/callback` hit | `http://localhost:3008` is NOT in the Supabase project's **Auth → URL Configuration → Redirect URLs**, so Supabase falls back to the prod Site URL and never returns to localhost | Add `http://localhost:3008/**` to that project's Redirect URLs (dashboard/Management API — no Supabase MCP tool for this). Or test on the deployed site where it's already allow-listed. |
| Google login lands on the **prod/sandbox domain** (e.g. `unite-hub-sandbox.vercel.app/auth/login?code=…`) instead of localhost | The app sends `redirect_to=http://localhost:3008/api/auth/callback?next=/founder/dashboard` (WITH a query string). An **exact** allow-list entry `http://localhost:3008/api/auth/callback` (no query) does NOT match → Supabase falls back to the **Site URL** | Add the **wildcard** `http://localhost:3008/**` to Redirect URLs (covers path **and** query). Exact entries are not enough once the app appends `?next=`. |
| Google login returns to `localhost/auth/login?error=oauth_failed`; dev log shows `Code exchange failed: fetch failed … UNABLE_TO_VERIFY_LEAF_SIGNATURE` | `/api/auth/callback` does a **server-side Node `fetch`** to the Supabase token endpoint. Node (the **dev server**, not just the vercel CLI) doesn't trust the AVG TLS root | Start the dev server with `NODE_EXTRA_CA_CERTS=<…\hermes-agent\venv\Lib\site-packages\certifi\cacert.pem>`. Use `D:\Unite-Hub\start-dev.ps1` (sets it then `pnpm dev`). NEVER use `NODE_TLS_REJECT_UNAUTHORIZED=0`. |
| Google login succeeds at Supabase but user is **bounced back to `/auth/login`** (authenticated yet denied) | The private-access guard (`src/proxy.ts` step 4 → `src/lib/auth/private-access.ts`) compares the user id/email to `FOUNDER_USER_ID`/`FOUNDER_ALLOWED_*`, and `vercel env pull` on Windows appended a **literal `\r\n`** to the value (`"…e83b6\r\n"`), so the exact-match fails | De-corrupt `.env.local`: strip trailing `\r\n` escapes from values (the pull quotes each value and appends `\r\n`). Verify the founder id matches the user's Supabase Auth UID. Restart dev. |
| `{"No API key found"}` from a `*.supabase.co/rest/...` URL in a browser/tool | A direct REST call with no `apikey` header — **not a bug** | Add `-H "apikey: <anon>"`; the app sends it automatically. |
| Cryptic `{"No API key"}` instead of a clear error | Server Supabase clients used `process.env...!` with no runtime guard | Use `src/lib/supabase/env-guard.ts` (branch `pidev/auto-supabase-guard`) which throws a named error + rejects truncated keys |

## Permanent cleanup (make it impossible to recur)
1. **Env parity across Vercel scopes:** ensure Production, Preview, and Development all hold the SAME real values for `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `ANTHROPIC_API_KEY`, etc. (`vercel env ls` to inspect; `vercel env add <NAME> <scope>` to fill gaps). Prod-blank/preview-populated is the trap.
2. **Auth redirect URLs:** the Supabase project's Redirect URLs must include `http://localhost:3008/**` AND every deployed origin (prod + Vercel preview `*.vercel.app`). Set Site URL to prod.
3. **Repo hygiene:** no `next.config.js` directory; ship the env-guard so failures are self-diagnosing; keep `.env.local` out of git (it is) and never paste redacted keys into it.
4. **Prefer the deployed environment for end-to-end testing** — it already has consistent env + allow-listed auth. Local needs the preview pull + the localhost redirect URL.
5. **After EVERY `vercel env pull` on Windows, de-corrupt `.env.local`:** the CLI quotes each value and appends a **literal `\r\n`** (bytes `5c 72 5c 6e`) before the closing quote. Most consumers tolerate it (trailing whitespace), but **exact-match** ones do NOT — e.g. `FOUNDER_USER_ID` in the private-access guard, breaking Google login with an "authenticated but bounced to /auth/login" loop. Strip it (GNU sed's `\\r` won't match — use Python `s.replace('\\r\\n"','"')`). Verify with `xxd` that values end `…"` + `0a`, not `…\r\n"`.
6. **Run the dev server via `D:\Unite-Hub\start-dev.ps1`** (it exports `NODE_EXTRA_CA_CERTS` then `pnpm dev`). The OAuth code exchange is a *server-side* fetch, so the dev server itself — not just the vercel CLI — needs the AVG-augmented CA bundle. (A persistent User env var would fix it globally but may be blocked by the harness; the launcher is the safe local equivalent.)

## The Google-OAuth login loop had THREE stacked causes (2026-06-05)
A single "Google login loops" symptom hid three independent bugs, each only visible after fixing the prior one — fix and re-test iteratively, reading the dev log + the post-redirect URL each time:
1. **Redirect allow-list too strict** → landed on the prod Site URL (vercel sandbox). Fix: add `http://localhost:3008/**` wildcard.
2. **AVG TLS on the dev server** → `Code exchange failed … UNABLE_TO_VERIFY_LEAF_SIGNATURE`. Fix: `NODE_EXTRA_CA_CERTS`.
3. **`\r\n`-corrupted `FOUNDER_USER_ID`** → authenticated but private-access guard denied. Fix: de-corrupt `.env.local`.
Verified working: `GET /api/auth/callback …307 → GET /founder/dashboard 200`. Drive the dashboard fix via Claude-in-Chrome on the user's own Chrome (their Google + Supabase sessions); select the exact account by `data-identifier`, and trigger the React button with `element.click()` via the JS tool when simulated clicks don't register.

## Common mistakes (observed — do not repeat)
- Pulling `--environment=production` (blank) instead of `--environment=preview` (populated).
- Theorizing about Supabase config without reading the dev log / response body first.
- Treating a Vercel-SSO 401 page as an app/Supabase error.
- Applying SQL via the dashboard picker → wrong one of the 4 look-alike projects; not verifying by REST afterward.
- Forgetting to restart `pnpm dev` after editing `.env.local`.
- Asking the user for the anon key (it's public via `get_publishable_keys`).
