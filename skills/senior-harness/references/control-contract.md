# Senior Harness control contract

Load this reference when a task crosses the Senior Harness boundary. The JSON file is the control
plane; prose, chat history, a model conclusion, or a worker self-report cannot override it.

## Hierarchy

```text
current user instruction
  > Senior Harness contract and policy
  > Lead LLM route proposal
  > specialist and worker execution
  > independent verifier
  > independent technical arbiter
  > human only for unresolved authority or business decisions
```

The verifier and arbiter are gates below the Harness, not permission to widen the task. Horizon is a
read-mostly advisory plane. Its proposals must pass an admission move before any delivery action.

## Startup admission

Before the TaskContract exists, `scripts/setup_driver.py` creates a separate startup contract and
receipt. It freezes the literal objective, exact Git checkout and HEAD, dirty-state digest, driver
digest, resolved skill-folder digests, a truthful host capability probe, the executable
model-router request and decision, and the requirement that Unlazy own downstream delivery control.
A valid startup receipt may admit mediated nonmutating discovery and planning. It is not a TaskContract, route receipt,
Unlazy plan, verification receipt, signed authority lease, or mutation permission.

Codex project hooks require repository trust and do not intercept every hosted or specialised tool.
Claude project hooks can be disabled by bare/safe modes. Therefore hook presence proves only the
named mediated lifecycle surface; remote branch protection, CI gates, and trusted runtime authority
adapters remain separate controls.

The project PreToolUse adapter requires startup admission and injects the objective lock; it does not
classify generic shell, edit, or MCP mutation authority. Those calls remain under existing host and
repository controls. The deterministic `guard-dispatch` boundary is narrower: it admits only a
ready, nonmutating delivery move and rejects stopped uncertainty paths.

An invalid or missing hook receipt does not strand diagnosis. Exact read-only recovery tools may
continue with a zero-authority warning; mutation, provider, worker, browser computer-use, and
outbound tools remain denied. Control-code digests are enforced at startup and the first mediated
tool. After that first tool in a normal delivery session, later Harness-code drift is reported as
stale evidence instead of becoming a blanket tool denial. This is not re-admission: the old receipt
cannot serve as fresh control-code evidence, and Grill interactions continue byte revalidation on
every tool.

For `grill-me` and `grill-with-docs`, the adapter narrows further. Until the Grill session reaches
explicit shared understanding, it admits only read-only evidence discovery and the dedicated Grill
state driver. The driver binds a real sketch and decision-tree, separates evidence facts from human
choices, exposes at most one question, retains answers verbatim, and buffers transcript/domain changes.
The confirmed receipt still grants zero authority. `guard-dispatch` may use it to admit a ready
nonmutating delivery move only; the existing mutation-authority stop remains in force. The complete
state contract is [`grill-contract.md`](grill-contract.md).

## TaskContract

Required top-level fields:

| Field | Contract |
|---|---|
| `schema_version` | Exactly `1.0`. |
| `stage` | `delivery-contract` before lint or dispatch. |
| `task_id` | Deterministically derived from the exact literal request. |
| `observed_at` | Timezone-aware instant used by the five-minute evidence freshness gate. |
| `literal_request` | Verbatim current instruction. |
| `authorized_scope` | Must contain the literal request; additions need explicit authority. |
| `authority_grants` | Empty in schema v1; approval authentication belongs to a trusted runtime adapter. |
| `inferred_outcomes` | Statements with provenance, confidence, and proposal-only status. |
| `classification` | Boolean `horizon_required` plus rationale. |
| `limits` | Parallel, node, branch, attempt, evidence-time, and spend ceilings. |
| `required_skills` | Must include `model-router` and `unlazy`. |
| `repository` | Exact base SHA, nullable pre-build candidate SHA, and absolute worktree. |
| `discovery_runs` | Per-run question, allowlists, time/spend, retention, value threshold, and stops. |
| `forecasts` | Separately scored ForecastContracts; never use scenarios as predictions. |
| `move_graph` | Acyclic list of MoveContracts. |
| `attempts` | Materially distinct pathway attempts with computed fingerprints. |
| `uncertainty_cases` | Stopped problems under independent investigation. |
| `verification` | Planned distinct principals and required receipt types; not proof. |
| `capability_pack` | Candidate, provisional, durable, or stale learning state. |

## MoveContract

Every move contains:

