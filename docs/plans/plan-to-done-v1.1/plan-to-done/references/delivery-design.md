# Delivery design: specify the harness without running it

## Existing lifecycle, not a competing one

Fetch the live UNI-2517 contract and applicable governing rules when planning a real mission.
The snapshot inspected for this skill design defines the following minimum delivery semantics:

IDEA → DISCOVERED → PLANNED → BUILD_AUTHORISED → EXECUTING → LOCALLY_VERIFIED → PR_OPEN →
REVIEWING → CI_GREEN → STAGING_VERIFIED → RELEASE_READY → SHIP_AUTHORISED → PRODUCTION →
POST_DEPLOY_VERIFIED → COMPLETE.

Use the canonical machine-readable lifecycle when available. This reference is a design
cross-check, not a new state engine. Quality checks can be prerequisites to an earlier action:
for example, current Library rules require independent pre-PR review even though REVIEWING is
also a named downstream lifecycle state. Write those dependencies; do not bypass pre-PR gates.

## Transition matrix to write

| Boundary | Required planning specification |
|---|---|
| Discovery to planned | Baseline, accepted outcome, scope, coverage, testable requirements and engineering decisions |
| Planned to build admission | Exact plan revision, applicable grant, dependencies, permitted tools/hosts, budget and reviewer reserve |
| Build to local verification | Frozen candidate, required commands, test data, negative controls and evidence capture |
| Candidate to push/PR | Current release-gate obligations, independent review, exact-head receipts and explicit authority |
| Review to release-ready | Resolved blockers, required CI, staging behaviour, visual checks and operational readiness |
| Release-ready to production | Separate release authority, target artefact, environment, migration/configuration and recovery plan |
| Production to verified outcome | Provider readback, deployed identity, intended user behaviour, health and observation window |
| Outcome to complete | All applicable required outcomes evidenced, permitted exceptions recorded and ownership handed over |

Each row must name preconditions, input/output references, responsible capability, authority,
evidence producer, independent checker, freshness rule, failure state and recovery path.
The plan is not itself an action grant. This skill cannot perform any transition by execution.

## Three different controls

Human authority determines whether an action may happen. Deterministic gates check whether
the defined conditions are met. Models propose, reason and review within those boundaries.
An advisory score, a majority vote or the text "APPROVE BUILD" is not an authority receipt.
A requirement to pass all mandatory checks must not become an uncalibrated 100/100 opinion.

Preserve the existing rules for merge, deploy, publish, spend, credentials and destructive
operations. Resolve an existing valid grant by scope, identity and expiry; do not either
ignore it or reinterpret it as unlimited permission. A denied action cannot be retried through
another tool or account. A planning-only request never authorises building.

## Durable work and recovery design

Specify one mission identity across workers and sessions, content-bound checkpoints, one
mutation owner per task, leases with fencing or equivalent stale-owner rejection, and cancellation
propagation. Do not promise exactly-once external effects merely because a lease exists.
Use idempotency keys where supported and reconcile ambiguous external outcomes before retry.
On partition or lost authority, stop the affected mutation and preserve resumable state.

The recovery plan must distinguish transient failures, bad inputs, missing evidence, quota
limits, unavailable reviewers, security incidents and authority refusal. Retry only bounded,
permitted actions. Repeated failure without new evidence becomes a diagnostic case, not an
infinite rephrasing loop. Continue independent authorised work only if dependencies and
incident containment allow it. Never let an optional Jev outage create an unnecessary global stop.

## Resource design

Record account/route eligibility, data policy, host capability, subscription versus metered
usage, task budget, concurrency, timeout and review/recovery reserves. Do not assume a product
subscription includes API access. Do not silently select paid fallback. Avoid transmitting the
entire context to every role; reference the canonical packet and supply relevant excerpts.

## Verification and release evidence

Bind evidence to the intent/spec revision and candidate commit or dirty-tree digest, and to
the built artefact, dependencies, relevant configuration and environment where applicable.
A source SHA alone does not identify every possible build output. List required local tests,
remote checks, integration/security checks, browser/visual journeys and post-release outcomes.
After a candidate changes, invalidate or re-establish affected evidence. Required skipped
checks are not passes. Author self-review never fulfils an independent-review requirement.

Write rollout, rollback or forward-repair, backup/restore, monitoring, alert routing, runbooks,
training and support responsibilities when applicable. A database migration may not be undone
by reverting application code. State success thresholds, observation window and failure triggers
from the agreed risk/operational contract, not invented universal values.

## Separate completion claims

The planning packet may be accepted without a line of product code being written. A feature
may satisfy its contract while the product remains incomplete. Production presence does not
prove the user outcome. Keep all three distinctions visible in the handoff and planned UI.
