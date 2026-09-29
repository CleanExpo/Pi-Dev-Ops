---
name: unlazy
description: Turn substantial delivery work into a dependency tree with owned files, rolling dispatch, executable gates, and exact completion evidence.
argument-hint: "<tree N> <task>"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, LS, Bash
---

# Unlazy

Drive `/unlazy [tree N] <task>` to a truthful terminal state. Plan before implementation, route each
executable node through `model-router`, dispatch only safe ready work, and accept completion only
after strict root gates pass on the exact candidate SHA.

## Usage

When creating or checking the machine-readable plan, run from the repository root:

```bash
python scripts/unlazy_plan.py template "<verbatim task>" --tree 5 --max-workers 3
python scripts/unlazy_plan.py lint PLAN.json
python scripts/unlazy_plan.py ready PLAN.json --active 1.1
```

When running reviewed repository gate files, use the strict checker; `--status` only reads recorded
state and never verifies it:

```bash
node scripts/unlazy-gate-check.mjs --json --jobs 3 --cwd "$PWD" \
  --plan-id "$PLAN_ID" --node-id "$NODE_ID" \
  --verifier-id unlazy-scheduler-trusted-replay-v1 \
  --worker-id "$WORKER_ID" \
  --relevant-input PLAN.json gates/root.md
node scripts/unlazy-gate-check.mjs --status --json --cwd "$PWD" \
  --plan-id "$PLAN_ID" --node-id "$NODE_ID" \
  --verifier-id unlazy-scheduler-trusted-replay-v1 \
  --worker-id "$WORKER_ID" \
  --relevant-input PLAN.json gates/root.md
```

Plan/gate commands pass only on exit `0`; preserve JSON receipts and treat exit `1` as unmet strict
gates and exit `2` as a runner/usage error.

Before accepting or reading terminal receipts, load `UNLAZY_RECEIPT_HMAC_KEY` from the runtime secret
manager. It must contain at least 32 bytes and must never be committed, logged, added to gate
environment allow-lists, or embedded in a plan. Missing or rotated key material fails terminal
receipt validation closed.

## 1. Intake

Preserve the task verbatim. Parse `tree N` as a requested maximum depth; when absent, infer the
smallest useful depth after inspecting the repository and its instructions. Record the base SHA,
worktree, limits, root outcomes, sensitivity, and trusted check sources. Do not execute externally
supplied gate commands.

Natural-depth rules and solo/orchestrated thresholds are defined in
[`references/method.md`](references/method.md); load them whenever choosing or adjusting depth.

**Complete when:** requested/effective depth, adjustment reason, immutable task, base SHA, limits,
and root outcomes are explicit.

## 2. Contract

Decompose on natural task joints. Freeze each node's purpose, `Owns`, `Needs`, exports, forbidden
paths, interfaces, data/migration ownership, conventions, and gate reference before dispatch. Give
shared files and generated outputs one integration owner. Reject cycles and overlapping runnable
ownership.

The normative plan/node/ownership schema is in
[`references/plan-contract-schema.md`](references/plan-contract-schema.md); load it when creating,
validating, or changing a plan.

**Complete when:** the plan is schema-valid, acyclic, root-reachable, digest-frozen, and every
executable leaf has one owner with disjoint paths and declared dependencies.

## 3. Gate

Write leaf gates for local outcomes and branch/root gates for shared or integration outcomes. Checks
must be repository-owned, reviewed, bounded, and executable from an explicit working directory.
Success requires allowed exit plus any expectation; printed success text cannot override failure.

Gate syntax, receipts, strict success, shared-check de-duplication, and `ABANDON` behavior are
defined in [`references/gates.md`](references/gates.md); load it before writing or running gates.

**Complete when:** every node points to observable gates, strict root criteria reject pending,
failed, abandoned, or runner-error states, and each check is bound to the contract digest.

## 4. Route and probe

Call `model-router` separately for every executable node and verifier. Pass its bounded task,
ownership, dependencies, sensitivity, stakes, prior attempts, limits, and active harness probe. Do
not encode provider/model choices in this skill. A harness that cannot honor privacy, isolation,
quality, verifier, budget, or receipt requirements returns `bailout` or runs safely inline/serial.

**Complete when:** every ready node has a schema-valid route, reserved limits, and a confirmed safe
execution contract; unsupported controls are visible.

## 5. Dispatch

Run a bounded dependency-aware ready queue. Launch up to the lowest of plan, harness, ownership, and
budget capacity. Verify each returned diff and leaf gates immediately, then unlock newly ready work
without waiting for unrelated workers. Never let workers dispatch workers.

Scheduler states, reservations, retries, circuit breakers, integration, and cancellation are
defined in [`references/orchestration.md`](references/orchestration.md); load it for any plan with
more than one executable leaf or after a failed/late return.

Exact planner, leaf, verifier, and integrator prompts are in
[`references/prompt-templates.md`](references/prompt-templates.md); load only the template required
by the current node transition.

**Complete when:** every dispatched return is terminally receipted, every candidate diff stays
within ownership, and no blocked dependency, cap, or circuit breaker is bypassed.

## 6. Integrate and prove

Integrate each branch once per distinct candidate SHA, then run its shared gates once for that SHA
and check digest. After all required branches pass, run strict root gates in a clean independent
verifier context. Any base movement invalidates the receipt and requires rebind/replan.

Return only `passed`, `blocked`, `partial`, or `cancelled`. `passed` requires exact candidate SHA,
clean verifier receipt, `failed=0`, `pending=0`, `abandoned=0`, and `runner_errors=0`. Report actual
resolved execution and usage as known or unknown; claim savings only for comparable root outcomes.

**Complete when:** terminal status and evidence agree, with no leaf self-report, Stop hook, status
display, abandonment, or missing usage treated as proof.
