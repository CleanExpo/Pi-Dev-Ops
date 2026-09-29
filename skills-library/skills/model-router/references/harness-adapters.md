# Harness Capability and Degradation Contract

Load this reference before delegation or whenever a route depends on isolation, model/effort
override, structured output, lifecycle control, cancellation, or usage reporting. A host name alone
does not prove any capability.

## Capability probe

Each active adapter reports:

- per-dispatch model override and exact resolved-model reporting;
- effort override;
- subagents and maximum active agents;
- isolated worktrees and tool allow-lists;
- structured output;
- lifecycle hooks;
- cancellation;
- token, cost, quota, and credit reporting;
- current policy/config digest and probe timestamp.

Report each field as `supported`, `unsupported`, or `unknown`, plus evidence. Check secret/key
presence only; never read or print values.

## Common adapter boundary

```text
probe_capabilities() -> HarnessCapabilities
resolve(RouteDecision) -> ResolvedRoute
dispatch(LeafPrompt, ResolvedRoute, IsolationSpec) -> RunHandle
poll/wait(RunHandle) -> WorkerReturn
cancel(RunHandle) -> CancelReceipt
collect_usage(RunHandle) -> UsageReceipt
```

The adapter translates stable floors into the existing executable policy seam. It must not create a
second provider ladder, bypass role ceilings, or claim a requested override was honored without an
exact execution receipt.

## Host profiles

- **Claude Code:** keep the main session as driver. Use a per-task override only when the installed
  runtime proves it. An optional Stop hook may block premature turn exit but never proves completion.
- **Codex:** keep the root as driver. Enforce gates in the scheduler. Shared-workspace fan-out is
  allowed only for proven disjoint paths with return-time diff checks; otherwise isolate worktrees.
- **VS Code/OpenRouter:** probe the installed extension/agent rather than assuming one interface.
  If per-call selection or lifecycle control is absent, use an approved repository helper or operate
  advisory/serial. Apply egress policy before sending prompt data.

## Truthful degradation

1. Missing model/effort override: use the smallest currently available safe tier inline or delegate
   without claiming a lower tier; otherwise `bailout`.
2. Missing isolation: serialize mutations; read-only disjoint gathering may still fan out.
3. Missing structured output: parse once, validate, and fail closed on ambiguity.
4. Missing cancellation: do not start work whose deadline/budget contract depends on cancellation.
5. Missing usage/cost: record `unknown`; never record an invented zero or savings claim.
6. Missing exact-model reporting: record the request and `resolved_model=unknown`.
7. Missing hook support: driver/scheduler enforces completion; no hook claim appears.

Privacy or high-stakes degradation never routes remote, lowers a floor, or weakens verifier
independence. If the adapter cannot honor the minimum contract, it returns `bailout` with evidence.

The probe passes when every required control is evidenced and the chosen action can honor the route
without an unsupported or falsely reported capability.
