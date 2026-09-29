# Pack — Unite-Group

Doctrine and pointers only. **Nothing in this file may decay.** No ticket IDs, no epic
numbers, no "current status", no model IDs, no counts, no SHAs. If a fact could be
different next Tuesday, it does not belong here — fetch it at run time.

## What Unite-Group is

`CleanExpo/Unite-Group` is **the** canonical monorepo for the Unite-Group product and
ecosystem. It absorbed Unite-Hub, hermes-workspace, Unite-Group-Spine,
pi-ceo-operator-mcp, brain-1 and Fabel-Prompt-Engineer with full git history. Read
`SOURCE-OF-TRUTH.md` and the root `CLAUDE.md` first; `CLAUDE.md` is authoritative where
the two disagree.

The product is `apps/web` — a single-tenant, founder-scoped CRM and operating plane
serving the portfolio's businesses. `apps/workspace` is the agent workspace,
`apps/spec-board` the vision-to-spec surface, `apps/empire` reference-only.

The North Star governing every surface: **no fake-as-real.** A read that failed must
never render as a read that succeeded and found nothing; a seed must never be dressed as
live. This is the most consistently honoured rule in the codebase and the one most worth
defending.

## The waterline

**Read it live, do not restate it:** the repo's `CONSTITUTION.md`, section
**"The Waterline — autonomy gate"**. If that heading is missing, stop — the gate has
moved or was never installed, and a remembered gate is not a gate.

Shape, for orientation only: agents act above the line; credential and secret changes,
production mutation, irreversible actions without tested rollback, new or increased cost,
and constitutional amendment fall below it and hand back to Phill. The one standing
merge exception is UG-AUTONOMY-001, and it never covers those classes.

## Never

- Write to a former repo. brain-1, hermes-workspace, pi-ceo-operator-mcp are frozen;
  Unite-Group-Spine is archived; Unite-Hub and its Vercel project were deleted. Do not
  describe any of them as pending, query them as live, or start work against them.
- Apply DDL straight to production Postgres. Every schema change is validated on a
  Supabase **database branch** first. There is no standing sandbox project.
- Stack a PR on another feature branch. Base is `main`, always — one issue, one branch
  off latest `main`, one PR into `main`. Stacked PRs strand work in their base.
- `--no-verify`, force push, or the human-override variable. Ever, for any reason.
- Self-certify a release. The independent review is a different agent in fresh context,
  preferring the other vendor's CLI, bound to the exact final SHA.
- Treat the root as a pnpm workspace. Each package keeps its own lockfile and manager;
  `apps/web` is itself a pnpm workspace and pnpm does not nest.
- Create a non-example `.env*` file inside `apps/web`. The web build verifier refuses to
  run when one exists and injects its own placeholders instead.
- A "done" claim without the command output that proves it. A null result is not evidence
  until a positive control has shown the check can return non-null.

## Vocabulary

Australian English in all product copy — colour, organise, recognise, licence (noun),
authorise. Currency AUD, dates DD/MM/YYYY, timezone AEST/AEDT. Commits
`type(scope): description`. Claims carry `[VERIFIED]` / `[INFERENCE]` / `[UNCONFIRMED]`
per `.claude/rules/fabel-evidence-standard.md`; untagged is a defect.

## Fetch at run time, never store

- Definition of done → root `package.json`, the `verify` script chain.
- Runtime truth → Vercel MCP `get_runtime_errors` and `list_deployments`. Production
  health lives there, not in any doc in this repo.
- Schema and publication state → Supabase MCP against the production project id named in
  the root `CLAUDE.md`; read-only first, always.
- Live backlog → Linear. Repo docs record what was *claimed*, dated; they rot within weeks.
- Estate context → `brain.js find`.
- Canonical env-var names → the `env-var-canon` project skill, never recall.

If a fetch fails, write `STATE: UNVERIFIED` in the brief and proceed on that basis. Never
substitute a remembered state for a live one — this repo's own audits record that
"re-verified by grep" is exactly what produced its false grades.
