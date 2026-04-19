# Task Brief

[HIGH] [CCW-CRM] Resolve main vs ai-updates split — Vercel Root Directory mismatch causing 5+ main-branch build failures/day

Description:
## Status update 2026-04-17 (awaiting Rana's input)

Filed autonomously by Phill's autonomous session earlier today. Rana confirmed he's looking into it.

### Context for Rana

The Vercel project `ccw-crm-web` has `productionBranch=ai-updates` (not `main`). Root Directory is `apps/web`. Today's live facts:

* `main` HEAD (`07adbde`, 2026-04-13) does **not** contain `apps/web/` — every main-branch deploy fails with *"Root Directory 'apps/web' does not exist"*.
* `ai-updates` HEAD (`0643e64`, 2026-04-17) has the monorepo structure with `apps/web/` and is serving prod via `ccw-crm-web-unite-group.vercel.app`.
* Divergence: ai-updates is 104 ahead / "700 behind" main in GitHub's compare, but ai-updates contains the newer actual work.

### Decision owed

Pick one of the three options in the original ticket description. Most likely: **Option A** (merge ai-updates into main, switch productionBranch to main, delete ai-updates when stable) — consolidates to conventional trunk and stops the daily main-build errors.

### Parallel context (unrelated but in-flight)

* Dashboard CARSI CI went 0/5 → 4/5 jobs green today (PRs #22/#24/#26/#28/#30/#32/#34 merged in CARSI).
* E2E still failing — see RA-1164 for the separate CARSI E2E ticket; likely needs DB seeding strategy, not branch decision.

Linear ticket: RA-1160 — https://linear.app/unite-group/issue/RA-1160/ccw-crm-resolve-main-vs-ai-updates-split-vercel-root-directory
Triggered automatically by Pi-CEO autonomous poller.


## Session: 7f93e1b44866
