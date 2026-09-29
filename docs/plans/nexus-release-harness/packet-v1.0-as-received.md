<!-- Imported 29 Sept 2026 exactly as received in session, NOT edited. The supplied text was truncated:
     it ends mid-way through source I10 ("..."); Part 12 (portfolio-manifest.json), Part 13 (validation
     report) and external sources W01-W12 were not received. Request the modular ZIP to complete it.
     Adoption decisions and repo corrections live in adoption.md, not in this file. -->

*Revision:** NEXUS-RELEASE-HARNESS-20260929-v1.0
**Date:** 29 September 2026, Australia/Brisbane
**Status:** DRAFT_FOR_INDEPENDENT_REVIEW. This is a planning
deliverable, not a running harness or approved production release.

This single-file edition contains the intent, full SPM specification,
plan, engineering design, testing, AAA scoring, staged release and
RANA support design, Linear pathway, evidence limits and sources.
Filename references inside the parts refer to the modular edition
supplied in the ZIP. After adoption, use the existing canonical
project planning location and load only the relevant part per task.

## Contents

1. README.md
2. intent.md
3. spec.md
4. plan.md
5. engineering.md
6. testing.md
7. scoring.md
8. production-live.md
9. linear-pathway.md
10. review-and-handoff.md
11. sources.md
12. Portfolio manifest (JSON)
13. Actual local document-validation report (JSON)


---

# Part 1: README.md

# Nexus Portfolio: Critical Pathway to Done

**Design revision:** NEXUS-RELEASE-HARNESS-20260929-v1.0
**Date:** 29 September 2026, Australia/Brisbane
**Delivery:** Planning documents, not a running harness.
**Admission status:** DRAFT_FOR_INDEPENDENT_REVIEW. No build or
release authority granted.

## Start here

Read `intent.md`, then load only the document relevant to the current
planning step. This is one planning package, not ten new orchestration
systems.

| Document | Purpose |
|---|---|
| `intent.md` | Business outcome, boundaries, portfolio scope and
completion contract |
| `spec.md` | Nineteen-section SPM specification |
| `plan.md` | Dependency-ordered implementation and adoption plan |
| `engineering.md` | Build-harness contracts across the ten
engineering categories |
| `testing.md` | Risk-based test programme, scale strategy and
project-specific scenarios |
| `scoring.md` | Proposed AAA release-scope assurance and independent
audit protocol |
| `production-live.md` | Staged release, monitoring, RANA support,
incident and cleanup design |
| `linear-pathway.md` | Existing Linear mapping, deduplication,
dependencies and proposed work packages |
| `portfolio-manifest.json` | Machine-readable planning inventory; not
an executable configuration |
| `review-and-handoff.md` | Evidence limits, author challenge, open
admission gates and continuation point |
| `sources.md` | Inspected internal evidence and primary external
documentation |

## The operating principle

**Ship a smaller promise completely. Do not ship a larger promise partially.**

All ten requested project tracks are represented. Their production
readiness remains **NOT_ASSESSED_BY_THIS_RUN**. Tracker summaries are
leads to investigate, not runtime proof. No product tests, independent
model reviews, Linear writes, code changes or deployments were
performed in preparing this packet.

The packet is intended for the existing canonical planning location
after authorised adoption. This downloadable folder is a delivery
copy, not a replacement source of truth. SHA-256 checksums identify
these document bytes; they do not certify technical or production
readiness.


---

# Part 2: intent.md

```yaml
id: NEXUS-RELEASE-HARNESS-20260929
revision: "1.0"
date: "2026-09-29"
timezone: Australia/Brisbane
mode: PLAN_AND_WRITE
planning_status: DRAFT_FOR_INDEPENDENT_REVIEW
product_readiness: NOT_ASSESSED_BY_THIS_RUN
build_authorised: false
linear_writes_authorised_by_this_file: false
production_authorised: false
```

# Intent: Human-Out-of-the-Loop Assurance and Staged Production Delivery

## 1. Problem

The founder cannot reliably distinguish implemented work from working
products. Bugs, broken integrations, missing functionality and
incomplete customer journeys are being discovered after work has been
described as handed over or complete.

The portfolio needs an evidence-backed answer to five questions: what
works, what does not, what remains unknown, what can be released
honestly now, and what dependencies prevent that release.

A complete roadmap is not a prerequisite for entering the market.
Fulfilling every promise included in the current release is.

## 2. Intended outcome

Design an extension of the existing Unite-Group Nexus delivery system
that discovers the current estate, defines small commercially useful
releases, produces a dependency-based Critical Pathway to Done in
Linear, and autonomously executes authorised testing and repair
through the existing SPM, Board and release controls.

RANA remains the accountable Senior Software Engineer for ongoing
engineering support. Resident monitoring and authorised agent workers
assist RANA; neither a document nor an AI persona establishes human
availability or permission to change production.

The intended operating loop is:

**Discover → verify promises → define release → map dependencies →
authorise bounded work → test → repair → independently audit →
authorise release → deploy → verify customer outcome → support →
improve.**

This request delivers the design. It does not activate that loop.

## 3. Projects in scope

| Track | Requested project | Scope boundary |
|---|---|---|
| DR | Disaster Recovery | Public acquisition, enquiry/claim intake
and accountable service handoff |
| NRPG | Disaster Recovery / NRPG | Contractor onboarding,
eligibility, membership and network workflows |
| HALL | Disaster Recovery / Trade Hall | Source-site navigation,
cross-site handoff and the Trade Hall experience |
| RA | RestoreAssist | Restoration business onboarding, claims,
field/admin handoff and commercial paperwork |
| CARSI | CARSI | Approved learning content, enrolment, progression,
assessment and credentials |
| SYN | Synthex | Content/campaign workflows and only those external
publishing capabilities proven ready |
| ATO | ATO-APP | Defined internal financial/evidence workflows first;
public scope requires explicit approval |
| CCW | CCW-ERP | Existing CCW CRM/ERP boundary, reconciliation and
approved operational workflows |
| UG | Unite-Group | Shared organisation, business data, access and
portfolio services |
| MC | Unite-Group / Pi-Dev-Ops / Mission Control | Governance,
orchestration, evidence, fleet and founder visibility |

`linear-pathway.md` records the observed boards and aliases. A project
name is not proof of a separate repository, deployment or tenancy
boundary. Resolve these independently before execution.

## 4. Non-negotiable business rule: customer promise integrity

Create a versioned Customer Promise Register from public acquisition
pages, advertisements, pricing, signup, onboarding, contracts and
actual product behaviour. For each promise, record the audience,
release, evidence, operational owner and supported fallback.

An enabled or advertised capability must have a working end-to-end
journey, support coverage and current evidence. A missing feature must
be completed, removed from that release with approved customer-facing
changes, or presented accurately as an optional future capability. Do
not silently narrow a promise already made to existing customers.

Classify future work separately from defects in something currently
sold. A future feature does not block an unrelated safe release.
Broken authentication, data isolation, core delivery, financial
integrity or a promised connector does.

## 5. Human out of the routine loop, not outside accountability

Once a bounded mission is authorised, agents must perform retrievable
discovery, test preparation, permitted execution, log inspection,
diagnosis, repair, regression testing and evidence recording without
returning ordinary engineering tasks to Phill.

Do not confuse autonomy with unlimited execution. The existing signed
mandate, action policy, repository restrictions, provider entitlements
and resource ceilings remain authoritative. Pause only the affected
lane at a genuine boundary, preserve its continuation record, and
continue independent safe work.

The inspected `nexus-mission-authority/3` policy permits scoped build
continuation after approval but protects production promotion,
rollback, credentials, destructive actions, scope changes and
authority changes. Safe-release merges require an existing mandate and
the Board release controller. This intent does not widen those
permissions. [I01]

A production incident does not create permission to bypass the policy.
Unattended rollback would require a separately approved policy change
where the current policy reserves rollback to the founder.

## 6. Reuse before creation

Reuse the existing SPM specification process, engineering-requirements
gate, signed intent binding, `may(action)` policy check, delivery
lifecycle, independent auditor, release controller, Linear
integration, durable evidence store and fleet controls wherever
verified.

Do not introduce a competing orchestrator, board, ticket database,
status model or credential broker. Repair an existing component when
that is the smallest safe route. Proposed skill additions must have an
explicit reuse/repair/extend/new decision.

The current SPM contract requires a real engineering gate and a
separate approval before implementation. A written packet is not build
admission. [I03]

## 7. Required design deliverables

The sibling documents form one traceable contract: intent →
requirements → work packages → tests → evidence → release stage →
customer outcome. Every material gap must have a disposition: verify,
repair, dependency, approved later release, or explicit owner
decision.

Linear must eventually show the next release, exact blocking
dependency chain, ready work, unknowns, owners, acceptance evidence
and support readiness for each project. Synchronisation must be
idempotent and must reuse existing tickets instead of generating a
second backlog.

## 8. Model and test roles

Preferred engineering lane: **Claude Opus 5.5 through an eligible
Claude Max workflow**. Preferred independent OpenAI lane: **the
requested GPT-5.6 family through an eligible ChatGPT Pro/Codex
workflow**. Resolve exact model identifiers, availability, permitted
automation and billing paths at admission. Do not silently substitute
models or assume a ChatGPT model-picker label is an executable Codex
model ID. [W01–W05]

**TypeSafe/Jev is optional advisory infrastructure**, useful for
bounded classification and routing. It is not the test runner, source
of truth, numerical calculator, security boundary or release approver.
Its typed answers remain probabilistic. No live Jev call or paid
activation is authorised here. [I04, W06]

