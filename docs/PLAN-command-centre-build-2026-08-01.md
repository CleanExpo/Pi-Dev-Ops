# Command centre consolidation — build plan

**Date:** 2026-08-01 · **Status:** Phase 1 BLOCKED on a scope finding. Phases 2–3 delivered.
**Nothing live touched. No deployment made. Fence in shadow.**

---

## Phase 1 — the two instructions in the brief conflict

The brief says two things that cannot both hold:

1. *"Take the 9 command-centre pages … consolidate them into one dashboard."*
2. *"The Pi-Dev-Ops version wins where they overlap."*

Measured, not estimated:

| | Lines |
|---|---|
| The 9 command-centre pages themselves | 2,244 |
| **Their actual transitive import closure** | **52,916 lines across 175 files** |
| All Pi-Dev-Ops dashboard routes that overlap them, combined | **912** |

The closure was computed by walking `from '…'` specifiers from all files under `command-centre/`, resolving `@/` and relative paths, and following to fixpoint — not by measuring directory sizes. It pulls in 71 files from `app/(founder)` alone (the shell, theme, deck layout), plus `components/command-centre` (30), `lib/command-centre` (25), `lib/operator-gateway` (14), `lib/integrations` (8), `lib/supabase` (5).

**So "Pi-Dev-Ops wins where they overlap" resolves to: ship the dashboard that already exists.** Its overlapping routes are thin — `brain` 12 lines, `health` 6, `settings` 41, `control` 94. The command-centre capability lives in the 53k-line graph, and applying the rule literally means it does not come across.

That is a legitimate choice. It is not the same as consolidating, and it should be made knowingly.

### Overlap map — evidence, not assertion

| CC page | Lines | Pi-Dev-Ops route | Lines | Honest verdict |
|---|---|---|---|---|
| `/` (deck index) | 264 | `overview` | 525 | **Pi-Dev-Ops wins** — genuinely more built |
| `/portfolio` | 306 | `projects` | 234 | **Pi-Dev-Ops wins** — comparable |
| `/operations` | 259 | `control` + `health` | 100 | **Capability loss** — Pi-Dev-Ops side is thinner |
| `/knowledge` | 120 | `brain` | 12 | **Capability loss** — `brain` is a 12-line stub |
| `/wiki-graph` | 132 | `brain` | 12 | **Capability loss** — no graph view exists |
| `/providers` | 68 | `settings` | 41 | **Capability loss** — LLM pool + cost tiles absent |
| `/operator-gateway` | 849 | `control` (kill-switch API) | 94 | **Capability loss** — largest page, no equivalent |
| `/hermes-control-panel` | 227 | — | — | **No equivalent** — must port or drop |
| `/studio` | 19 | — | — | **Safe to drop** — requires a `taskId`; it is an entry point from routed ideas, not a standalone page |

Only **2 of 9** are genuine wins for Pi-Dev-Ops. **6 are capability losses.** One (`/studio`) is safely droppable.

### What I did not do, and why

I did not build a merged dashboard and deploy a preview. Producing a shell with six stubbed pages and calling it a consolidated command centre would look like Phase 1 was delivered while shipping a regression. The scope finding is the deliverable, because it changes the decision.

**The "Pi-Dev-Ops wins" dashboard already exists and is already deployed:** `https://pi-dev-ops.vercel.app` (HTTP 200, "Pi CEO — Autonomous Dev Platform", `target: production`). If that plus a clean subdomain is the goal, no build is required at all — go straight to Phase 3.

### The decision

- **Option A — subdomain only.** Point `cc.unite-group.ink` at the existing Pi-Dev-Ops dashboard. Cost: near zero, today. Accept that the 6 capability losses above are not migrated, and that the Authority-Site command centre stays where it is.
- **Option B — real migration.** Port the operator-gateway, knowledge, wiki-graph, providers, operations and hermes panels into Pi-Dev-Ops's idiom against its own data layer. This is a scoped project, not a consolidation task. Sequence it by the table above, largest first (`/operator-gateway` at 849 lines is the pole).

**Recommendation: A now, B as separately-scoped work.** A is reversible and delivers the clean-domain goal immediately. B should be planned per-page with its own acceptance criteria, not attempted as one move.

---

## Phase 2 — env vars and data sources

### What the dashboard needs — 29 distinct variables

