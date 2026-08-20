---
name: model-router
description: Use before substantive work when choosing whether to work inline, delegate, fan out, or escalate based on ambiguity, stakes, scope, repetition, privacy, and prior failure.
allowed-tools: Read, Grep, Glob, LS, Bash
---

# Model Router

Classify work before execution. Emit a stable capability contract; leave exact runtime/provider
resolution to the active policy seam. Never dispatch, edit, execute the requested task, or declare
it complete.

## Usage

When a caller needs the repository's machine-readable classifier, run from the repository root:

```bash
python -m app.server.task_routing request.json
# or: python -m app.server.task_routing < request.json
```

Pass one `RoutingRequest` JSON object by file or standard input. Treat exit `0` plus schema-valid
stdout as a decision, not execution proof; any other exit or invalid JSON fails closed.

## 1. Normalize

Convert the request and current context into a `RoutingRequest`. Preserve the bounded task verbatim.
Estimate signals from inspected evidence; use `unknown` rather than inventing capability, cost,
quota, privacy, or harness support.

The request, decision, and receipt fields are defined in
[`references/route-decision-schema.md`](references/route-decision-schema.md); load it whenever a
machine-readable route or validation is required.

**Complete when:** every required request field is present, enums are valid, and uncertain facts
are explicit.

## 2. Intersect

Apply every applicable constraint. Privacy, stakes, policy ceilings, and verifier independence are
hard floors; cost and capacity are tie-breakers only. Keep task class, worker role, quality floor,
and execution location independent.

The deterministic floors, fan-out rules, escalation ladder, and override rules are defined in
[`references/routing-policy.md`](references/routing-policy.md); load it whenever classifying a
substantive task or retry.

**Complete when:** the route preserves every hard floor and no cheaper choice weakens correctness,
privacy, or verification.

## 3. Probe

Use the active harness capability probe before claiming that delegation, isolation, model/effort
override, structured output, cancellation, hooks, or usage reporting is available. Check only key
presence; never print secrets. Unsupported controls degrade truthfully to a safe inline/advisory
route or `bailout`.

Capability contracts and truthful degradation are defined in
[`references/harness-adapters.md`](references/harness-adapters.md); load it when the route may leave
the current agent or needs a harness-specific control.

**Complete when:** every required control is marked supported, unsupported, or unknown, and the
selected action can honor the minimum contract.

## 4. Decide

Use deterministic rules first. Call a bounded classifier only when a material decision remains
unresolved after evidence inspection. Validate its response against the decision schema. Low
confidence escalates upward or bails out; it never lowers a floor.

The normalized prompt sequence and classifier template are defined in
[`references/prompt-pathway.md`](references/prompt-pathway.md); load it only for ambiguous routes or
when another skill needs the exact prompt pathway.

**Complete when:** exactly one schema-valid `RouteDecision` exists with stable reason codes,
bounded execution, budget, verifier, escalation, and fallback contracts.

## 5. Return

Return the decision JSON plus one compact line:

```text
<action> <parallel-cap> | <role> <floor> | verifier <floor> | cap <amount-or-unknown> | privacy <class>
```

Do not name an exact provider/model before downstream resolution. Do not claim savings from a route
decision. Actual selection, usage, gates, and comparable-outcome evidence belong in a later
`RouteReceipt`.

**Complete when:** the caller receives one valid decision and a human line that does not overclaim
execution, support, cost, or completion.