Run high-volume deterministic, property-based, state-machine and
contract tests in the appropriate isolated environment. Use frontier
models for test design, difficult diagnosis, adversarial challenge and
independent review, not one paid inference call per generated test
case.

## 9. Release and quality expectations

Progress through internal verification, a controlled pilot, a limited
market release and broader availability. Expand scope only after the
relevant release gate is satisfied. Maintain separate commercial,
technical, operational and authority states.

AAA is a proposed **internal release-scope assurance grade**, not a
claim of zero defects, complete roadmap delivery, external
certification or WCAG AAA conformance. Mandatory gates cannot be
averaged away. The existing SPM 100/100 planning admission rule
remains separate and unchanged. [I03]

Never claim that hundreds of thousands of executions constitute
exhaustive testing. Report distinct scenarios, generated inputs,
assertions, retries, coverage, detected faults and residual risk
separately.

## 10. Definition of programme success

The implemented system must demonstrate:

1. All ten tracks have an evidence-backed inventory, a promise
register, a first release contract and a deduplicated dependency plan
in Linear.
2. A smallest useful pilot completes the existing Nexus lifecycle
without Phill acting as the routine tester. Five consecutive genuine
delivery cycles and one recovered injected worker failure must be
evidenced, preserving the existing acceptance expectation. Each cycle
must reach its explicitly authorised acceptance state. A
non-production delivery may earn that narrower outcome, but cannot be
labelled production COMPLETE; five production deployments are not
required before the first launch. [I06]
3. Failed, blocked, skipped, stale and unknown evidence cannot produce
a green required gate or a false COMPLETE state.
4. A release reaches production only with the required authority and
is verified against actual customer outcomes afterwards.
5. RANA receives actionable monitoring, reproducible defects,
engineering context and an agreed support rota before live exposure
grows.
6. Changes preserve customer data, active work, evidence and rollback
capability; cleanup is scoped, authorised and verified.

Completion applies to an identified release. It must never imply that
the entire evolving portfolio is finished.

## 11. Delivery ownership and next stage

The current deliverable is this planning package. Its independent
SPM/engineering review, actual runtime baselines, model-lane
entitlement checks and admission receipts remain outstanding and are
recorded in `review-and-handoff.md`.

After the required planning acceptance and scoped authority are
recorded, the first execution package is **CP-00: reconcile governance
and runtime identity**, followed by the independent discovery packages
in `plan.md`. The file itself must never be treated as the approval
receipt.


---

# Part 3: spec.md

# SPM Specification: Portfolio Assurance to Production

**Revision:** NEXUS-RELEASE-HARNESS-20260929-v1.0
**Status:** DRAFT_FOR_INDEPENDENT_REVIEW. Canonical engineering gate: NOT_RUN.
**Sources:** Internal references I01–I10 and external references
W01–W12 in `sources.md`.

## 1. Task

Extend the established Nexus harness to discover actual readiness
across the ten tracks, construct staged-release critical paths,
execute authorised test/repair missions, and support independently
verified live releases.

## 2. Project context

Governance resides in Unite-Group; Pi-Dev-Ops is an existing
orchestration surface; the shared skills library contains the SPM
contract. Linear already contains relevant projects and
release-related work. Reuse these rather than building another control
plane. Repository presence does not establish operational health.
[I01–I03, I07]

A read of native Linear release pipelines returned no visible
pipelines. Use existing projects and milestones as the lowest-change
planning route unless the approved design establishes a reason to
introduce native release pipelines. This is an observed connector
result, not proof about unavailable workspace features.

## 3. Problem

Local checks, task labels and narrow acceptance criteria can miss the
actual customer journey. The existing Definition of Complete
distinguishes structural, build, behavioural, integration/security,
visual, review, release and outcome evidence. Enforce those
distinctions end to end. [I02]

## 4. Desired outcome

One founder view answers: “What can be released next, what still
blocks it, who owns the blocker, and what evidence will remove it?”
RANA has a separate operational queue for incidents, repairs and
release candidates. Existing clients remain protected while later
capabilities are developed.

## 5. Scope

Included: all ten inventories; customer-promise mapping; dependency
planning; test-harness adapters; evidence scoring; bounded repair;
independent audits; staged release; production monitoring; incident
handling; cleanup and continuity.

Excluded: wholesale rewrites, a new orchestrator, autonomous policy
changes, unsolicited customer communications, new paid inference, real
tax lodgements or bank movements, production load testing, automatic
branch/data deletion, or a guarantee of exhaustive verification.

## 6. Existing capability and reuse decision

| Capability | Inspected basis | Design disposition |
|---|---|---|
| Action authorisation | `mission-authority.json`, pinned revision |
Reuse through its canonical evaluator; never duplicate policy logic |
| Delivery completion | UNI-2517 | Reuse its lifecycle and prove
runtime enforcement |
| SPM planning | `skills/spm/SKILL.md`, pinned revision | Reuse the
nineteen-section and engineering-gate requirements |
| Routine fleet execution | Existing Pi-Dev-Ops agent boundary
document | Reconcile against newer central policy; do not adopt
permissive old rules blindly |
| Jev decision layer | Prior proposed Jev intent | Keep disabled;
evaluate only after separate activation authority |
| Linear portfolio mapping | Current projects and selected issues |
Reuse canonical records and deduplicate |
| Existing tests/monitors | Not comprehensively inspected | Inventory
before selecting additional libraries or services |

The old Pi-Dev-Ops document advertises a local SPM path whose fetch
returned 404. The shared-library SPM was retrieved successfully.
Resolve the installation path before invoking a skill; do not invent a
command implementation or treat the skill as absent estate-wide. [I03,
I07]

## 7. Specialist board

Use the established Nexus SPM and Board identities, membership, quorum
and signed decision records. Do not create new voting members in this
document.

Required review lenses: product/customer promises;
architecture/integration; independent QA; security/privacy;
operations/reliability; UX/accessibility; and relevant
industry/financial subject expertise. RANA provides engineering
ownership. An AI review using a specialist prompt is not a human
specialist's sign-off.


### Existing principal-engineer bench

The retrieved `engineering-requirements` skill defines seventeen
available specialist seats, not a requirement to summon all seventeen.
Its four core seats are `boris`, `eng-failure`, `eng-observability`
and `eng-test`; additional seats depend on the change. Preserve those
existing selection rules rather than inventing another Board. [I10]

Review the programme architecture and each bounded CP work package
separately. Under that skill, more than ten earned seats requires
decomposition, not a larger review prompt. Each admitted review must
run cold in genuinely separate contexts. The migration-drift check is
an execution-phase preflight under an approved data-access boundary:
drift or an indeterminate result seats `eng-release`; it never implies
permission to read secrets or mutate a database. No such check was run
while writing this packet.

The bench, not this author, produces the canonical category
provenance, exact `spec_sha256`, reviewer/session identity and actual
verdict. An author-written `engineering.md` is the design input to
that process, not its signed output. No reviewer identity, independent
finding or passing gate receipt has been fabricated.

## 8. Judge challenge

| Failure in a naive design | Required correction |
|---|---|
| “Run a million tests” becomes a quota rather than useful evidence |
Risk-based scenarios, invariants, fault seeding, coverage and stop
rules |
| Models approve their own work | Independent sessions, immutable
candidate, separate findings and deterministic gates |
| All projects wait for a giant harness rebuild | Small pilot using
existing components; independent release tracks |
| A high average hides a broken login or connector | Mandatory
blockers outside the score |
| “Autonomous” quietly grants production rights | Existing policy
checked immediately before every side effect |
| “Later release” excuses a promise already sold | Preserve existing
obligations and obtain explicit scope/customer-treatment decisions |
| Alerts and tickets become more bloat | Fingerprint deduplication,
one owner, evidence summaries and retention |
| Fixing customer bugs drains planned delivery forever | Incident
priority, resource reservation and visible release-path recalculation
|

Author challenge is not an independent Board review. No numerical
self-awarded approval is supplied.

## 9. Proposed solution

Add or repair thin adapters around the existing control plane:
portfolio discovery, promise/coverage registry, release-contract
projection, test result normalisation, critical-path planning,
independent audit receipts and operational monitors.

The data flow is **existing source → versioned evidence →
deterministic evaluation → Linear/Mission Control projection**. LLMs
may propose hypotheses and changes; they may not rewrite the evidence
or set final readiness directly.

## 10. User experience

Founder view: one row per project, with separate fields for “live
now”, “next release”, “customer promise”, “critical blocker”, “ready
task”, “assurance”, “unknowns”, “support owner” and “decision
required”. Show evidence age and direct proof references. Avoid a
single misleading portfolio percentage.

RANA view: severity, customer impact, affected release, reproduction,
trace, likely owner, rollback options, current mandate and next safe
action. Duplicate failures update an existing incident rather than
flood the board.

For customers, disabled capabilities must not appear as working
purchase promises. Loading, empty, denied, offline and failed states
are real acceptance cases. Keyboard navigation, small screens and
supported assistive-technology journeys belong in release acceptance.

## 11. Technical requirements