| Group | Variables |
|---|---|
| **Supabase** | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY`, `SUPABASE_SERVICE_ROLE_KEY` |
| **Models** | `ANTHROPIC_API_KEY`, `ANALYSIS_MODE`, `ANALYSIS_MODEL`, `ANALYST_MODEL`, `ORCHESTRATOR_MODEL`, `WORKER_MODEL` |
| **Auth / access** | `DASHBOARD_PASSWORD`, `PI_CEO_PASSWORD`, `PI_CEO_URL` |
| **Integrations** | `GITHUB_TOKEN`, `LINEAR_API_KEY`, `VERCEL_TOKEN`, `RAILWAY_URL` |
| **Telegram** | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET` |
| **Webhooks / cron** | `CRON_SECRET`, `WEBHOOK_SECRET`, `INTAKE_WEBHOOK_SECRET`, `TAO_WEBHOOK_SECRET` |
| **Flags / runtime** | `TAO_USE_AGENT_SDK`, `THINK_SEED_ENABLED`, `HARNESS_AUDIT_PATH`, `NODE_ENV`, `VERCEL_ENV` |

⚠️ **Present-vs-missing could not be confirmed read-only.** `vercel env ls` returned nothing because the project is not linked locally, and linking writes `.vercel/project.json` — a repo mutation this brief forbids. Confirming requires either a `VERCEL_TOKEN` or you running `vercel env ls` in `dashboard/` yourself.

**What is inferable:** the deployment is live and serving, so the variables needed to boot are set. The uncertain set is the feature-specific ones — Telegram, Linear, GitHub, Railway.

### Data sources

| Source | Detail | Status |
|---|---|---|
| Supabase — Unite-Group prod | `lksfwktwtmyznckodsau` | **Shared with the standalone platform.** Both already read it. |
| Supabase — Pi CEO | `zbryrmxmgfmslqzizsto` | Pi-Dev-Ops only |
| GitHub API | via `GITHUB_TOKEN` | needed by `builds`, `webhook/github` |
| Linear | via `LINEAR_API_KEY` | needed by project surfaces |
| Anthropic | via `ANTHROPIC_API_KEY` | **metered — spend surface** |
| Telegram | bot token + chat id | founder-supplied, still absent |

**The dashboard needs no database the Pi-Dev-Ops project does not already reach.** No migration of data is implied by Option A.

---

## Phase 3 — go-live plan for `cc.unite-group.ink` (NOT RUN)

Chosen because `unite-group.ink` is **owned outright** — in the Vercel domain registry, Vercel registrar, expires 2027-03-04, and `vercel dns ls unite-group.ink` succeeds. Unlike `unite-group.in`, nothing here is blocked on account access.

Its apex currently 404s and only `live.` is assigned, so `cc.` is free.

| # | Step | Touches | Gate |
|---|---|---|---|
| 1 | Confirm env completeness — `vercel env ls` in `dashboard/` | nothing | **you run it** (I cannot, read-only) |
| 2 | Add any missing env vars to the `pi-dev-ops` project | secrets | **GATE — founder** |
| 3 | Add domain `cc.unite-group.ink` to the `pi-dev-ops` project | DNS + production | **GATE — founder** |
| 4 | Vercel auto-creates the CNAME/ALIAS in `unite-group.ink` DNS | DNS | **GATE — founder** |
| 5 | Promote a production deployment on `pi-dev-ops` | production | **GATE — founder** |
| 6 | Verify: `cc.unite-group.ink` returns 200 and the auth gate behaves | nothing | read-only |
| 7 | Soak one full scheduled cycle before announcing | nothing | — |

**Every step that changes anything is gated. Steps 1, 6 and 7 are the only ungated ones.**

### Rollback

| After step | Rollback | Cost |
|---|---|---|
| 3–4 | Remove the domain from the project | seconds — `.ink` DNS is Vercel-managed and yours; nothing else uses `cc.` |
| 5 | Promote the previous deployment | one click, Vercel keeps history |
| Any | Do nothing — `unite-group.in` is untouched throughout | zero |

**The rollback is unusually clean because this adds a surface rather than moving one.** `unite-group.in` and the Authority-Site platform are not modified at any step. If `cc.unite-group.ink` is wrong, delete it; nothing regresses.

### Explicitly out of scope

- Repointing `unite-group.in` — blocked on account access, and unnecessary for this goal
- Touching the Authority-Site platform, its 49 non-command-centre pages, or its 123 env vars
- Retiring the existing command centre — that follows Option B, not this plan
- Any DNS change on `unite-group.in`, including the pending A-record cleanup

---

## Confirmation

Read-only throughout: `find`, `grep`, `wc`, a Python import-closure walker over source files, `vercel env ls` (returned empty, no link created), and `vercel dns ls`. No deployment, no domain change, no env change, no file written outside this document and the task list.

Fence remains in **shadow**. No `HARD_STOP`. No denials seeded.
