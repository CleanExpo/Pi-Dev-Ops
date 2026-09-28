# Writing contract: the actual deliverable

## Write the packet, not instructions to write it

Use the project's established planning records. The responsibilities below can be sections
or linked existing documents; they do not mandate a new file for every row. Preserve accepted
versions and record proposed revisions. The packet must remain reconstructable from exact
content revisions, not mutable links alone.

Where there is no established planning location, present the proposed location and write to
the task's authorised output area. Do not create a new database, tracker or governance tree.

## Required responsibilities

| Responsibility | Required content |
|---|---|
| Intent | Existing five-section human contract; identity, revision and acceptance evidence |
| Current state | Source-bound baseline, incomplete work, reuse assessment and unknowns |
| Completion coverage | Whole-product boundary, change boundary, capability/journey register and gaps |
| Product specification | Behaviour, user journeys, interfaces, scope, exclusions and preservation rules |
| Engineering requirements | Existing engineering.md contract covering all ten engineering categories |
| Implementation plan | Dependency-ordered work packages, milestones, integration steps and refinement checkpoints |
| Verification plan | Requirement-linked cases, environments, test data, expected results and failure controls |
| Release and operations plan | Authority, exact-candidate verification, rollout, recovery, monitoring and support |
| Decisions and evidence | Source ledger, assumptions, conflicts, decisions and review records |
| Handoff | Exact next step, prerequisites, authority needed, blockers and continuation cursor |

The Build Contract is the linked agreement across the specification, engineering requirements,
verification and delivery records. It does not require a competing build-contract database.
Use SPM's existing 19-section specification where applicable and link these responsibilities
into that structure. The ten engineering categories retain their existing schema and validator.

## Requirement record

Each requirement has an ID, originating need, applicability, priority, statement, rationale,
assumptions, linked user journey, dependencies, acceptance-case IDs and authority status.
Write one independently testable obligation per statement. Separate desired behaviour from
implementation choices. Do not invent performance targets; cite the approved value or record
an unresolved budget with the experiment or owner decision needed to establish it.

Classify origin as FOUNDER, EXISTING_CONTRACT, DISCOVERED_CONSTRAINT or PROPOSED_ENHANCEMENT.
A proposed enhancement is not silently converted into an approved obligation.

## Interface record

Name producer, consumer, version, authentication/permissions, request and response meaning,
validation, errors, timeouts, retry/deduplication, compatibility and observability. State which
facts are already verified and which are proposed. Do not invent request fields, route names
or SDK functions when current implementation or official documentation can resolve them.

## Work-package record

Record ID; outcome; related requirements; affected components; existing assets to reuse;
dependencies; input contract; proposed changes; non-goals; test cases; expected evidence;
reviewer capability; authority class; resource ceiling; failure/recovery path; completion test.
A package may be an investigation when a decision needs evidence. Its output is a decision
record, not a claim that the unknown implementation is complete.

For each implementation package, specify how another worker can begin without redesigning
the requirement. Avoid "implement properly", "wire everything", "finish later" and other
instructions that conceal missing decisions. Exact file targets are required only when
verified; otherwise record a bounded discovery task before implementation admission.

## Acceptance-case record

Record test ID; requirement IDs; actor; preconditions; fixture/data policy; procedure; expected
observable result; negative or counterexample case; target environment; evidence to capture;
review ownership. Distinguish planned procedure from actual execution evidence.

Each mandatory criterion must be falsifiable. A validator that checks headings alone cannot
prove the prose is adequate. A screenshot cannot alone establish persistence or permissions.
A test list is not a passed test run.

## Planning manifest

Record planning identity, scope, project, intent revision/hash, inspected repository revisions,
canonical artefact references, document content hashes, source/evidence references, policy
references, unresolved decisions, review state, planning status and proposed next action.
Hashes identify content; they are not signatures, approvals or proof of correctness.

## Change and freshness handling

If intent, scope, dependencies, policy, source revision or acceptance criteria change, assess
which planning claims and review results become stale. Retain history; re-review affected
portions. Do not silently overwrite an accepted plan or transplant an older approval.

## Writing quality bar

Use consistent terms and Australian English. Put the operator's outcome first. Keep the
operator brief short while retaining complete technical detail in linked records. Explicitly
record all critical unknowns; do not fill missing evidence with plausible prose. Write the
entire authorised planning packet during the task, and identify any incomplete responsibility
in the final status rather than suggesting that somebody else should create it later.
