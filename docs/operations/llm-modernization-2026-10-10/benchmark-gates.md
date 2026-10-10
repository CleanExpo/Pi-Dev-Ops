# Representative benchmark and rollout gates

The offline doctor tests measure inventory correctness and secret containment.
They do not measure LLM output quality. The following local fixtures define the
remaining comparison; no provider inference or paid Evals run is part of this change.

Use [fleet adoption](fleet-operations.md) for host installation and conditional
Pi-Dev-Ops adoption, and [receipt templates](templates.md) to retain exact evidence.

| Case | Fixed input and acceptance | Failure that must block rollout |
|---|---|---|
| Small existing-stack fix | Known repository bug, exact starting SHA, narrow file scope, regression fixture | Passing test mirrors implementation or unrelated rewrite |
| Long investigation | Relevant code + decoy historic notes; answer cites current source paths | Treats an old handoff or transcript as current runtime evidence |
| Context checkpoint | Dirty file hashes, locked cost/publication boundary, pending check; resume preserves all | Lost approval, rollback reference, blocker or exact-tree requirement |
| Tool discovery | Task with many available tools; discover only needed schema and finish | Blind universal tool deletion or an unnecessary new connector |
| Model contract | CLI/API fixture with differing effort/thinking/tool contracts | CLI flags or effort copied into unsupported API schema |
| Independent review | Implementation containing seeded wrong path/permission/status assumption | Reviewer rubber-stamps or invents a Judge score |
| Structured extraction | Known fixture with malformed/ambiguous items and expected unknowns | Hallucinates missing values or loses Unicode/field fidelity |
| Runtime receipt | Stale `ready`, reused/live unknown PID, timeout and absent PID | Calls stale readiness healthy or invents usage/model identity |

Compare the previous task packet and the compact packet with identical fixtures,
starting trees, account constraints and maximum retries. Save prompt hashes, requested
and observed model, latency, output size, available provider usage, scope violations,
check outcomes and independent reviewer findings. Quality is acceptance pass rate
and preserved constraints; token/latency improvements count only when measured.

## Development flow and measured improvement

Use the approved stage policy in `.judge/approval-policy.md`. Bounded development
can proceed at its lower floor with owned noncritical gaps. Promotion retains
95+ and the target remains 100. This changes when a reversible candidate may be
built; it does not excuse missing security, authority, billing, workspace trust,
rollback or required evidence. The fixture acceptance bar stays fixed across the
comparison, even when the development-stage Judge floor changes.

For each fixture pair, record both prompt hashes, exact starting revision,
candidate hashes, task class, provider/version, requested and observed model,
effort, account-access evidence, maximum retries and output cap. Count elapsed
time across retries and human interventions across the whole task. Missing
provider usage remains null. Independent review must confirm acceptance and
constraint preservation for each final candidate.

The primary efficiency metric is total elapsed seconds across the matched runs,
including retries, failures and recorded blocked time, divided by accepted tasks.
With no accepted tasks the metric is null. Compare the same fixture mix and keep
acceptance pass rate and protected constraints from regressing; promotion still
needs its own 95+ Judge decision. Report human interventions separately.

Record accepted tasks per hour, acceptance pass rate, human interventions per
accepted task, elapsed time per accepted task and provider-reported tokens per
accepted task when available. Report each ratio with the sample count and failed
or blocked runs. A blocked access check is recorded as blocked; it does not become
a zero-token success. Input-byte reduction is recorded separately from loaded
tokens and output quality.

An efficiency claim needs comparable before/after receipts. For elapsed time,
divide baseline time by candidate time only for equivalent accepted outcomes;
for interventions, compare counts and report zero without division. A 10x claim
requires the named metric to reach that ratio with acceptance and protected
constraints preserved. A single passing fixture does not establish a fleet-wide
10x result. After new instructions are installed, use a fresh session and record
the loaded source version before collecting runtime measurements.

## Gates

1. **Offline assets:** unit checks pass, external receipt is parseable, no raw
   config/env/auth/session output, source files are unchanged by the audit.
2. **Guidance:** independent review confirms protected boundaries survive; source
   paths and vendor model references resolve; no unproved gain is claimed.
3. **Adapter:** mocked tests prove requested model, cwd, permissions, timeout,
   response shape and unknown usage propagate. No blind registry replacement.
4. **Included-access smoke:** current account/billing policy is compatible and one
   permitted representative task returns attributable evidence. Unavailable access
   blocks; it does not trigger an API/OpenRouter fallback.
5. **Fleet:** repeat fixtures in Claude, Codex and each relevant estate runner;
   preserve dirty worktrees and distinguish local source from running/deployed state.
6. **Runtime rollout:** promotion-stage Judge/SPM/independent exact-tree gates pass before
   runner restart, scheduling, deployment or live config activation.

Gates 3–6 remain unfinished until their receipts exist. A vendor benchmark, revised
Markdown, installed model name or offline test suite cannot close them.