| ID | Requirement | Verification contract |
|---|---|---|
| R01 | Resolve all project/repository/environment identities | T01:
ambiguous alias cannot target a deployment |
| R02 | Reconcile advertised promises with executable journeys | T02:
advertised stub blocks affected release |
| R03 | Derive readiness from exact-version evidence | T03: changed
SHA/config invalidates affected receipts |
| R04 | Continue permitted work without redundant founder prompts |
T04: missing ordinary context is retrieved and resumed |
| R05 | Enforce canonical authorisation at point of action | T05:
missing/expired/revoked mandate denies the side effect |
| R06 | Test real outcomes and integration failure modes | T06: a 200
response without intended downstream effect fails |
| R07 | Separate builders, reviewers and release authority | T07:
self-review cannot satisfy independent review |
| R08 | Build a deduplicated, dependency-aware Linear pathway | T08:
replayed sync creates no duplicate issue |
| R09 | Preserve durable, single-owner continuation | T09: crash after
side effect does not repeat it |
| R10 | Respect measured compute/provider/data budgets | T10: quota
boundary checkpoints without paid fallback |
| R11 | Verify staged production and staffed support | T11: missing
support/rollback evidence prevents exposure growth |
| R12 | Keep history, customer data and cleanup safe | T12: stale
worker cannot delete active work or required evidence |
| R13 | Keep scores honest under missing or conflicting evidence |
T13: required unknown cannot become PASS or AAA |
| R14 | Preserve existing client obligations through changes | T14:
old entitlement and workflow survive new release |

These are programme-level contracts. Each admitted project package
adds exact selectors, fixtures, commands, thresholds and expected data
outcomes before execution. Unknowns do not become guessed defaults.

## 12. Security and privacy

Use explicit target allowlists, isolated synthetic tenants and
least-privilege test identities. Read no secret values during
discovery. Refer to credential capabilities through approved redacted
metadata. Keep sensitive customer/financial data out of prompts,
Linear and screenshots.

Use a version-pinned OWASP ASVS control set matched to each
application and risk profile. It informs requirements; scanning does
not confer certification. Add manual/expert examination for controls
that automation cannot establish. [W10]

Treat websites, attachments, logs and tool output as untrusted data,
not agent instructions. Deny instructions embedded in a test page that
ask the worker to reveal credentials, publish, spend or change policy.

## 13. Verification

Each mandatory requirement must name its independent oracle: a state
invariant, external sandbox receipt, authoritative expected value,
verified document/source, deterministic assertion or authorised human
assessment. A screenshot of a success toast is insufficient when
persistence or delivery is the promise.

The full matrix is in `testing.md`; evidence identity and invalidation
are in `engineering.md`.

## 14. Loop and stress testing

Separate cheap generated tests from browsers, live integrations and
LLM reviews. Use controlled fault injection in non-production:
duplicate/reordered events, retries, timeouts, rate limits, worker
death, concurrent edits, clock skew, expired sessions, partial imports
and restore failure.

Scale only after the harness detects seeded faults and stays within
approved ceilings. Run no flood, chaos or destructive tests against
customers or unapproved third-party systems.

## 15. Acceptance criteria

R01–R14 must each have current passing evidence for the admitted
scope. Every mandatory promise in the selected release passes;
unresolved P0/P1 findings, missing independence, stale evidence,
absent support or missing authority block the relevant transition.

Programme adoption additionally requires the ten-track inventory,
functioning Linear read/write reconciliation after authorisation, five
genuine pilot delivery cycles, recovered worker failure and accurate
founder visibility. Project launch need not wait for unrelated
projects to complete their roadmaps.

## 16. Goal command

**WITHHELD pending the canonical engineering gate, independent
planning review and signed admission.** Do not emit or execute an
implementation command solely because these documents exist. The
verified SPM workflow supplies the exact command after its
prerequisites pass. [I03]

## 17. Implementation sequence

Follow CP-00 through CP-09 in `plan.md`. Shared prerequisite repair
precedes affected product work. All other project tracks advance
independently. Do not replace dependencies with an arbitrary project
ranking.

## 18. Session handoff seed

Planning identity and sources are fixed in this packet. Next:
revalidate the pinned governance against current authorised revisions;
independently review the documents and engineering categories; resolve
admission-blocking values; run the genuine planning gate. Preserve
existing work and perform no product mutation during that review.

## 19. Final recommendation

Adopt a narrowly scoped pilot and evidence-first staged releases,
subject to the existing approval process. Do not activate
portfolio-wide autonomy, paid Jev access or production promotion from
this draft. The strongest initial result is one genuine customer-value
delivery with reproducible evidence, not a large agent installation.


---

# Part 4: plan.md

# Plan: Dependency-Ordered Adoption

**Status:** Proposed work packages. Not created in Linear by this
drafting run.
**Rule:** This is a partial-order delivery plan, not a claim that
current durations or launch dates are known.

## 1. Shared pathway

| Package | Deliverable | Depends on | Exit evidence |
|---|---|---|---|
| CP-00 | Reconciled authority, canonical skills and environment
identity | Accepted planning/review scope | Current policy IDs;
conflicting rules resolved; no invented permissions |
| CP-01 | Ten-track inventory and reusable-capability map | CP-00 |
Repositories, owners, live/preview targets, current work and evidence
gaps |
| CP-02 | Customer Promise Registers and first-release contracts |
Relevant CP-01 track | Every discovered promise accounted for; first
scope commercially coherent |
| CP-03 | Test-environment, data and provider-lane admission | CP-00
and relevant CP-01 | Isolation, target ownership, permitted
entitlements, quota and egress proofs |
| CP-04 | Evidence adapter, anti-false-completion controls and harness
self-tests | CP-00, CP-03 | Missing/stale/forged/failed receipts
rejected; seeded defects detected |
| CP-05 | Deduplicated Linear dependency projection | CP-01, CP-02;
separate write grant | Existing issues reused; relations round-trip
correctly; read-after-write proof |
| CP-06 | One golden-path test/repair/audit delivery pilot | Relevant
CP-02–CP-05; build grant | Isolated candidate, genuine checks,
independent review, no false finish |
| CP-07 | Stage release and RANA operational handover | CP-06; support
and release gates | Exact candidate; approved exposure; live outcome
proof; support accepted |
| CP-08 | Expand adapters and controlled portfolio delivery | CP-06;
each track's admission | Other tracks use the same contracts; no
separate orchestrators |
| CP-09 | Continuous monitoring, regression and scoped cleanup |
CP-07/CP-08 by track | Actionable signals, safe recovery, retained
evidence, reconciled state |

CP-01 starts as shallow breadth across all ten tracks. Deep assessment
and pilot delivery proceed as soon as a track's prerequisites are
satisfied. Do not hold a safe release for an unrelated product's
inventory problem.

## 2. Per-project dependency shape

For each track P, propose only these coherent work packages, reusing
existing equivalents:

`P-DISCOVER → P-PROMISE → P-VERIFY → P-REPAIR → P-AUDIT → P-RELEASE → P-OBSERVE`

`P-VERIFY` also depends on CP-03 and CP-04. `P-REPAIR` means the set
of confirmed blockers for that release, not every historical backlog
item. `P-RELEASE` depends on support readiness and the relevant
approval receipt. A branch can reach RELEASE_READY while a protected
production action remains separately gated.

Shared identity, billing or cross-product handoffs create additional
edges only after their actual dependency is verified. Do not invent
coupling because products share a brand.

## 3. Pilot selection

SPM selects the smallest valuable slice using observed customer harm,
existing promises, dependency unlocks, business value and verification
effort. Existing live security/data-integrity incidents take
precedence over growth.

RestoreAssist's first-business journey is a candidate, not a
predetermined winner. Trade Hall navigation is a useful small
verification case but must not be mistaken for validating the complete
Trade Hall product. Preserve current ownership and in-flight PRs.

## 4. Calculate a real critical path

After owners provide evidence-backed duration estimates and the actual
dependency graph is known, compute earliest start/finish and latest
start/finish over the acyclic graph. Zero-slack tasks form the
dependency critical path for the chosen release.

Then account for finite worker capacity, RANA's availability, provider
quotas, external lead times and approval windows. Report the
resource-constrained release forecast separately from the
unconstrained graph calculation. An unknown duration is unknown, not
zero. Detect cycles and unresolved external dependencies before
presenting dates.

Recalculate when scope, dependencies, estimates, incidents or resource
availability change. Keep unrelated ready work moving. Report date
ranges with assumptions rather than an invented launch commitment.

## 5. Controlled fleet expansion

Start with one reconciled worker lane and a genuine end-to-end
delivery using existing infrastructure. The Mac Mini is the intended
coordination host, subject to verified uptime, backup and current
topology; do not migrate a working hosted service merely to match that
preference.

Add the mobile MacBook and then the Windows PC only after checkpoint,
reconnect, lease fencing, toolchain and permission behaviour are
proven. A sleeping laptop is unavailable capacity, not a failed
product. Never copy account tokens between machines to manufacture a
shared inference pool.

## 6. Adoption milestones

**M0: Truth established.** All ten tracks have evidence states and a
next release contract.
**M1: Harness trustworthy.** Deliberate false-green cases and crash
recovery fail safely.
**M2: Pilot proven.** Five genuine missions to their explicitly
authorised acceptance state, one recovered injected failure and a
usable founder evidence view. These need not be five production
deployments. Non-production acceptance never earns production
COMPLETE.
**M3: First scoped release supported.** Customer promise, promotion
and live support gates pass.
**M4: Portfolio expansion.** Tracks progress independently and
existing customers remain supported.

These programme milestones are separate from the customer release
stages in `production-live.md`. A milestone marked Done does not
promote any product.


## 7. Requirement-to-work trace

| Requirement | Owning work packages | Acceptance test |
|---|---|---|
| R01 | CP-00, CP-01 | T01 |
| R02 | CP-02 | T02 |
| R03 | CP-04 | T03 |
| R04 | CP-06 | T04 |
| R05 | CP-00, CP-03, CP-04 | T05 |
| R06 | CP-03, CP-06 | T06 |
| R07 | CP-04, CP-06, CP-07 | T07 |
| R08 | CP-05 | T08 |
| R09 | CP-04, CP-06 | T09 |
| R10 | CP-03 | T10 |
| R11 | CP-07 | T11 |
| R12 | CP-09 | T12 |
| R13 | CP-04 | T13 |
| R14 | CP-02, CP-06, CP-07, CP-09 | T14 |

