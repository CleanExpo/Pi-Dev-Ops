# Route Contracts

Load these schemas whenever producing, consuming, validating, or receipting a route. Reject unknown
required enums, missing identifiers, negative limits, invalid floors, or a fallback below the
selected floor. JSON examples are normative for field names, not live values.

## RoutingRequest 1.0

```json
{
  "schema_version": "1.0",
  "request_id": "uuid",
  "task": "verbatim bounded task",
  "harness": "claude-code|codex|vscode-openrouter",
  "signals": {
    "determinism": "high|medium|low",
    "ambiguity": "low|medium|high",
    "scope": "inline|bounded|multi-file|subsystem|project",
    "dependency_count": 0,
    "reasoning_depth": "shallow|normal|deep",
    "stakes": ["none|customer|auth|payment|privacy|security|legal|release|migration"],
    "volume": 1,
    "expected_minutes": 20,
    "context_tokens_estimate": 12000,
    "modalities": ["text", "code"],
    "required_tools": ["read", "edit", "test"],
    "sensitivity": "public|internal|confidential|client",
    "prior_failures": 0,
    "ownership_disjoint": true
  },
  "limits": {
    "max_cost_usd": 0.10,
    "max_quota_units": null,
    "deadline_seconds": 900,
    "max_parallel_workers": 3
  }
}
```

Use `null` for a deliberately unbounded or unreported quota only when repository policy permits it.
Use explicit `unknown` markers in receipts for unavailable measurements; never coerce missing usage
to zero.

## RouteDecision 1.0

```json
{
  "schema_version": "1.0",
  "route_id": "uuid",
  "policy_version": "git-sha-or-config-digest",
  "action": "inline|delegate|fanout|bailout",
  "task_class": "mechanical|bounded|deep|high_stakes|long_horizon",
  "worker_role": "driver|senior|worker|verifier",
  "quality_floor": "cheap|mid|top",
  "execution_location": "local_only|remote_allowed",
  "reasoning_effort": "low|medium|high|xhigh",
  "confidence": 0.91,
  "reasons": ["stable-pattern", "disjoint-ownership"],
  "privacy": {
    "data_class": "internal",
    "provider_constraints": []
  },
  "execution": {
    "max_parallel_workers": 3,
    "timeout_seconds": 900,
    "max_attempts": 2,
    "owns": ["path/a"],
    "needs": ["leaf-1"]
  },
  "budget": {
    "max_cost_usd": 0.10,
    "max_quota_units": null,
    "reservation_required": true
  },
  "verifier": {
    "quality_floor": "mid",
    "reasoning_effort": "high",
    "independent": true
  },
  "escalation_on": ["two-failed-attempts", "low-confidence", "contract-drift", "security-signal"],
  "fallback": ["mid", "top", "bailout"]
}
```

`reasons` and `escalation_on` use stable machine-readable slugs. The human explanation is separate.
An inline decision still declares limits and verifier requirements. A bailout identifies the unmet
contract in `reasons` and performs no dispatch.

## RouteReceipt 1.0

A post-resolution receipt contains the full decision plus:

- `resolved`: harness, exact provider/backend/model, selection source, and whether each requested
  control was honored;
- `usage`: input/output/reasoning/cache tokens, billed cost, marginal cost, quota/credit units, and
  `known|unknown|not_applicable` state per measure;
- `attempt`: start/end timestamps, latency, fallback chain, attempt count, and terminal status;
- `provenance`: repository, worktree, base SHA, candidate SHA, policy/config digest, plan/node/gate
  identifiers, and runner version;
- `verification`: leaf/root gate outcomes, verifier receipt ID, and comparable-outcome flag;
- `baseline`: baseline policy/version and price snapshot when a savings comparison is claimed.

Do not store secrets, raw client data, full upstream errors, or unbounded stdout/stderr. A receipt may
say `billed_cost_usd=0` only when observed; quota consumption remains a separate field.

## Validation invariants

1. `confidence` is between 0 and 1; numeric caps and timeouts are finite and non-negative.
2. Confidential high-stakes work is `local_only + top` for worker/verifier or `bailout`.
3. Verifier floor is never below worker floor; high-stakes verification is independent.
4. Fan-out requires `max_parallel_workers >= 2` and disjoint owned paths.
5. Fallback is monotonic and ends in `bailout` when no safe target exists.
6. A savings claim requires equal root-gate outcome, actual usage, and timestamped baseline prices.
7. The policy digest and route ID bind the complete declared policy semantics, not only a version
   label.

The contract is complete when schema validation and all invariants pass.
