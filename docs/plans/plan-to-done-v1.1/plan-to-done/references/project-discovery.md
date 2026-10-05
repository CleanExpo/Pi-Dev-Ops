# Project discovery: sufficient evidence before writing the plan

## Purpose

Establish the current project baseline without changing the product. Discovery stops when
there is enough evidence to specify the intended outcome and identify blocking unknowns.
It does not require reading an entire company estate for a narrow change.

## Evidence record

For each material claim record a stable evidence ID, source location, repository or artefact
revision, environment, observation time, retrieval method, freshness requirement and the
specific claim supported. Distinguish direct observation, source-code inspection, test result,
operator statement, inference, historical report and proposed behaviour.

A source-code path demonstrates implementation structure, not successful execution. An old
passing report supports its recorded version, not the currently inspected candidate.
Read-only runtime evidence may be consumed if access is already permitted; do not run a
mutating walkthrough, test purchase, deployment or state-changing API request during planning.

## Discovery questions

| Area | Establish | Record when unavailable |
|---|---|---|
| Identity | Canonical repository, project registry entry, plan location, governing documents | Unresolved identity; no guessed repository |
| Version | Inspected commit, branch, uncommitted work, relevant open/closed PRs | Local or remote state not inspected |
| Production | Deployed artefact, environment and relationship to inspected code | Production state unknown |
| Product | Required users, roles, journeys, outcomes and completion definition | Owner decision or missing project contract |
| Architecture | Existing modules, interfaces, schemas, integration owners and shared capabilities | Unverified dependency or undocumented interface |
| Behaviour | Existing test definitions and authentic result records | Test available but not run, or evidence unavailable |
| Operations | Deployment, configuration, monitoring, data recovery and support arrangements | Operational gap |
| Work in progress | Related tickets, unfinished branches, local work and previously rejected approaches | Host state not accessed; do not infer absence |
| Governance | Write boundaries, release gates, data-egress rules and applicable grants | Block the affected privileged action |

## Existing work classification

Classify relevant capabilities as evidenced working, partially implemented, structurally
present but unverified, missing after sufficient inspection, conflicting, or unknown.
Record proposed treatment separately: preserve, integrate, repair, extend, create, defer,
exclude pending approval, or investigate. Do not turn a proposed treatment into an observed fact.

Before proposing a new component, name the existing alternatives inspected and the reason
each is insufficient. Before proposing reuse, identify tests or checks needed to establish
that the reused capability actually satisfies the requirement.

## Questions and uncertainty

Technical questions answerable from permitted repository or connected records are research
work, not founder homework. Business choices and genuinely unavailable evidence are recorded
with owner, effect on the plan, resolution method and a decision checkpoint. Never ask the
operator to repeat an answer already present in a verified source.

Conflicting authoritative sources require an explicit conflict record. Do not pick the
most convenient sentence or assume the newest prose overrides a higher-authority contract.
Continue unaffected planning while the disputed transition remains blocked.

## Exit criteria

The project, desired outcome, affected surfaces, significant dependencies and preservation
boundaries are identified. Every material unknown has a disposition. The baseline is sufficient
to write the plan, or the packet is explicitly a bounded draft with the missing evidence named.