CP-08 repeats these same applicable contracts for each additional
project; it does not introduce a weaker portfolio expansion gate. Each
product-specific promise receives its own child requirement and
evidence link during admitted discovery.


---

# Part 5: engineering.md

# Engineering: Build-Harness Contracts

**Status:** Proposed engineering resolution, authored in this drafting run.
**Independent senior-engineer review:** NOT_RUN.
**Canonical `engineering_gate.py`:** NOT_RUN. These headings do not
constitute a passing gate.

The design extends existing records and adapters. It does not mandate
a new database, queue, scheduler or schema migration. Implementation
must first identify current persistence and safe extension seams.

**Provenance boundary:** this is the author-written engineering
design, not a completed independent bench review. The canonical bench
must supply its actual frontmatter, category ownership, frozen-spec
hash and verdict before the existing engineering gate can admit
implementation. [I10]

## 1. Data model

Model the following logical records in existing canonical stores where possible:

| Record | Required fields |
|---|---|
| ProjectIdentity | Stable track ID; aliases; verified
repository/environment references; owners; dependency links; discovery
timestamp; evidence status |
| Promise | Stable ID; exact source and revision; audience;
existing/new customer obligation; release; supported outcome; journey;
operational owner; disposition |
| ReleaseContract | Project/release ID; in/out scope; promise IDs;
must-pass controls; deployment strategy; acceptance/SLO thresholds;
supported cohort; support/rollback requirements |
| WorkPackage | Stable key; requirement IDs; Linear issue reference;
dependencies; scope; owner; estimate range; risk; mandate reference;
acceptance tests |
| TestCase | Scenario ID; requirement/promise IDs; target; fixture;
preconditions; oracle; side-effect class; seed; resource ceiling;
cleanup contract |
| EvidenceReceipt | Run/test IDs; result; source and artifact
identity; environment/config/schema digests; timestamp;
expiry/invalidation conditions; logs/traces; worker; integrity
metadata |
| ReviewReceipt | Candidate and contract hashes; reviewer
identity/provider/model/session; author independence; findings;
verdict; evidence references; review time |
| AuthorityReceipt | Existing signed mandate reference; exact scope;
action; allowed target; validity; policy revision; revocation state |
| Incident | Impact/severity; affected release/customer cohort;
reproduction; dedup key; owner; containment; follow-up work; closure
evidence |

Minimum evidence results: `PASS`, `FAIL`, `NOT_RUN`, `BLOCKED`,
`STALE`, `NOT_APPLICABLE`. Preserve native lifecycle states
separately. NOT_APPLICABLE requires an approved rationale; it cannot
conceal a current promise.

Example receipt shape, deliberately unexecuted:

```json
{
  "schema": "nexus-evidence-proposal/1",
  "project_id": "RA",
  "release_id": "RA-R1-CANDIDATE",
  "requirement_id": "R06",
  "test_id": "RA-HANDOFF-NO-ADDON",
  "result": "NOT_RUN",
  "candidate_sha": null,
  "artifact_digest": null,
  "contract_hash": null,
  "environment_id": null,
  "config_digest": null,
  "schema_version": null,
  "seed": null,
  "expected_outcome": "Admin can save the claim and use the supported
handoff without a dead end",
  "observed_outcome": null,
  "evidence_refs": [],
  "executed_at": null
}
```

Nulls prevent admission where the field is required. They are not
permission to guess a target or report a pass.

## 2. Invariants

Customer-visible promise → release contract → requirement → test →
receipt → outcome must be traversable in both directions. Orphan tests
and orphan promises are reported.

No required skipped/blocked/unknown/stale result may satisfy a gate.
No builder writes its own independent approval. No new commit, rebased
merge result, rebuilt artifact or material config/schema change
inherits release approval without the required revalidation.

A release is identified by the full deployed artifact/configuration
tuple, not a branch name or SHA alone. Reuse immutable build artifacts
where supported. Verify the actual merge result and deployment bytes;
reviewed branch evidence alone cannot certify a different merge
candidate.

A positive HTTP response is not proof of persistence, delivery,
entitlement, reconciliation or a business outcome. A tracker state is
a projection, not a release receipt.

## 3. Failure modes

| Failure | Required behaviour |
|---|---|
| Missing dependency, uncertain model output or unread context | Read
permitted evidence; classify unknown; perform bounded diagnosis;
continue independent work |
| Tool/hook failure | Repair only within existing authority; protected
hook/policy changes remain gated |
| Provider quota or entitlement unavailable | Checkpoint; mark lane
capacity/entitlement blocked; run eligible deterministic work; no paid
fallback |
| Linear unavailable or write timeout | Durable outbox; idempotency
key; readback before retry; no false sync-success claim |
| Worker crash after external side effect | Reconcile provider receipt
and idempotency key before retrying |
| Repeat repair failure | Preserve counterexample; stop that mutation
loop at the admitted retry ceiling; route to RANA/specialist review |
| Bad/stale/forged review or evidence | Reject candidate transition;
preserve evidence of rejection |
| Customer-impacting incident | Trigger approved response; suspend
affected rollout; do not create new rollback authority |
| Evidence storage fails | Fail the affected verification/release
gate; do not run unrecorded side effects |

A blocked lane is not a reason to park the whole portfolio.
Conversely, “keep going” never justifies bypassing a protected
boundary.

## 4. Interface contracts

Use typed, versioned adapters for discover, execute-test,
normalise-result, record-evidence, sync-Linear, request-review and
request-release. Every side-effecting adapter receives project,
environment, candidate, expected state, action, mandate reference,
policy revision and idempotency key.

Validate input/output schemas deterministically. Missing fields,
unknown enum values, duplicate identifiers or stale expected state
fail closed. Use compare-and-set/version checks for mutable records.
Authorisation is checked again immediately before the side effect, not
only when a task enters the queue.

**Jev decision contract:** a bounded advisory request includes a
redacted state, finite eligible choices, question/rubric version and
evidence references. Application outputs are `PROPOSE(candidate_id)`
or `ABSTAIN`; these are our adapter states, not claimed native Jev API
fields. Validate the provider's actual typed result and calibration
metadata against current official documentation. Never accept
arbitrary shell commands, URLs or permissions as a model-generated
action. [W06]

Jev may prioritise candidate tests or suggest failure categories. It
may not suppress hard controls, decide whether a secret is safe to
disclose, calculate financial truth, accept an unknown test as passed
or set release authority. Benchmark its decisions against held-out,
independently labelled examples before authorised activation. A
deterministic route remains available when Jev is disabled.

## 5. Concurrency and ownership

One active writer owns a work package/worktree. Use expiring leases
and monotonically increasing fencing tokens; reject writes from
workers whose leases have expired, including workers that reconnect
after sleep.

Across the fleet, use explicit capability labels and admission caps
for browser, CPU, memory, provider and integration work. Distinct test
namespaces isolate tenants and fixtures. External event retries must
be idempotent. A distributed system may deliver events more than once;
design reconciliation around that fact rather than claim exactly-once
delivery.

Reviews operate on frozen candidates. Once an author changes the
candidate, invalidate the affected reviews, recompute impact, and
rerun required global controls. Shared-component changes trigger only
the verified dependent tracks, plus platform-wide mandatory checks.

## 6. Migration

First migration is informational: map existing IDs, statuses,
artifacts and owners without changing their semantics. Use existing
evidence storage before considering new tables. A migration proposal
must include before/after schema, compatibility, backfill,
reconciliation, rollback and authority.

Do not run migrations against any database merely because it is called
staging; the inspected central policy treats database migrations as
protected. Provisioning test data likewise requires an admitted
fixture mechanism. [I01]

Read-only shadow comparison precedes CCW transactional adoption.
Preserve legacy systems and existing customer entitlements until an
approved migration plan proves safe cutover and recovery. Never remove
old obligations to improve a release score.

## 7. Rollback and recovery

Every release contract specifies an exercised recovery path, including
application artifact, configuration, feature flags, background jobs
and data compatibility. A code rollback may be insufficient after a
data migration; require the appropriate restore or forward-repair
procedure.

Store protected backups outside the test-run blast radius and prove
restore in an isolated permitted environment. Record business-approved
recovery time and recovery point objectives before production
admission. No invented values stand in for those decisions.

Preparation and testing of a rollback plan do not authorise its
production execution. Under the inspected central policy, production
rollback remains protected. Any future unattended rollback design
requires a separate policy decision and test proof. [I01]

## 8. Observability and evidence integrity

Capture stdout/stderr, process exit, test counts, browser
console/network errors, server traces, queue behaviour, relevant data
assertions and deployment outcomes. Logs must be streamed and
inspected during execution. Redact credentials and personal data
before persistence or model ingestion.

Monitor customer outcomes, not just uptime: intake acknowledged, lead
owned, entitlement granted, report created, lesson resumed, invoice
reconciled and publication confirmed where promised. Include a
monitor-of-monitors heartbeat and evidence of alert delivery.

Evidence must be append-only or equivalently tamper-evident in the
approved store. Hashes alone establish identity, not truth; trusted
runner provenance, restricted writer identities and authoritative
source receipts are also required. Keep review receipts separate from
builder-writable artifacts.

Show freshness by evidence class. Invalidate affected receipts on
candidate, schema, config, connector permission, external contract or
release-scope change. Discovery snapshots are never permanent
live-health certificates.

