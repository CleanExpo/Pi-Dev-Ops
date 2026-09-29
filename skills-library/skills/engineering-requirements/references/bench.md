# The bench — roster, ownership, and dispatch

Seventeen seats. Four always sit; the rest are earned by what the change actually touches. This
file is the single source of truth for who exists and when they fire.

The design rule behind it: **one reviewer with a longer prompt is not a bench.** This session
proved it — a generalist review of an RLS incident concluded the exposure was limited to encrypted
OAuth tokens. A drift lens then found nine surviving `"Anon read access"` policies, sourced from a
loose bootstrap file the generalist never opened, exposing 11,007 rows of plaintext client
financial data. Same repository, same hour, different speciality.

## Always seated (the core four)

| Seat | Owns | Why it never sits out |
|---|---|---|
| `boris` | chair; every category no specialist claims | Arbitrates disagreement, and guarantees all ten categories are answered even on a one-seat review |
| `eng-failure` | `failure_modes` | Every change can break something; blast radius is never `N/A` for free |
| `eng-observability` | `observability` | The failure you cannot detect is the one that costs the most |
| `eng-test` | `test_oracle` | Without an oracle, every other finding is unfalsifiable |

## Earned seats

Dispatch is by predicate over the change — the diff, the spec, and the repo. Deterministic where
it can be; the chair decides only the genuinely ambiguous case.

| Seat | Owns | Fires when the change touches |
|---|---|---|
| `eng-data` | `data_model`, `migration` | `*.sql`, `migrations/`, schema files, ORM models, or a spec naming a table, column or cascade |
| `eng-authz` | `invariants` | auth, sessions, JWTs, roles, permissions, tenancy, RLS or policy definitions |
| `eng-secrets` | cross-cutting | `.env*`, key material, tokens, OAuth, or any new external integration |
| `eng-concurrency` | `concurrency` | queues, crons, workers, background jobs, upserts, retries, or any second writer |
| `eng-contract` | `interface_contract` | route handlers, public APIs, exported types, request/response schemas, webhooks |
| `eng-rollback` | `rollback` | migrations, deploys, feature flags, or anything whose reversal is not obvious |
| `eng-performance` | `budget` (latency half) | queries, loops over collections, pagination, or any request path |
| `eng-cost` | `budget` (spend half) | paid APIs, model calls, cron frequency, storage growth |
| `eng-release` | cross-cutting | CI config, deploy config, env vars, migrations — **and unconditionally when the repo's migration ledger disagrees with its migration directory** |
| `eng-frontend` | cross-cutting | components, pages, client state, styling, anything reaching the browser |
| `eng-supply-chain` | cross-cutting | `package.json`, lockfiles, Dockerfiles, CI install steps |
| `eng-compliance` | cross-cutting | personal, financial or health data, retention, consent, or any incident with notification duties |
| `eng-ai` | cross-cutting | prompts, model calls, agent definitions, tool schemas, evals |

`eng-release`'s unconditional trigger is deliberate and is the lesson of the ATO incident: a
correct security migration sat committed and unapplied for five and a half months while the
repository believed the table was protected. Ledger drift is not a category of change — it is a
standing condition that must be checked on every review.

That trigger is **runnable, not aspirational**:
[`scripts/migration_drift.py`](../scripts/migration_drift.py) compares the repository's migration
directory against the database's applied ledger. Exit 0 in sync, 1 drift, 2 cannot determine — and
2 seats `eng-release` exactly as 1 does, because a check that cannot reach the database is the same
silent fail-open it was built to catch. Run `migration_drift.py self-test` first: it is the
positive control, and a drift check that has never failed is indistinguishable from one that
cannot fail.

## Category ownership

All ten categories are answered on every review. A category with no specialist seated falls to the
chair, so the contract in `categories.md` never weakens because the bench was small.

| Category | Owner | Falls back to |
|---|---|---|
| `data_model` | `eng-data` | `boris` |
| `invariants` | `eng-authz` | `boris` |
| `failure_modes` | `eng-failure` | — always seated |
| `interface_contract` | `eng-contract` | `boris` |
| `concurrency` | `eng-concurrency` | `boris` |
| `migration` | `eng-data` | `boris` |
| `rollback` | `eng-rollback` | `boris` |
| `observability` | `eng-observability` | — always seated |
| `budget` | `eng-performance` and `eng-cost` | `boris` |
| `test_oracle` | `eng-test` | — always seated |

## Cost discipline

A trivial change seats four and costs four reviews. A schema change touching auth and money seats
nine. Nothing seats all seventeen unless the change genuinely spans them — and if it does, that is
itself the finding: the change is too big, and the chair should return a decomposition instead of
a review.

Seats run **in parallel**, not in sequence. They are independent lenses, and a seat that has read
another seat's findings is no longer independent.

## Disagreement

Seats are told to state contradictions explicitly rather than omit them. The chair arbitrates and
records both positions in the merged artifact. A bench that silently averages its disagreements is
worth less than any single member of it.

## Adding a seat

A new seat earns its place by naming a failure class that the existing seventeen provably missed —
with the incident or review that proves it. Seats added on the grounds that a domain "seems
important" dilute every dispatch that follows.
