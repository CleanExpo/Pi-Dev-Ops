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

This slice vendors the Unlazy method and its machine-readable contracts. It ships **no** plan linter
and **no** gate runner: there is no `unlazy_plan.py` and no `unlazy-gate-check.mjs` here, so do not
invoke either. Write `PLAN.json` by hand against
[`references/plan-contract-schema.md`](references/plan-contract-schema.md) and validate it by reading
that schema, not by running a bundled CLI.

Run gates with the repository's own reviewed check commands — the ones its contributing guide,
`package.json`, or `Makefile` already define — and record their exact command, exit code, and
terminal summary in the plan node. A gate passes only on the exit code the gate file declares
(default exactly `0`); treat any other exit as an unmet gate and a crash or usage error as a runner
error, never as a pass.

Where a host does supply an Unlazy scheduler and gate runner, the receipt, execution-context, and
HMAC requirements it must satisfy are specified in [`references/gates.md`](references/gates.md) and
[`references/orchestration.md`](references/orchestration.md). Those are requirements on that runner.
Nothing in this skill issues, signs, or verifies a terminal receipt, so never present a hand-written
plan or an unverified summary as one.

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
