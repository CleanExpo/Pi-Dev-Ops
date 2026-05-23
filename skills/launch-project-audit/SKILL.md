---
name: launch-project-audit
description: Scan the codebase and produce a plain-English map of every feature — what's built, stubbed, orphaned (built-disconnected), wired, or tested — plus how far each piece has travelled toward production. Cheap model for the bulk pass, frontier only for ambiguous calls. Use on "what's actually built", "scan the project", "what's left", or as step 2 of /ship-it.
owner_role: Curator
status: wave-4
automation: manual
intents: project-audit, scan-project, whats-built, build-state-map
---

# launch-project-audit

Tells a non-coder the truth about what is finished versus half-built — and where the hidden gap is: code that exists but nothing calls.

## Why this exists

READMEs and "done" Linear tickets lie. "It compiles" is not "it's wired." The single most common hidden gap is `built-disconnected` — a real implementation that no route imports, no button calls, no frontend hits. A non-coder cannot see it by eye; reference/dead-code tooling can. This skill produces the evidence-cited map that the rest of the crew acts on.

It complements, never replaces, the existing auditors — it is the ONE thing none of them does (a feature-by-feature build-state + pipeline-stage map). Explicitly defer: security findings → [`security-audit`](../security-audit/SKILL.md); UI/design → [`design-audit`](../design-audit/SKILL.md); autonomy/leverage scoring → [`leverage-audit`](../leverage-audit/SKILL.md); runtime per-step logging → [`audit-emit`](../audit-emit/SKILL.md). This skill only owns "what's built vs stubbed vs disconnected vs wired vs tested, and how far to production."

## Triggers

- "scan my project", "what's built", "what's left", "is this ready".
- Step 2 of [`ship-it`](../ship-it/SKILL.md), after [`launch-charter`](../launch-charter/SKILL.md) is loaded.

## Method

Work cheaply first; escalate only for judgment.

1. **Flatten the repo (cheap/auxiliary model).** Use `rendergit` (github.com/karpathy/rendergit) to turn the repo into one page, or fall back to `git ls-files` + reading key files. Feed to the cheap model for the bulk pass. Do not load the frontier model yet.
2. **Inventory features** from the flattened repo + every spec / `.md` / `CLAUDE.md` / `AGENTS.md` / `HERMES.md` / `.harness/projects.json`.
3. **Classify each feature's BUILD STATE** on concrete signals, not vibes:
   - `not-started` — named in docs but no file/route/component exists.
   - `stubbed` — file exists but body is a placeholder: `TODO`, `FIXME`, `raise NotImplementedError`, `return None`, empty handler, "coming soon", mock/hardcoded data where real logic belongs.
   - `built-disconnected` — implemented but nothing imports it / no route points to it / the handler is never called. Detect with dead-code tooling: dashboard (TS) `knip`, `ts-prune`, `depcheck`, `madge`; backend (Python) `vulture`, `ruff` (F401/unused), `deptry`. This is the category a non-coder cannot see.
   - `built-wired` — implemented AND connected AND data flows end to end.
   - `built-tested` — the above, with tests in `tests/` that actually cover it.
4. **Escalate only ambiguous calls to the FRONTIER model** — keeps cost down.
5. **Map PIPELINE STAGE per feature** (`idea → in-progress → PR-open → merged → in-production`). Cross-reference GitHub branches/PRs/merges with the live deploys: Railway for `app/server/*` (FastAPI), Vercel for `dashboard/*` (Next.js). A feature can be `built-wired` in code but only `merged`, not `in-production` — surface that gap explicitly.

## Output

One plain-English table, sorted closest-to-done LAST so unfinished work is on top:
`Feature | Build state | Pipeline stage | What's missing | Suggested next step`.

Save to `.harness/audits/audit-<YYYY-MM-DD>.md`. Emit a `curator_proposal` row via `audit_emit.row(...)` so the run is logged in `.harness/swarm/swarm.jsonl`.

## Safety bindings

- Read-only. This skill never modifies code, only reports.
- Respects the kill-switch (`TAO_SWARM_ENABLED=0`) — reporting still runs, no builder dispatch.
- Cites evidence per row; honours `pii-redactor` on any quoted code containing secrets.

## Verification

1. Every `built-disconnected` and `stubbed` row names the exact file/symbol AND the signal proving it (the missing reference, the TODO, the empty handler).
2. A row that cannot cite evidence is marked `needs-human-look`, never guessed.
3. Re-running on an unchanged tree produces the same classifications (deterministic on the cheap pass).
4. Pipeline stage for at least one `app/server/*` and one `dashboard/*` feature is cross-checked against the live Railway/Vercel deploy, not just the branch.

## Out of scope

- Fixing anything — see [`launch-enhance-debloat`](../launch-enhance-debloat/SKILL.md).
- Security / design / leverage scoring — delegated to `security-audit` / `design-audit` / `leverage-audit`.
- Per-step runtime audit logging — that's [`audit-emit`](../audit-emit/SKILL.md).

## References

- [`launch-review`](../launch-review/SKILL.md) — consumes this audit as input.
- [`security-audit`](../security-audit/SKILL.md), [`design-audit`](../design-audit/SKILL.md), [`leverage-audit`](../leverage-audit/SKILL.md) — the auditors this skill defers to.
- `AGENTS.md` boundary matrix (which paths are safe to touch later).