## 9. Budget and admission

Before execution record approved limits for wall time, attempts,
context/token usage, provider concurrency, CPU/memory, disk/artifact
retention, browser workers, external requests and permitted
expenditure. Apply the stricter of programme and repository limits.
Missing values block the relevant execution lane, not permitted
planning or unrelated deterministic tasks.

Reserve capacity for review, regression and incident handling before
assigning builds. Do not consume the full subscription allowance
generating changes that cannot be independently checked. Store source
references and concise deltas rather than replaying full transcripts
to every model.

Claude/OpenAI subscriptions are not an unlimited shared API pool.
Verify the permitted native workflow and actual account/model
entitlement. Current OpenAI authentication guidance distinguishes
subscription access from usage-based access and directs programmatic
workflows toward appropriate authentication; do not assume Pro alone
approves every unattended scheduler design. Current Anthropic guidance
similarly restricts credential intermediation. When the requested lane
is unsupported, record the specific gap without enabling a metered
route. [W01–W05]

Jev is separately evaluated and disabled by default. Pricing, provider
approval, data handling and budget require explicit admission before
even a shadow API call.

## 10. Test oracle

The oracle is defined before the repair where feasible and reviewed
independently. For deterministic business logic, derive expected
values from approved rules/reference fixtures, not the production
function under test. Cross-check units, rounding, boundaries and dates
with independent implementations or authoritative reference cases.

Use provider sandbox receipts for connector effects and database
assertions for persistence. Browser assertions must check usable
outcomes, not incidental CSS or success text. For visual/semantic
judgement, combine deterministic checks, structured review and
authorised human/expert validation where the claim requires it.

Do not modify acceptance tests, hide a failing fixture, reduce
coverage, lower a threshold or quarantine a critical test to obtain
green. A legitimate correction to an incorrect oracle requires an
independent explanation and versioned contract change.

The harness must first reject deliberately faulty implementations. A
test suite that cannot detect the seeded broken connector or false
completion state is not admissible for release assurance.


---

# Part 6: testing.md

# Testing: Unknowns to Evidence

**Execution status:** NOT_RUN. Every test described here is a design
requirement, not an achieved result.

## 1. Discover before generating tests

Reconcile five independent inventories: customer promises;
screens/routes and API contracts; data/jobs/events; connectors and
deployment configuration; and open/closed tasks with existing tests
and receipts.

Identify stubs, mocked success, disconnected buttons, unreachable
routes, undocumented flags, manual fulfilment, old migrations and
checks that never execute. Use permitted metadata, not secret values.
Compare stated behaviour with the actual deployed version when bounded
runtime observation is authorised.

Every discovered item receives evidence status, release relevance,
risk, owner, proposed test and disposition. Coverage is measured
against a versioned inventory; discovering a new surface changes the
denominator visibly. “100% inventoried” means the recorded inventory
is accounted for, not that all possible unknowns have been eliminated.

## 2. Test layers and where they run

| Layer | Objective | Permitted target after admission |
|---|---|---|
| Static/build | Types, imports, lint, dependency/config consistency,
compile | Isolated checkout |
| Unit/property/state-machine | Invariants over many inputs and action
sequences | Local or isolated test runtime |
| Component/API | Validation, persistence, authorisation, error
contracts | Disposable test service/data |
| Connector contract | Real request/response semantics, retries and
receipt reconciliation | Provider sandbox or approved test tenant |
| Browser E2E | Whole user journey with console/network/data outcome |
Isolated preview/staging, then separately approved live smoke |
| Accessibility/visual | Keyboard, focus, responsive layout, errors
and representative assistive use | Approved browser/device matrix |
| Security | Tenant/object access, injection defences, file handling,
sessions, supply chain | Owned, allowlisted non-production targets |
| Load/soak/recovery | Capacity, queues, resource leaks, restore and
degraded behaviour | Controlled non-production load environment |
| AI/agent adversarial | Prompt injection, stale state, false
evidence, authority misuse | Isolated evaluation harness |
| Production synthetic | Narrow continuous proof of critical outcomes
| Dedicated synthetic identity and approved side-effect budget |

Reuse existing runners where they fit. Playwright supports isolated
browser tests and traces; fast-check supplies generated input and
failure minimisation; k6 supports threshold-based performance checks.
These are candidate tools, not a mandate to install duplicates.
[W07–W09]

## 3. Scale without a million model calls

Use deterministic generators to exercise high-value invariants. As a
planning illustration, 50 genuinely different properties × 10,000
generated inputs produces 500,000 property executions. This is
arithmetic, not an estimate of attainable throughput or independent
customer scenarios.

Increase sample counts only after checking time, cost, isolation and
defect-detection value. Bias inputs toward boundaries, malformed data,
concurrency and known failure clusters. Preserve seeds and shrink
failures into small reproducible counterexamples. Use pairwise
combinations for broad interaction coverage and targeted higher-order
combinations for dangerous interactions.

Report separately: distinct scenario definitions, generated cases
executed, unique states/transitions, assertions, retries, skipped
cases, seeded faults detected, real defects and covered requirements.
Repeating one happy path does not create broad coverage. Passing
samples alone do not justify a statistical reliability claim unless
the sampling assumptions and method actually support it.

## 4. Common complete customer journey

For each relevant product, verify **acquisition claim → signup →
identity/consent → plan/payment or invitation → entitlement → first
promised outcome → save/resume → support → cancellation/export/data
handling**.

Use new and existing accounts, ordinary users and legitimate
administrators, at least two isolated tenants, supported devices,
permitted locales/time zones, denied permissions and expired sessions.
Verify the negative route as thoroughly as the successful route.

A real payment, customer notification, social publication, dispatch or
tax submission is an external side effect. Sandbox tests are the
default. Live checks require explicit scope and approved test
identities; avoid real customer impact and unwanted messages.

## 5. Project-specific release probes

These are candidate acceptance areas to refine against discovered
promises, not assertions that every feature is currently in scope or
broken.

| Track | First useful slice to validate | Critical adversarial and
regression cases |
|---|---|---|
| DR | Request help, retain the enquiry, acknowledge it and assign an
accountable follow-up | Anti-abuse failure; missing fields; duplicate
submission; no available coverage; delayed delivery; lost routing;
real recipient acknowledgement; accurate emergency-service claims |
| NRPG | Contractor application, saved progress, verified eligibility
and honest status | Unapproved contractor cannot appear approved;
expired credentials; missing coverage; duplicate lead allocation;
missed acceptance; membership/payment failure where included |
| HALL | Both source sites enter the correct hall; navigation and
promised enquiry/participation work | Actual desktop/mobile click;
redirects; target unavailable; deep-link refresh; back navigation;
external handoff; unwanted referrer/token exposure; broken exhibitor
link; no shared-signin assumption |
| RA | Business onboarding, create/save a claim, admin/field handoff
and the paperwork promised in the pilot | Save/Next with incomplete
initial information; autosave/reload; no-field-addon route; authorised
master entitlements versus normal users; custom pricing versus NRPG/DR
constraints; rounding; report/quote/invoice consistency;
offline/conflicting edits; connector failures |
| CARSI | Approved course discovery, enrolment, access, resume,
assessment and earned credential | Payment without access; duplicate
enrolment; progress lost across devices; disabled/unapproved course;
assessment bypass; certificate without completion; incorrect
CEC/credential rules; accessibility; unsupported factual content |
| SYN | A complete content brief, approved draft, preview and export
or verified publishing | Revoked/expired OAuth; incorrect destination
account; duplicate schedules; approval bypass; publishing disabled but
still sends; API rate limit; partial publish; content marked published
without provider receipt |
| ATO | Explicitly bounded internal import/evidence/reconciliation
workflow | Duplicate imports; missing pages/rows; wrong financial
year; decimal/rounding errors; conflicting source records; unjustified
classification; unauthorised export; cross-user disclosure; lodgement
attempted without authority |
| CCW | Shadow reconciliation and approved operational slice at the
existing Phase gates | SKU/warehouse mismatch; duplicates/deletions;
snapshot date drift; unknown stock treated as available; partial sync;
stale customer pricing; duplicate orders; read-only mode writes;
approved exception populations mixed into totals |
| UG | Correct authorised business context, trustworthy shared data
and working operational handoffs | Cross-business data access;
stale/missing schema; false dashboard state; revoked role; session
expiry; conflicting updates; connector inaccessible while shown
connected |
| MC | One mission enters, is owned, tested, reviewed and honestly
reported | Lease expiry; mobile worker disconnect; duplicate dispatch;
agent approves itself; stale SHA; failed hook; forged Board receipt;
premature Done; missing quota; kill switch; restart reconciliation;
failed Linear readback |

RestoreAssist's listed cases are proposed exploratory probes, not
verified defects or attributed prior instructions. Retrieve the
current accepted role, handoff, pricing and add-on rules before
defining expected outcomes. CARSI content and credentials need
authoritative source/version review, not agreement between LLMs.
Financial and CCW expected values must come from approved
deterministic source records.

## 6. Connector proof ladder

Record a connector's evidence at distinct levels: configured metadata;
implementation present; mocked test; contract/sandbox test; approved
live smoke; monitored outcome. Do not collapse these into “connected”.

Test permission scopes, token expiry/revocation through safe fixtures,
timeout, malformed response, version drift, pagination,
duplicate/reordered webhook, invalid signature, replay, rate limiting,
queue recovery and partial failure. Assert both the external receipt
and intended local state. Reconcile missed events without duplicate
customer actions.

