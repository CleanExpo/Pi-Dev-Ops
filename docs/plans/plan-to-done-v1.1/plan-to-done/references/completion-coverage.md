# Whole-project completion coverage

## The two scopes

Keep two linked scopes: the product's agreed completion boundary and the specific change being
planned. A request to finish a product uses the first. A request to improve one feature uses
the second while retaining visibility of wider unresolved product gaps. Do not automatically
expand a feature change to fix everything found.

The key reconciliation is:

`agreed required outcomes = preserved outcomes + planned changes + unresolved required gaps`

This is an accounting of requirements, not a numerical claim of software completion.
Every required item has an explicit place. An unrelated feature cannot compensate for a
missing critical capability, and a deferred required item is still a gap.

## Capability and journey register

Each row carries: ID; user/outcome; source requirement; scope; required-for-release status;
applicability and rationale; current evidence state; evidence references; proposed treatment;
related requirement IDs; work-package IDs; acceptance-case IDs; owner; unresolved decision.

Evidence state is one of VERIFIED, PARTIAL, STRUCTURAL_ONLY, MISSING, UNKNOWN or CONFLICTING.
VERIFIED must name the observed version, environment and precise claim. Proposed treatment is
one of PRESERVE, REPAIR, EXTEND, INTEGRATE, CREATE, INVESTIGATE, DEFER or EXCLUDE_PROPOSED.
Only a recorded authorised decision can accept an exclusion or alter the completion boundary.

## Applicability scan

Assess each area, but do not invent irrelevant product requirements merely to fill the table.
Mark not applicable with a specific reason and the change that would make it applicable.

| Area | Questions that expose unfinished products |
|---|---|
| Users and onboarding | Who starts, signs in, gains access, is invited, recovers access and exits? |
| Core journeys | Does each main user goal have a beginning, connected middle and observable finish? |
| Roles and handoffs | Can work move between administrator, technician, customer and manager where required? |
| UI and interaction | Are required views, responsive layouts, validation, empty/loading/error states and accessibility specified? |
| Data lifecycle | What is created, saved, resumed, changed, imported, exported, retained and removed? |
| Identity and security | Which permissions, tenant boundaries, secrets and audit obligations apply? |
| Integrations | Are both sides of each interface specified, including authentication and failure behaviour? |
| Commercial rules | Where applicable, are pricing, billing, entitlements and account transitions coherent? |
| Outputs | Can users obtain required reports, notifications, records or other promised deliverables? |
| Failure and recovery | What happens after timeouts, duplicates, offline work, partial failure and process restart? |
| Performance and capacity | What workloads and supported environments matter, and how are budgets justified? |
| Deployment and migration | Can the intended version be introduced without losing data or breaking compatibility? |
| Operations and support | Who observes failures, repairs them, restores data and supports the released capability? |
| Validation and release | How will actual user outcomes be verified in the intended environment? |

## Journey specification

For each required journey, write actor and permissions, trigger, preconditions, relevant data,
normal steps, handoffs, alternative paths, error paths, persisted result and visible outcome.
Specify the UI/API/data chain and the observation that will prove the chain works. Include
an assertion after reopening, reconnecting or refreshing when persistence is part of the claim.

A page can exist while its save action fails. An API can exist without a usable interface.
A notification can be queued without reaching its recipient. These are different claims.

## Mandatory coverage rules

- No required outcome without a requirement or an explicitly unresolved decision.
- No work package without a justified requirement, risk-reduction purpose or approved investigation.
- No required interface without producer and consumer obligations.
- No acceptance check without an observable expected result and a failure condition.
- No deferred required outcome hidden outside the completion summary.
- No project-wide readiness claim from change-scoped evidence.
- No late-stage replacement of the agreed completion definition with an easier target.

## Writing a safe incremental plan

Use vertical increments: each increment connects an observable user action to its persisted
outcome and verification. Foundational work is valid, but label it foundation, not a delivered
user journey. Include the integration work linking increments and the final project-level
reconciliation. Near-term packages can be exact; distant packages may be conditional, with
explicit entry evidence and refinement checkpoints. This avoids both fake foresight and an
endless series of individually successful but disconnected components.

## Coverage report

Report counts separately: required items accounted for, implemented evidence verified,
partial items, unknown items, planned changes, deferred required gaps and proposed exclusions.
A 100% accounting rate can coexist with zero implemented work. Never merge these quantities
into a single reassuring percentage.
