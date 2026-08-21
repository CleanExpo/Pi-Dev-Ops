# Bounded Rolling Orchestration

Load this scheduler contract for any plan with multiple executable leaves, any failed/late return,
or any branch integration. It is a dependency-aware ready queue, not wave-based fan-out.

## State machine

```text
pending -> ready -> running -> verifying -> passed
                                      \-> blocked
pending|ready|running ----------------> cancelled
```

Only dependencies all in `passed` make a node ready. Branch/root nodes enter verifying only after
their required children pass and their candidate is integrated.

## Driver loop

```text
validate plan, ownership, privacy, capabilities, and budget
while root is non-terminal:
  mark dependency-satisfied nodes ready
  select ready nodes with no ownership collision
  reserve spend/time/slots atomically
  dispatch up to min(plan cap, harness cap, ownership cap, budget cap)
  on each return:
    freeze candidate SHA and diff
    verify owned paths and leaf gates immediately
    pass -> receipt and unlock dependants
    fail -> targeted retry or monotonic escalation
  integrate a complete branch once
  run branch gates once for its SHA and check digest
  trip circuit breaker on hard contract violation
run root gates in a clean independent verifier context
```

Do not wait for an entire wave: dispatch newly unblocked work while unrelated leaves continue.
Workers are leaves and may not dispatch other workers.

## Bounds and reservations

- Default active workers: three; the driver is not a worker. Never exceed user, repository, harness,
  ownership, privacy, budget, or deadline caps.
- Reserve estimated maximum spend before dispatch and release unused amounts on terminal receipt.
- Stop launching new work when 80% of run budget or deadline is reserved; let active leaves return,
  verify them, then reassess.
- Default attempts: two (initial plus one targeted repair). A third requires an explicit upward
  escalation receipt and a still-valid budget.
- Missing usage is `unknown`, not zero. Unknown usage may block further paid dispatch when a cap
  cannot be proven.

## Return verification

For every return:

1. bind base/candidate SHA and enumerate the diff;
2. reject paths outside `owns`, moving base, missing candidate, or contract-digest mismatch;
3. rerun approved leaf gates in an independent verifier context;
4. record actual execution controls, usage knowns/unknowns, and terminal result;
5. unlock dependants only after `passed`.

Only a leaf already in `verifying` may receive a terminal result, and the result flag must be a JSON
boolean. Never coerce strings or skip the `running -> verifying` boundary.

A worker summary is not evidence. A failed leaf may retry once with the exact unmet gates. The
second comparable failure escalates capability or blocks; it does not loop.

## Circuit breakers

Stop the affected branch on ownership collision, contract drift, privacy violation, injection,
unreviewed gate change, hard dependency failure, corrupted ledger, exhausted cap, or cancellation.
Cancel only dependants of a blocked hard dependency; independent branches may continue within caps.

Late returns after cancellation are receipted and quarantined, never integrated. Cancellation
releases reservations exactly once.

## Integration and root

One integration node owns shared files. Integrate each branch once per candidate SHA, run its shared
gates, and cache only by the strict gate digest. Root `passed` requires all dependencies, an exact
integration SHA, a clean independent verifier, and strict gate counts at zero.

The loop is complete only when every reservation reconciles, every dispatched node has one terminal
receipt, and the root is truthfully `passed`, `blocked`, `partial`, or `cancelled`.