Mocks remain useful for many failure paths, but cannot alone establish
that an advertised real integration works. Do not intentionally break
or flood third-party production systems.

## 7. Harness acceptance tests

| ID | Injected condition | Required result |
|---|---|---|
| T01 | Alias resolves to two different deployments | No guessed
target; exact identity blocks affected action |
| T02 | Signup promises a connector whose implementation is a stub |
Affected release blocked or scope-change decision required |
| T03 | Review is for a different SHA or material config | Review
rejected as stale; required revalidation queued |
| T04 | Worker lacks information available in permitted records |
Worker retrieves it without a routine founder question |
| T05 | Expired/revoked mandate, changed policy or protected target |
Side effect denied at execution time; independent work continues |
| T06 | API returns success while downstream effect is missing |
Journey FAIL, not PASS |
| T07 | Builder posts an approval under its own review identity |
Independent-review gate FAIL |
| T08 | Same Linear event/write is replayed after a timeout | One
canonical issue/update after readback reconciliation |
| T09 | Worker dies immediately after a committed external action |
New owner reconciles, never repeats the effect blindly |
| T10 | Provider quota is exhausted | Checkpoint with visible wait
state; no account rotation or paid fallback |
| T11 | Deployment succeeds but support/rollback proof is absent | No
exposure expansion or COMPLETE state |
| T12 | Cleanup is aimed at active work, unique commits or required
evidence | Deletion denied and active state preserved |
| T13 | Required test is skipped, quarantined or unknown | No green
required gate; no AAA |
| T14 | New release removes an existing customer entitlement |
Regression detected and affected release blocked |

Additional fault seeds: kill the monitor; corrupt a receipt; inject a
malicious instruction into page text; race two workers; hide an
exception in a paginated API; make a customer payment callback arrive
twice; produce zero tests with exit code zero; return stale cache
content after deployment. All must yield the intended failure or
protective state.

## 8. Exit rules

Mandatory critical journeys and controls must pass on the final
candidate. A retry pass does not erase an unexplained flake. Critical
flaky tests remain blockers until fixed or independently replaced with
equally strong evidence. Test collection counts and command exits must
both be checked.

Performance acceptance requires an approved workload, sample/window,
thresholds and environment profile. Load volume is not a substitute
for representative behaviour. Security findings require verified
remediation or an explicitly permitted disposition; severe findings
cannot be averaged out.

Every discovered failure becomes a reproducible case and one
fingerprinted issue where authorised. Preserve raw evidence and
minimise the counterexample. Do not flood Linear with one ticket per
generated input.


---

# Part 7: scoring.md

# Scoring: AAA Release-Scope Assurance

**Status:** Proposed internal rubric. No project or document has been
awarded AAA by this run.

## 1. Keep four questions separate

1. **Planning admission:** the current SPM process requires its real
100/100 mandatory-criterion result, engineering gate and approval.
[I03]
2. **Release-scope assurance:** does the selected release satisfy its
frozen requirements?
3. **Release authority:** does the signed policy permit this exact action now?
4. **Whole-product completion:** what portion of the approved
longer-term roadmap is actually delivered?

A high answer to one does not answer the others. The rubric below
cannot lower an existing gate or grant permission.

## 2. Evidence score

Freeze control groups and weights before execution. Score groups, not
raw test-case counts.

| Dimension | Proposed weight |
|---|---:|
| Customer promises and end-to-end outcomes | 25 |
| Integrations and data integrity | 20 |
| Security, access and privacy | 20 |
| Reliability, recovery and operational support | 15 |
| Usability and accessibility requirements | 10 |
| Evidence provenance, reproducibility and release discipline | 10 |
| **Total** | **100** |

Within a dimension, the proportion is **accepted control groups /
applicable required control groups**. Accepted means current passing
evidence of the required class. FAIL, NOT_RUN, BLOCKED and STALE
contribute zero. A group has no partial pass if a mandatory child
check is missing.

A NOT_APPLICABLE exclusion requires a pre-approved reason and
applicability review. Show excluded controls and both denominators.
Reclassifying a failed promise as N/A after a run is a scope change,
not a scoring adjustment.

The weighted score is diagnostic. It is not a probability that the
software is correct or a model confidence average.

## 3. AAA rule

**AAA-RELEASE-READY** requires all of the following:

- Evidence score is 100/100 for the frozen applicable release
controls; every mandatory customer promise passes.
- No unresolved P0/P1 finding, material data/security issue, required
unknown, stale receipt or unexplained critical flake remains.
- Two genuinely separate non-author audit passes cover the same final
candidate, drawing on the requested Claude and OpenAI lanes with
actual provider/model/session receipts.
- Deterministic build, integration, security, recovery and release
checks pass. No required suite is skipped or replaced with model
opinion.
- Support ownership, monitored outcomes, approved rollout limits and a
tested recovery plan are recorded.

**AAA-LIVE-VERIFIED** adds actual authorised promotion, exact
deployed-artifact readback and the defined post-release
outcome/observation evidence.

These are assurance labels attached to a release ID and scope. They do
not replace the canonical delivery lifecycle, certify compliance, mean
zero defects or imply that future features exist. Approved minor
issues outside mandatory release obligations remain visible with
owners and review dates. There is no global portfolio AAA average that
can conceal a failing product.

## 4. Multi-model audit protocol

Freeze the contract, candidate, environment tuple, change set and
evidence index. The builder may provide reproduction facts but cannot
control the independent auditor's tests or verdict.

An OpenAI reviewer and a separate Claude reviewer examine the raw
evidence and candidate independently, initially without the builder's
persuasive summary or the other reviewer's score. The Claude review
session must not be the author session. Record provider, exact model,
session, access scope, verdict and findings. Shared model families can
still have correlated blind spots; separate sessions do not establish
statistical independence.

Each reviewer challenges customer promises, interfaces, security/data
integrity, failure handling, test oracles and release/support
obligations. Review output is PASS, FAIL or ABSTAIN, with
evidence-backed findings. Missing access produces ABSTAIN, not assumed
agreement.

A substantive disagreement generates a reproducible test or a bounded
specialist decision. Do not vote away a blocker, average conflicting
findings, or rerun prompts until a favourable answer appears. If
either reviewer changes code, that person/session becomes an author
for the change and an independent replacement review is required.

Jev may help classify findings; it does not count as either
independent release reviewer and cannot overrule deterministic
evidence. RANA and the authorised Board retain their actual roles. A
reviewer receipt is not a founder signature.

## 5. Anti-gaming and calibration

Use held-out adversarial cases, seeded faults, independently chosen
fixtures and audits of test-oracle changes. Record false-green
escapes, reopened defects, reviewer disagreement and production
incidents by release.

Do not improve a score by hiding a feature only from tests, changing
the denominator without scope approval, deleting failures, collapsing
retries into successes, or using thousands of trivial checks to
outweigh one missing outcome.

After live operation, compare the assurance result with actual escapes
and update future test design through the approved process. Do not
rewrite historical scores or weaken thresholds automatically.


---

# Part 8: production-live.md

# Production Live Harness and RANA Support

**Status:** Design only. No monitor, worker, alert, deployment or
support rota activated.

## 1. Release stages

Stages describe the size of the customer commitment, not permission to
weaken mandatory quality or security controls.

| Stage | Exposure | Exit/advancement proof |
|---|---|---|
| R0: Reality baseline | No new exposure | Identity, promise
inventory, current live risks and next release scope recorded |
| R1: Internal verified slice | Isolated test/staging users | Full
selected journey; failure/recovery tests; trustworthy evidence;
independent candidate review |
| R2: Controlled pilot | Approved invited cohort with bounded usage |
Current promises fulfilled; onboarding/support accepted; live checks
and agreed observation window pass |
| R3: Limited market release | Public acquisition for the proven
offering | Honest pricing/signup; demonstrated fulfilment and support
capacity; deployment/recovery/monitoring gates pass |
| R4: Broader availability | Expanded acquisition/cohorts | Capacity
and reliability evidence at intended load; stable operations; no
unresolved release blockers |
| Next increment | Additional explicitly defined capability | A new
contract re-enters the same relevant gates without invalidating
existing clients' promises |

Projects already live keep their exposure classified separately from
assurance. Do not relabel a live product “not live” just because this
audit has not assessed it. Do not assume that being live means it
passed R3.

## 2. What must be frozen before a release

The release contract must identify the candidate and artifact;
configuration and schema; enabled feature flags; audience and
promises; unsupported/excluded features; acceptable workload and
service objectives; integration dependencies; support rota; monitor
thresholds; exposure steps; minimum samples and observation windows;
abort conditions; recovery procedure; and authority receipts.

These values are business- and risk-specific. Missing mandatory values
prevent the affected production admission. Agents may retrieve
evidence and draft options without requesting routine implementation
decisions from Phill.

Any proposed pilot/manual fulfilment is valid only when it is
operationally staffed, meets the actual promise and is disclosed where
relevant. A hidden manual backlog is not a working automated product.

## 3. Candidate to live

Follow the canonical earned lifecycle:

`IDEA → DISCOVERED → PLANNED → BUILD_AUTHORISED → EXECUTING →
LOCALLY_VERIFIED → PR_OPEN → REVIEWING → CI_GREEN → STAGING_VERIFIED →
RELEASE_READY → SHIP_AUTHORISED → PRODUCTION → POST_DEPLOY_VERIFIED →
COMPLETE`

Keep BLOCKED, FAILED_RECOVERABLE, FAILED_GATED, CANCELLED, UNKNOWN and
STALE explicit. Programme stages and assurance labels are additional
dimensions, not competing meanings of Done. [I02]

