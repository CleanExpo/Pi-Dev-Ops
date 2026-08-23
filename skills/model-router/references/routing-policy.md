# Routing Policy

Load this policy when classifying substantive work, routing an executable node, or handling a
failed attempt. It is the single source of truth for task floors and escalation. Exact provider and
model mappings belong downstream in versioned runtime configuration.

## Orthogonal fields

| Field | Values | Meaning |
|---|---|---|
| `task_class` | `mechanical`, `bounded`, `deep`, `high_stakes`, `long_horizon` | Reasoning and risk shape. |
| `worker_role` | `driver`, `senior`, `worker`, `verifier` | Responsibility and authority. |
| `quality_floor` | `cheap`, `mid`, `top` | Minimum capability, not a provider or location. |
| `execution_location` | `local_only`, `remote_allowed` | Data-egress constraint, not capability. |

## Constraint intersection

Compute a baseline, then intersect every applicable constraint:

1. Mechanical, deterministic, low-stakes work starts at `worker/cheap`.
2. Bounded production work starts at `worker|senior/mid`.
3. Deep or long-horizon work starts at `driver|senior/top`.
4. Auth, payment, privacy, security, legal, migration, or irreversible release work is
   `high_stakes`, requires `senior/top`, and an independent `verifier/top`.
5. `confidential|client` data is `local_only` unless a current explicit data-use policy permits
   that class. Location never lowers capability.
6. If no allowed execution target can meet both location and quality floors, return `bailout`.
7. Repository policy ceilings and allow-lists can raise or reject a route; the router cannot bypass
   them.

## Action

- `inline`: under ten focused minutes, no useful fan-out, no independent-verifier requirement, and
  the current agent meets all floors.
- `delegate`: one bounded node benefits from separate execution or verification.
- `fanout`: at least two ready nodes, disjoint ownership, useful parallel work, sufficient reserved
  budget/time, confirmed harness capacity, and cancellation support for a time-bounded run.
- `bailout`: privacy, isolation, policy, capability, receipt, budget, or verifier contract cannot be
  preserved.

An explicit zero cost, quota, or deadline is a hard zero, not an unknown value. It blocks delegated
and fan-out work. Use `null` only for an intentionally unbounded or unreported optional budget when
repository policy permits it. Missing cancellation degrades otherwise-valid timed fan-out to one
worker; it never leaves multiple workers running beyond the declared boundary.

Non-finite numeric limits (`NaN` or infinities) are invalid input, never an unbounded cap. Work at
the `top` quality floor is never inline because its independent verifier must remain a separate
execution boundary.

Gathering work is non-mutating `worker/cheap` unless another constraint raises its floor or changes
its location. Do not treat high volume as high stakes by itself.

## Role and verifier floors

| Role | Authority | Typical floor | Verification |
|---|---|---|---|
| `driver` | intent, plan, dispatch, integration, root result | `top` | Does not verify its own leaf. |
| `senior` | architecture, subtle debugging, migrations, security design | `mid\|top` | Independent, equal or higher floor. |
| `worker` | frozen implementation or non-mutating gathering | `cheap\|mid` | Never below worker; production mutation defaults to `mid`. |
| `verifier` | diff boundary and gate rerun | `mid\|top` | Fresh context; no candidate repair. |

Verifier independence means a different execution context that did not author the candidate. A
worker self-check is evidence for handoff, not acceptance.

## Retries and escalation

- Attempt 1 may retry once at the same floor only with named failing-gate feedback.
- A second comparable failure escalates monotonically: `cheap -> mid -> top -> bailout`.
- Contract drift, ownership collision, privacy violation, injection attempt, or security signal
  stops affected dispatch immediately; do not retry the same contract blindly.
- Fallbacks may preserve or raise quality and privacy restrictions; never downgrade either.
- Low-confidence classifier output escalates or bails out.

## Overrides

Accept overrides that raise capability, lower concurrency, tighten privacy, or lower spend. Reject
an override below a hard floor and cite the governing signal. Do not ask the user to choose an
exact provider/model for a known task class.

## Completion check

A route passes policy only when the action is executable under current capabilities, all floors are
preserved, the verifier is independent where required, ownership is disjoint for fan-out, limits
are bounded, and fallback cannot silently weaken the contract.