```json
{
  "move_id": "M01",
  "parents": [],
  "plane": "horizon",
  "kind": "observe",
  "state_delta": "A new observable state that did not exist before.",
  "owner": "logical-role-id",
  "prerequisites": [],
  "evidence_ids": ["E-source"],
  "confidence": 0.9,
  "counter_case": "What would make this move wrong.",
  "value": "Why the move earns attention.",
  "cost": "bounded estimate or class",
  "reversibility": "reversible",
  "trigger": "Observable condition that admits the move.",
  "expiry": "2026-09-21",
  "status": "proposed",
  "authority_required": "none",
  "authorization_status": "not-required",
  "authority_source_id": null
}
```

Allowed planes are `horizon`, `delivery`, `verification`, and `learning`; every plane has a closed
kind list. Unknown action names fail. Every mutating delivery kind names its required authority but
must remain `authorization_status: proposal` with no authority-source claim in schema v1. Hashing the
literal request proves integrity, not permission. Therefore schema v1 never returns mutating moves as
ready; a trusted runtime adapter must authenticate policy or human approval before execution. Delivery must descend from an
`admit` move, and only an `admit` move may cross directly from Horizon to delivery.
Meaning-identical state deltas, cycles, missing parents, empty triggers, and branch-width violations
fail closed. A horizon-bearing graph needs a longest linked path of 15–20 state-bearing moves; total
nodes remain bounded separately. The checker proves structure, not semantic value: an independent
verifier must reject filler or label-only deltas.

## Discovery and forecasts

Topical discovery may expand, but each `discovery_runs` entry is operationally bounded. It needs a
single scoping question, source and privacy allowlists, maximum minutes and spend, retention period,
value-of-information threshold, and observable stop conditions. Horizon-bearing work needs at least
one such run.

A move with `kind: forecast` requires a separate ForecastContract. Outcome labels must be unique,
probabilities must sum to one, and a `mutual_exclusivity_rationale` makes the semantic claim
reviewable. The contract also freezes a resolution criterion, resolution source and date,
scoring-rule version, and freeze time. Score it only after the resolution receipt exists; a strategic
scenario or move is not automatically a prediction.

## Attempt pathway

The deterministic fingerprint covers only the decision available before execution:

```json
{
  "route_id": "route-from-model-router",
  "input_sha256": "sha256:immutable-input-digest",
  "problem_id": "P-runtime",
  "hypothesis": "configuration drift",
  "method": "query-authoritative-source",
  "tool_path": "connector-id",
  "source_set": ["source-id"],
  "model_class": "senior"
}
```

Attempt IDs, timestamps, labels, output, and final status do not alter the pathway fingerprint. Source
order and duplicates are normalised. A repeated fingerprint is the same route and is rejected.
`failed`, `runner-error`, `blocked`, and `timed-out` count toward the two-attempt stop. The contract's
`observed_at`, attempt start, and last-authoritative-evidence timestamps enforce the five-minute stop.
An open uncertainty case needs `stop_current_path: true`, at least two unique specialists, a separate
non-empty arbiter, evidence IDs, a discriminating experiment, and a resolution criterion.

## Evidence and acceptance

Authenticated evidence receipts must bind:

- literal request and TaskContract digest;
- base and exact candidate identities;
- canonical skill IDs and the runtime `where` command's full skill-folder digest;
- route decision and execution-control receipts;
- raw command, working directory, exit code, and redacted output hash;
- builder, verifier, and arbiter identities;
- authoritative source IDs and freshness;
- actual usage where available, otherwise an explicit unknown reason.

Status text and identity strings are not evidence. Schema v1 deliberately rejects non-empty receipt
claims because it has no trusted signature adapter. A focused check proves only its stated scope. Any base movement,
contract change, gate change, missing receipt, identity collision, or runner error invalidates the
acceptance decision.

## Capability lifecycle

```text
candidate
  -- first independent verified success --> provisional
  -- qualified fresh replay -------------> durable
  -- bound stack or vendor drift ---------> stale
  -- independent revalidation ------------> durable
```

A qualified replay uses the frozen pack, a separate principal, a fresh workspace, no prior task
cache, objective evaluation, and new receipts. Schema v1 accepts `candidate` only; a trusted signed
exact-SHA adapter owns every later transition. A failed replay leaves the pack provisional or stale;
the Lead LLM cannot promote it by explanation.

## Self-hosting acceptance

The repository fixture `tests/fixtures/senior_harness_self_host.json` describes the Harness building
itself across 18 linked moves. This replay proves validator consistency and mutation resistance, not
independent acceptance:

```bash
python skills/senior-harness/scripts/senior_harness.py lint tests/fixtures/senior_harness_self_host.json
python -m pytest tests/test_senior_harness.py -q
```

The positive control must pass. Mutation controls must reject a short horizon, a cycle, duplicate
state, Horizon execution, missing authority, self-verification, repeated attempts, missing
uncertainty escalation, and unsupported capability promotion.