Use the existing Board controller for a permitted safe-release merge.
Independently verify the actual merge candidate and hosted
infrastructure semantics. On the inspected Unite-Group policy, a merge
and moving the production domain are distinct actions; do not
generalise that configuration to another repository. [I01]

For production, prefer the smallest practical exposure mechanism
already supported: internal release, named pilot tenants, feature
flags or controlled traffic cohorts. Canarying is useful when the
infrastructure and meaningful metrics support it; do not invent
percentage-based routing for a deployment that lacks it. [W11]

After promotion, read back the deployed artifact and configuration,
exercise the exact promised journey with an approved synthetic
identity, inspect relevant logs and verify downstream state. Cache
invalidation and CDN observations must be included where they affect
served content.

Deployment success alone is PRODUCTION evidence, not
POST_DEPLOY_VERIFIED. A quiet low-traffic window is not enough to
establish reliability without the contract's required observations.

## 4. RANA's operating model

RANA is the named human Senior Software Engineer, not an AI account
name. Confirm the actual Linear identity, accepted responsibility,
coverage hours, backup responder and notification channel before live
support admission. Do not promise 24/7 human coverage without an
accepted rota.

The resident software harness supplies:

- Continuous approved telemetry, bounded synthetic journeys and
monitor heartbeat checks.
- Deduplicated incidents containing impact, environment, candidate
version, reproduction, redacted trace, evidence and next safe action.
- Isolated repair candidates with regression tests and independent
reviews, ready for the existing approval route.

RANA owns engineering triage, difficult diagnosis, change
coordination, support handover and the technical release
recommendation within established authority. RANA does not
automatically receive founder-only production rights from this design.

Separate the production support lane from roadmap development. Reserve
an agreed share of real capacity for incidents and regressions; do not
invent RANA's available hours. Pause expansion of an affected release
when customer promises or service objectives are not being met.

## 5. Incident response

Use the existing severity policy if one exists; reconcile terminology
before admission. Proposed meaning: P0 is severe ongoing harm/security
or data compromise; P1 is a blocked core promised journey or
materially wrong customer outcome; lesser issues have lower urgency
but remain owned.

For each incident: detect → corroborate → classify → contain within
authority → reproduce safely → repair in isolation → independently
verify → obtain required release authority → release → confirm
recovery → add regression and root-cause record.

The agent must not “fix production in place” to save time. Destructive
fixes, credentials, migrations and rollback remain protected. Under
the inspected central policy, even production rollback needs founder
authority; a faster automatic incident-response lane would require a
separately approved policy revision, not wording hidden in this
intent. [I01]

Prepare authorised messages and evidence automatically, but send
external communications only through an existing communication
mandate. Report customer impact without leaking customer data into
tickets or model prompts.

## 6. Maintain promises as the product grows

Test upgrade/downgrade, grandfathered plans, roles, data compatibility
and old integrations when introducing a new feature. Version the
promise register and release notes. Retire features through an
approved migration/customer-treatment process, not silent removal to
reduce the test matrix.

Separate product-engineering inference from inference sold to
customers. Personal Max/Pro subscriptions must not become an
undocumented shared backend for customer-facing AI features. Product
inference, privacy, costs and provider terms require their own
approved architecture. [W01–W05]

## 7. End-to-end ownership and cleanup

Agents must monitor logs while work runs, resolve problems within
scope, rerun relevant checks, retain exact-version evidence, update
Linear after authorisation and verify the final outcome. Do not hand
Phill tasks a permitted agent can complete.

Before cleanup, enumerate the task-owned artifacts and apply the
canonical action policy. Delete only explicitly permitted disposable
material, with a preview and post-check. Branch deletion is a
protected destructive action in the inspected policy, even after
merge. Do not interpret “clean everything up” as blanket deletion
authority. [I01]

Never force-reset a shared repository, remove unique commits, wipe
uncommitted work, clear credential/session stores, flush shared
production caches indiscriminately or delete required logs and
rollback artifacts. Unrelated dirty worktrees belong to their owners
and are not failure evidence for the isolated task.

Use versioned retention rules: transient successful-run output can
expire under an approved TTL; failure evidence, release receipts,
active-incident material and required audit records retain their
prescribed lifetime. No policy means preserve evidence and report the
retention decision, not delete by guesswork.

Final handoff reports: exact release/version; promises verified; tests
actually run; unresolved issues; Linear records updated; production
state; support owner; cleanup completed or awaiting protected
approval; and the next bounded increment. A protected cleanup
remainder must be visible rather than silently represented as done.


---

# Part 9: linear-pathway.md

# Linear: Critical Pathway to Done

**Observed:** 29 September 2026, Australia/Brisbane.
**This drafting run:** read projects, selected issues and
release-pipeline metadata; created no issues, changed no statuses,
notified no owners.

## 1. Canonical mapping from current read results

The IDs below are connector-returned references. Resolve their current
native IDs before writes; do not assume the displayed `P-*` identifier
is a GraphQL UUID. [I08]

| Track | Existing Linear home | Observed reference | Handling |
|---|---|---|---|
| DR | Disaster Recovery Website | P-DR-14 | Use existing project and DR team |
| NRPG | DR-NRPG Contractor Go-Live; DR-NRPG Ops | P-DR-34; P-DR-15 |
Release and ongoing operations are related, not duplicates |
| HALL | Existing DR issue DR-953 and follow-up DR-952 | DR team |
Cross-site product track; confirm canonical project/target-repository
ownership before writing |
| RA | RestoreAssist | P-RA-13 | Canonical home; avoid resurrecting
archived Revenue/V2 boards |
| CARSI | CARSI | P-GP-11 | Existing G-Pilot team; brand name does not
determine team key |
| SYN | Synthex | P-UNI-6 | Existing Synthex/Unite-Group project;
resolve canonical team |
| ATO | ATO | P-UNI-3 | ATO-APP is the requested alias; verify
repository and internal/public scope |
| CCW | CCW CRM | P-UNI-5 | CCW-ERP is the requested alias; preserve
existing release/sign-off restrictions |
| UG | Unite-Group | P-UNI-2 | Shared platform, separate from its
Mission Control presentation |
| MC | Pi-Dev-Ops; Mission Control | P-RA-21; P-UNI-45 | One programme
with orchestration and cockpit components; avoid duplicate tickets |

The existing **Nexus Continuous Optimisation & Resilience** project
(P-UNI-39) is a candidate parent for the portfolio pathway. Its
milestones already cover diagnosis, stability, completion enforcement
and optimisation. Confirm scope fit rather than automatically create
another programme.

The visible native release-pipeline query returned an empty list.
Design the initial path using existing projects, issues, milestones
and dependency relations; introducing native pipelines is a later
deliberate adoption choice, not a prerequisite to discovering bugs.

## 2. Existing evidence leads to reconcile

These are tracker observations, not new runtime findings or
instructions to duplicate/reopen work automatically:

| Track | Observed lead | Required handling |
|---|---|---|
| HALL | DR-953 is Done, but its description explicitly records no
live Chrome click verification | Retain valid narrow-task evidence;
verify complete customer entry/hall journey separately [I05] |
| NRPG | Current project summary mentions DR-949 CAPTCHA and DR-950
`/claim` 404 | Fetch current issues, candidate and runtime proof
before defining blockers |
| CARSI | Summary points at signup/onboarding and enrolment work |
Reconcile existing tasks with the complete learner journey |
| RA | Summary records a bounded basic-flow pass, not a fresh
paid-path verification | Treat the exact proven scope separately from
billing or add-on readiness |
| SYN | Summary describes internal use and parked OAuth work | Do not
market live external publishing until that promise is actually proven
|
| ATO | Summary describes internal scope and legal-page 404 work |
Keep internal readiness distinct from a public tax-facing release |
| CCW | Existing project text preserves human merge and operational
sign-off requirements | Bind the actual current gates; do not use a
generic low-risk release rule |
| UG | Summary identifies migration and security concerns | Triage
current evidence before growth; do not assume summaries are fresh
proof |

For any retrieved issue with a partial description, fetch its full
record before using it as an acceptance contract. Current work and
assignees take precedence over a newly generated plan.

## 3. Proposed hierarchy

A portfolio coordination epic links CP-00…CP-09 from `plan.md`. Each
project receives a first-release epic only where no equivalent exists.
Reuse existing release milestones or propose R0–R4 mapping in
descriptions; do not change global team workflows automatically.

Inside each release epic, link only actionable work packages:
discovery, promise/acceptance mapping, missing evidence, confirmed
blockers, independent audit, release admission and post-release
support. Hundreds of thousands of test executions belong in the
evidence store, not as individual tickets.

Represent dependency edges using actual Linear relations. Put a shared
prerequisite in its owning project and link dependants to it. Never
clone the same shared-auth fix into ten projects.

## 4. Minimum work-package fields

Stable dedup key; project/release; customer promise; requirement;
expected outcome; exact target; risk; current evidence status;
dependencies; accountable owner; build/release authority references;
reproducible acceptance tests; evidence links; estimates and
assumptions; support/rollback implications; and next safe action.

Suggested stable key:
`nexus-release:<canonical-project>:<release>:<requirement-or-failure-fingerprint>`.
Do not put the current run timestamp in the identity; that defeats
deduplication.

Initial planning records stay in the current equivalent of
Draft/Backlog without autonomous-dispatch flags. Do not apply `Ready
for Pi-Dev` or an autonomous label until the actual admission
requirements and signed scope are satisfied.

## 5. Idempotent sync protocol

After a separate write grant:

