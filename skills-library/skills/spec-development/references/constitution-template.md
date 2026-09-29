# Constitution: <repo name>

> Standing law for all development in this repo. Created by spec-development phase 0
> ONLY because no CLAUDE.md/AGENTS.md existed. If a CLAUDE.md is later added, merge
> this into it and delete this file — one constitution per repo.

## Non-negotiables
Rules every spec, plan, and PR must obey. Keep under 15; each must be checkable.
1. <e.g. All API routes authenticate and scope queries by tenant.>
2. <e.g. Tests accompany every behaviour change; suite must be green before PR.>
3. <e.g. Additive migrations only without explicit human approval.>
4. <e.g. Secrets live in env, never in code, never in logs.>
5. <e.g. Australian English in user-facing copy; GST-inclusive pricing.>

## Quality gates (the oracle)
The commands that define "done" here — type-check, test, lint, build — exactly as CI
runs them.

## Architecture defaults
Framework, data layer, auth pattern, error-response idiom, directory conventions —
the choices new code follows unless a plan.md argues otherwise and wins.

## Decision rights
What agents may do autonomously vs what waits for the human (deploys, deletions,
spend, pricing, legal copy).
