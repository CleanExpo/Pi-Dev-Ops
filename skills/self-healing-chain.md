# The self-healing chain

Nine single-purpose skills. Each is reachable on its own; the chain is the default order, not a requirement.

```
prove-the-failure → contain → diagnose → classify ─┬→ propose-fix → adversarial-review → verify → immunise → incident-memory
                                                    └→ (stop, report with diagnosis) ──────────────────────→ incident-memory
```

`classify` is the gate. Three of its four outcomes are stop. That is the design.

## Chain-wide constraints

**Two gates, the same two as everything else.** No step spends money or mutates production without the founder. The chain has no special standing — a self-healing action is an action.

**`immunise` may propose a fence change; it may never apply one.** Fence rule files are on the self-modification list and freeze the agent on the *first* attempt. There is no bounded-retry allowance and no "the fix requires it" exception. A chain that can widen its own fence is not fenced.

**Bounded retries: three attempts, each materially different.** Then stop and report the diagnosis rather than the error. Giving up is a valid, logged outcome with the same standing as a fix.

**R3 is a different rule and must not be conflated.** Retrying a *denied* action is terminal — a second attempt freezes the agent. Retrying a *failed repair* is permitted within the bound of three. A denied action was never attempted; a failed repair was attempted and did not work. If a fence denial occurs mid-repair, the denial is terminal and the attempt bound does not license retrying it. This distinction is restated in full inside `propose-fix`, deliberately, so an agent reading only that skill still gets it right.

**Circuit breaker over the whole chain.** If completed remediations in the trailing 24 hours reach three, the chain halts entirely — not just the current failure — writes the trip to incident memory, and calls the founder. Reset is human-only. A system repairing itself repeatedly is failing repeatedly with the evidence smoothed over.

**Never spec an unbounded negative.** A spec item that asks a reviewer to prove something never happens — no network call, no write, no side effect — cannot be satisfied, because there is always one more path. Write bounded, diff-relative claims: *"introduces no X the source did not have"*. Where the baseline's own safety properties are load-bearing, establish that baseline by hand before the port and cite it. Full rule in `adversarial-review`.

**No expert personas.** Sub-agents are task-execution tools with narrow briefs and word limits. `adversarial-review` gets its value from what the reviewer *cannot see* — the builder's reasoning — not from pretending to be a senior engineer. Separation of model and context is the mechanism; roleplay is noise.

## Lineage

`prove-the-failure` is `diagnosing-bugs` Phase 1 (mattpocock/skills), made into a hard gate. `adversarial-review`'s dual-axis structure is from `code-review` (same repo). The phase-gate form, imperative voice, and checkbox completion criteria follow that house style throughout.

## Status

Built, not installed. Not wired to any trigger. The fence remains in shadow.