1. Resolve team, project, release/milestone and owner identities;
inspect current open and relevant closed work, then build a change
preview.
2. Search by stable key and matching outcome. Prefer updating/linking
existing work; conflicting candidates require reconciliation, not
blind creation.
3. Apply bounded changes using existing connector semantics and
concurrency checks. Preserve human edits, scope and assignees.
4. Read back issues, descriptions, relations and state. A successful
tool response is not enough if the resulting dependency graph is
wrong.
5. Record a sync receipt and cursor. On timeout, reconcile actual
state before retrying. Never claim sync complete while changes remain
unknown.

The available connector may not offer arbitrary custom fields. Use
supported native fields and structured description blocks rather than
inventing an API contract.

## 6. Critical-path and status projection

Linear mirrors canonical execution evidence but does not become the
sole deployment record. Show “next release”, “blocking chain”, “ready
now”, “awaiting authority”, “unknown evidence”, “owner” and “forecast
assumptions”.

Do not compute readiness from issue count. One core unresolved
dependency can block a release with ninety-nine completed tickets.
Completed subtasks do not automatically close a parent release or the
whole product.

On candidate drift or newly confirmed defects, update the release's
assurance/status projection with history. Do not silently rewrite a
prior receipt or imply the original verification covered new code.


---

# Part 10: review-and-handoff.md

# Review and Handoff

## 1. Written

The requested intent, nineteen-section SPM spec, adoption plan,
engineering contracts, testing programme, AAA scoring design,
production support design and Linear mapping are written in this
packet. All ten requested tracks are represented.

## 2. What was actually inspected

Current connected Linear project metadata, the Definition of Complete
issue UNI-2517, the Trade Hall issue DR-953, visible native
release-pipeline metadata, a pinned Unite-Group authority policy,
Pi-Dev-Ops AGENTS.md, pinned shared-library SPM and
engineering-requirements skills, prior planning/Jev/fleet documents
and current primary technical documentation.

This is a sampled design baseline, not a source-code or production
audit of ten products. No new product-readiness percentage is
established.

## 3. Checks and claims

| Check | State |
|---|---|
| Planning documents authored | WRITTEN |
| Ten-track representation and internal cross-reference/manifest
validation | See `validation.json` for actual local results |
| Genuine separate Claude/OpenAI review | NOT_RUN |
| Canonical engineering-requirements skill and engineering gate | NOT_RUN |
| Full current-code/runtime discovery for each product | NOT_RUN |
| Product builds, tests, load/security tests and live browser journeys
| NOT_RUN |
| Subscription authentication or entitlement proof on the fleet | NOT_RUN |
| Linear mutations, task dispatch, code changes, merges or deployment
| NOT_PERFORMED |

An author self-check is not an independent audit. Planning validation
is not a passing product test.

## 4. Author challenge and corrections incorporated

The design avoids count-based confidence, self-approved code,
universal production autonomy, duplicate boards, unbounded paid
inference and treating a narrow completed task as a fully verified
product.

It also preserves current customers' promises when reducing future
scope, explicitly separates live state from assurance state, treats
provider authentication as an admission requirement, and recognises
that under the inspected policy production rollback and branch
deletion remain protected.

The first draft risk of requiring all ten products to finish before
any release is removed: the plan uses per-track prerequisites and a
small pilot. The risk of recreating the complete Nexus platform is
removed through reuse decisions and thin adapters.

## 5. Admission gaps and who resolves them

| Gap | Resolution owner/lane | Effect |
|---|---|---|
| Independent planning/engineering verdict and real engineering gate |
Existing SPM, engineering-requirements process and authorised
reviewers | No build-ready or approved-plan claim until completed |
| Actual repositories, release artifacts, environments and current
work for all tracks | Permitted discovery agents | Affected target
cannot be selected by guesswork |
| Current promise and supported-release contracts | SPM with existing
product owners; RANA for feasibility | Determines what must work
before exposure |
| Model/client/authentication/automation entitlement | Approved local
account checks and primary provider policy review | Unsupported
provider lane cannot be activated |
| Numeric execution ceilings and performance/observation thresholds |
Existing policy and accountable owners | Scale/load/rollout not
admitted with invented values |
| RANA identity, accepted coverage and backup responder | Existing
team/operations authority | No unsupported claim of staffed live
service |
| Financial/training/domain correctness acceptance | Accountable
domain expert with authoritative sources | AI agreement cannot replace
required expertise |
| Linear mutation and release mandates | Existing authority process |
Drafting alone does not authorise writes or promotion |

These are preflight tasks for the system and accountable owners, not a
list of routine engineering work being handed back to Phill.

## 6. Exact continuation point

Read `intent.md` and the evidence/source index. Resolve the current
canonical planning and engineering skills from the existing shared
library. Review this packet in planning-only mode, reconcile with
current policy, and obtain a genuinely independent assessment. Execute
only document-validation activities permitted by that planning mode.

Do not create tickets, run product tests, change credentials, install
workers or start the build until the relevant separate admission is
established. After admission, CP-00 is the first execution package.
The SPM process supplies the actual implementation command after its
engineering gate passes.

## 7. Preserve on continuation

Keep this planning identity, source references, limitations, ten-track
mapping and current work ownership. Do not start another duplicate
discovery project, invent new Board members or apply an AAA label from
the document's presence.


---

# Part 11: sources.md

# Source Register

**Checked:** 29 September 2026, Australia/Brisbane. Web and connector
observations can change. Revalidate at execution admission.

Internal tracker statements are attributed evidence leads. They are
not independent runtime verification. The source register also
identifies private Library documents by their actual returned
identities; it does not invent public URLs for them.

## Internal evidence

- **I01: Canonical action policy.** `CleanExpo/Unite-Group`, revision
`8eb9491b826b45fbd311b7fdfc9848ce8bd8c7a3`,
`scripts/nexus-runner/mission-authority.json`, schema
`nexus-mission-authority/3`. Retrieved via connected GitHub. Scope:
build continuation, safe-release requirements, protected
production/rollback/deletion/credentials and Board-controller merge
lane. [Pinned source](https://github.com/CleanExpo/Unite-Group/blob/8eb9491b826b45fbd311b7fdfc9848ce8bd8c7a3/scripts/nexus-runner/mission-authority.json).
- **I02: Definition of Complete.** Connected Linear issue UNI-2517,
full description fetched; record last updated 5 September 2026. Source
of existing earned lifecycle and evidence-class distinctions. A Done
issue is not proof every runtime consumer now enforces the contract.
[Issue](https://linear.app/unite-group/issue/UNI-2517/p0-definition-of-complete-and-pre-pr-verification-contract).
- **I03: Existing SPM skill.** `CleanExpo/skills-library`, revision
`64d5869dcea0d3b6ea6bf0187b83bcf966621225`, `skills/spm/SKILL.md`.
Source of planning-only scope, nineteen sections, mandatory-criterion
100/100 admission and separate engineering gate. [Pinned
source](https://github.com/CleanExpo/skills-library/blob/64d5869dcea0d3b6ea6bf0187b83bcf966621225/skills/spm/SKILL.md).
- **I04: Prior Jev design.** Library
`Pi-Dev-Ops_Mission_Control_JEV_Reflex_Layer_INTENT.md`, file
`file_00000000b29881fa962c981ed73028a8`, version 1, dated 26 September
2026. Source of advisory typed decisions, non-activation boundaries
and demo-reference context. This is a proposed design, not deployment
evidence.
- **I05: Trade Hall delivery record.** Full connected Linear issue
DR-953, last updated 28 September 2026 at 23:14:55Z (29 September in
Brisbane). Description dates the delivery 28 September and records
both redirect deployments plus an unverified real live Chrome click.
Treat those dates and narrow claims separately.
[Issue](https://linear.app/unite-group/issue/DR-953/trade-hall-live-on-disasterrecoverycomau-and-nrpgbusiness).
- **I06: Existing fleet intent.** Library `intent.md`, file
`file_00000000b69481fa9f1e79b6f948caf8`, version 1. Retrieved
acceptance passage requires five consecutive real deliveries,
recovered injected failure, independent evidence and no unapproved
metered inference. Not proof those conditions have been met.
- **I07: Pi-Dev-Ops agent boundaries.** Connected GitHub `AGENTS.md`
at main, retrieved during this run. It includes older
threshold/permission language, so reconcile it with the canonical
stricter applicable policy. Its documented
`.claude/skills/spm/SKILL.md` fetch returned 404; the shared-library
skill in I03 was found.
[Source](https://github.com/CleanExpo/Pi-Dev-Ops/blob/main/AGENTS.md).
- **I08: Connected Linear portfolio snapshot.**
`list_projects(limit=50, includeMilestones=true)` returned
`hasNextPage=false`. Relevant returned names/IDs are in
`linear-pathway.md` and `portfolio-manifest.json`.
`list_release_pipelines(includeStages=true, includeTeams=true)`
returned an empty list with no next page. This establishes only what
these read calls returned, not account-wide feature availability or
product health.
- **I09: Planning/writing correction.** Library
`SKILL(20260928-103900).md`, file
`file_00000000b5a881faac80822e1aeddd62`, version 1. The `plan-to-done`
skill separates planning documents from implementation, ticket
mutations, live Jev calls and production claims. Its retrieved
sections also distinguish self-checks from genuine independent review.

- **I10: Existing engineering bench.** `CleanExpo/skills-library`,
revision `64d5869dcea0d3b6ea6bf0187b83bcf966621225`,
`skills/engineering-requirements/SKILL.md`, fetched in full. Defines
seventeen available seats, four compulsory core seats, conditional
additional specialists, decomposition above ten earned seats, cold
independent review and the provenance-bound gate. [Pinned
source](
...
