<!-- Received 29 Sept 2026 as chat text from Phill. Stored as sent (table rows re-flowed into Markdown
     tables; wording unchanged). The package it refers to (spm/references/source-ledger.md,
     spm/references/acceptance-cases.json, the candidate skill) was NOT received; S1–S5 below are its
     citations, not files in this repo. Adoption decisions: ../nexus-release-harness/adoption.md O10–O17. -->

# /spm: one command, one mission, verified delivery

Design revision: 2.0, 29 September 2026, Australia/Brisbane.
State: Proposed design and candidate skill package. Not installed, activated or runtime-verified.
Owner-facing entry point: /spm in the existing Mission Control text area.
Supersedes: The proposal to make plan-to-done the owner's new entry point. Its planning-and-writing responsibility remains an internal stage.

## 1. The required experience

Phill states the outcome once. Mission Control owns the process, selects the appropriate skills and agents, researches, plans, writes, builds, tests, challenges, repairs, updates records, manages the authorised release and verifies the actual outcome. Phill sees where the mission is, what happens next, what needs his decision, and the evidence supporting completion.

The system must not hand responsibility back merely because a specification, model turn, task, session, pull request or deployment finished. Technical transitions belong to the harness. Genuine business and authority decisions remain with the authorised human.

One command does not require one giant prompt or one model. It requires a consistent command interface above the existing governed execution system.

## 2. What the inspection established

| Observation | Evidence | Consequence for this design |
|---|---|---|
| The inspected shared spm skill describes itself as specification-only and emits a separate /goal command. | S1 in spm/references/source-ledger.md | Change the public /spm responsibility to mission ownership. Keep specification writing inside it. |
| The v1 plan-to-done candidate explicitly delivers its planning packet and stops. | S2 | Retain this behaviour for the internal planning worker, not for the whole mission. |
| The inspected Unite-Group live-agent-operations.ts constructs shipFeed and recentShips from tasks labelled done. | S3 | Replace that inference with a view backed by release and outcome receipts. This source inspection is not a deployment audit. |
| The inspected Senior Harness v1 contract delegates authenticated mutation approval to a trusted adapter and does not admit mutation from request text alone. | S4 | Prove an existing compatible authority adapter or implement the missing binding under approval. Never bypass the gate. |
| Pi-Dev-Ops exposes an existing typed live-status contract. | S5 | Extend and reconcile existing surfaces rather than create a second dashboard or state store. |

These findings explain specific mismatches between the inspected contracts and the requested experience. They do not establish all causes of previous incomplete projects or the current readiness of any machine.

## 3. One interface, two outcomes selected by the request

/spm <outcome> is the single public entry. In a selected mission, ordinary follow-ups use the same text area and the same mission identity. The UI may insert /spm automatically; no second workflow must exist for plain text.

- A request to build, fix or finish starts a delivery mission, subject to existing authority.
- An explicit request to research, plan, write a specification or not build remains planning-only.
- A status question is a read, not an instruction to start, restart or duplicate work.
- A pause, cancellation, amendment or approval is applied to the identified mission with the appropriate authority check.

An empty /spm opens the selected or last relevant mission's current state. If multiple missions could be meant, show their names in the same interface rather than guessing or asking for technical identifiers. An unscoped high-consequence action must not pick a project automatically.

New submissions carry a client-generated request identifier. Retries of that submission are idempotent. A genuinely new mission gets a new identity even if its wording matches an earlier one. Do not derive mission identity from the prompt text alone.

The original request is preserved verbatim. Later instructions and accepted scope changes create revisions. An old frozen prompt must not cause a current pause, cancellation or correction to be ignored.

## 4. The owner-visible mission card

The default card contains only:

| Field | Meaning |
|---|---|
| Outcome | What this mission is meant to deliver and its scope. |
| Now | Earned phase plus what is actually happening. |
| Next | The next action the system will take and its trigger. |
| Waiting on | A dependency, capacity, evidence or permission, with the responsible owner. |
| Needs you | A specific decision or Nothing. Never a general instruction to manage the agents. |
| Proof / updated | Links to the evidence behind the claim and when the underlying observation was made. |

Detailed logs, branches, skills, agents, models and test output sit behind an expandable detail view. They are not the default reading burden.

Human-friendly phase labels are a presentation of the existing lifecycle: Understanding, Planning and writing, Building, Checking, Ready for release, Releasing, Shipped and verified. They are not another authoritative state machine. Planning-only missions finish with Planning delivered, never Product shipped.

Activity is separate from phase: working, queued, recovering, waiting for capacity, needs decision, paused, blocked, stale, cancelled. A blocked test does not move the earned phase backward or erase previous evidence. New candidate revisions may invalidate evidence and must show why.

Show verified acceptance outcomes out of the frozen applicable set, plus failed, pending and unknown counts. Do not show an invented completion percentage or use files, commits, elapsed time or tokens as product progress. Show scope changes explicitly rather than quietly shrinking the denominator.

Use source observation time, event sequence and separate connection status. Refreshing a page does not refresh old evidence. A disconnected client displays the last observation as stale; it must not fabricate current progress. A heartbeat proves liveness, not useful delivery.

Notifications are milestone- and exception-based in the authorised surface. Do not create email, Slack, SMS or other outbound notifications without an applicable grant. Dedupe notifications across reconnects and devices.

## 5. Internal process ownership

| Responsibility | Required work | Exit condition |
|---|---|---|
| Understand and discover | Resolve the project, original request, existing work, current evidence and constraints. | A scoped objective and supported baseline, with unknowns visible. |
| Plan and write | Write the actual intent/specification, engineering requirements, coverage map, acceptance procedures and ordered work packages. | Planning output passes applicable review and structural checks; acceptance is real, not inferred. |
| Admit and resource | Bind permissions, worker ownership, skill versions, provider routes, review capacity and budgets. | The next task is legal, ready and assigned; unresolved protected actions remain pending. |
| Build and integrate | Use bounded changes, correct interfaces, actual persistence, failure handling and integration ownership. | A reproducible candidate, not disconnected leaves or stubs. |
| Test and challenge | Run required checks and connected user journeys; obtain independent multi-model challenge and resolve material findings. | Evidence belongs to the candidate and satisfies the agreed criteria. |
| Publish and release | Commit, push, update the PR and tracker, obtain protected approvals, merge and deploy through the approved release path. | The target environment's actual artefact and release are identified. |
| Verify and close | Check the deployed user outcome, operational health, handover and relevant support requirements. | Canonical completion criteria and every required evidence class are satisfied. |

The coordinator owns all transitions. A leaf worker cannot set the parent mission complete. A plan writer returns to the coordinator, not to Phill with a command to copy. A builder cannot approve its own work. The final candidate must be reviewed after integration, not only its individual parts.

Reuse the existing Senior Harness, scheduler, model router, skill selector, engineering requirements, proof and release controls. /spm is their owner-facing entry and coordinator contract, not a new scheduler competing with them.

## 6. Principal-engineer delivery is the default

Use every relevant approved capability to meet the agreed outcome to the required engineering standard. Do not interpret this as enabling every feature, selecting the most expensive model or expanding the product without approval.

For each feature, cover its actual connected journey: entry, validation, permissions, persistence, downstream handoff, empty/error states, retry behaviour, observability and operational ownership. Applicable security, accessibility, performance, compatibility, data, migration, rollback and concurrency requirements must be decided explicitly.

The engineering review supplies requirements the founder should not have to remember. Derive thresholds from the project, current primary documentation and representative conditions. An invented performance target is a proposal, not an existing requirement.

For each material capability, record: relevant to this mission; available on the selected host; authorised; selected or not selected with rationale; exercised with evidence. Selection does not prove execution. A missing essential capability blocks only affected work; optional capability failure has a declared, non-deceptive fallback.

Defaults include test-first or an appropriate alternative with justification, relevant regression checks, browser/runtime walkthroughs where applicable, independent review, no critical placeholder implementation, operational documentation and post-release verification. Exceptions require rationale and the appropriate authority; agents cannot lower the quality bar to finish faster.

Existing root requirements remain visible through scope reconciliation. Related opportunities outside the accepted objective remain proposals, not hidden scope expansion or required work silently dropped.

## 7. Multi-model review and Jev

Resolve model/provider choices from the current approved capability registry. Do not hardcode a fashionable roster into the skill. Measure observed provider, exact model, reviewer identity, candidate and usage. Reserve review and recovery capacity before admitting expensive build work.

Use separate builder and reviewer executions. Material work requires the configured cross-model/provider independence policy. Different personas or windows of the same model are not provider diversity. Prevent the builder from editing protected review criteria or receipts. Resolve disagreements with evidence and a separate arbiter when required, not majority voting or a flattering average.

TypeSafe guidance supports the design and review of Jev integrations. Jev may rank an eligible skill shortlist or advise on narrow semantic decisions after evaluation. It never supplies permission, arithmetic, exact identity checks or completion proof. It must not remove mandatory tests.

No Jev or other paid route is activated by this document. Live or shadow provider calls need an authorised route, data policy and budget. An unavailable optional classifier falls back to the existing safe selection path; it does not strand the entire mission.

## 8. Permission without constant babysitting

The system prepares and carries out authorised steps. Phill does not need to remember their technical names. Where an applicable grant already covers an action, do not ask again simply because a worker or session changes.

An approval must bind the action, scope, project, revision/candidate as appropriate, environment, approving identity, limits and expiry. The same card offers the specific approval when required, including the risk and recommendation. A general go, skill description or model score cannot substitute for an ambiguous or expired release grant.

Preserve existing protected-action rules. This design does not grant standing merge, production, deletion, spend, credential, publication or security-policy permissions. The desired reduction in prompts must be implemented as scoped grants and validated policy, not bypass flags.

Commit, push, PR creation/updates, tracker updates and non-production deployment are automatic only where the specific active grant permits them. Merge and production release stay separately governed unless a valid policy explicitly grants that exact class of action. A missing authority adapter is an implementation gap, not a reason to turn enforcement off.

Grant changes and policy changes require the correct owner decision. Approval of this architecture does not authorise its deployment or every future mission.

## 9. Same mission from every device

Use the existing Mission Control web surface as a thin authenticated client. Phone, PC, MacBook and Mac Mini must talk to the same canonical mission service, not create local copies of the workflow. Terminal /spm must use that service too or clearly report offline/unavailable; it must not secretly run a second local process.

The Mac Mini is the preferred always-on controller host in the requested topology, subject to real readiness verification. PC and MacBook are additional admitted workers; the mobile phone is an operator surface. Preserve the actual current storage owner discovered during implementation. Do not migrate the database onto the Mini merely because it is the preferred controller.

The durable mission record and event history hold approved objective revision, plans, stage, node state, worker leases, candidates, attempts, evidence references, grants, capacity state and next action. Model context is disposable. The backend, not an open browser tab or an individual chat response, owns continuation.

One controller lease with fencing prevents split-brain dispatch. Worker leases, task ownership and action idempotency protect mutations. After an interrupted external write, read back the external state before retrying. Do not promise universal exactly-once execution for providers that do not support it. Ambiguous side effects enter reconciliation, while independent safe work may continue.

Disconnected clients are read-only snapshots for protected actions. Authentication expiry must be distinguished from a failed mission. A successful submission is acknowledged only after durable acceptance, not after a temporary UI message. Reconnecting reads canonical state and missed events.

If the Mac Mini is unavailable, the UI reports it. Automatic controller failover requires a separately proven single-writer design; otherwise keep the queue durable and restore the controller without claiming active work.

The shared skill release and API contracts are versioned. Each host proves its installed adapters, permissions, gate behaviour, browser/test capability and approved account routes. Installed and reachable are not verified. No forced parity of hardware or operating systems is required; parity means the same semantics and truthful capability declarations.

## 10. Continuation and failure handling

An admitted task advances automatically when its prerequisites pass. Review feedback creates bounded repair work without asking Phill to relay it. Quota exhaustion queues work against approved capacity without paid fallback. Technical uncertainty uses evidence gathering and bounded independent diagnosis.

A child failure blocks dependants, not all unrelated authorised work. Stop the whole mission when safety, data integrity, explicit cancellation or a shared dependency requires it. Repeated failures use method fingerprints and configured retry/circuit-breaker policies. Rewording the same failing command is not a new strategy.

Persist a checkpoint before context exhaustion or a planned handoff. If a worker dies, reconcile its worktree and external effects before reassigning ownership. Preserve local changes and active branches. Do not reset, delete or auto-resurrect abandoned work to make the queue look clean.

Every waiting state names what will resume it and who owns the next action. A normal session end is not a mission end. Cancellation propagates to workers and pending effects; an action already irreversible must be reported honestly.

## 11. Shipped means observed, not announced

For a production-delivery mission, Shipped and verified requires all applicable mandatory requirements and the canonical lifecycle's release and outcome gates. Bind evidence to the objective revision, source, integrated candidate, built artefact, configuration/migrations and actual environment.

The finish record includes outcome scope, exact release/version, live destination, independent review, required test results, observed end-to-end behaviour, material limitations, rollback/support ownership and timestamp. Do not replace an absent receipt with a similar-looking report.

A pull request is a candidate, not shipping. Passing CI is evidence for its checks, not a live outcome. Production deployment is not post-deployment verification. Missing, skipped, stale and failed evidence remain distinct.

Shipped is historical fact for an identified release. Current health is a separate observed field. A regression, revoked evidence or a later release can invalidate current readiness and create repair work without rewriting release history.

Planning-only work may be delivered as a document without pretending the software shipped. A feature-level mission cannot award product-wide completion. Mandatory unresolved work prevents the relevant completion claim; accepted nonblocking limitations must be visible and truly outside mandatory acceptance.

## 12. Integration work before this can be called working

1. Reconcile the existing intake, project registry, scheduler, status, approval and receipt owners. Record their real paths, versions and runtime evidence.
2. Prepare the versioned /spm migration and prevent planner-to-SPM recursion. Keep the old command pinned for in-flight missions until they can be safely migrated.
3. Bind the existing text area and CLI to one authenticated mission entry. Prove durable submission, deduplication and status lookup.
4. Connect planning outputs to execution admission without a human command handoff. Prove valid grants and explicit protected-action prompts.
5. Wire existing skills, workers, models, integration ownership and gates. Run the representative connected feature journey.
6. Replace label-based shipped views with receipt-backed projection and meaningful next-action ownership.
7. Prove restart, device change, offline behaviour, quota limits, duplicate dispatch prevention and cancellation.
8. Run an independently reviewed authorised pilot from one request to actual release and post-release outcome. Only then promote the proven path.

This sequence is an implementation plan, not a claim these changes have been made. Do not publish another dashboard in place of wiring the existing one. Use the real system with a controlled test mission, not synthetic data shown as production success.

## 13. The owner's acceptance test

Phill submits one request in Mission Control, sees the actual phase and next action, changes devices, and returns to the same mission. The system writes the plan, chooses and exercises relevant capabilities, builds, integrates, independently reviews, repairs, updates the authorised records, prompts only for genuine required decisions, releases under valid authority and shows proof of the real outcome.

No technical command copying, agent selection, test reminders or manual relay between phases is required. A restart and a transient worker/provider failure are deliberately included. No duplicate mission or external write may result. A planning-only request must stop at planning.

The evaluation scenarios are in spm/references/acceptance-cases.json. They are not passing results. Promotion needs actual baseline/with-skill trials, runtime fault tests and an independent reviewer.

## 14. What was delivered in this response

This package writes the revised architecture, a candidate /spm contract, its integration/review references, an internally adapted planning skill, and acceptance scenarios. Local package checks establish only file structure and selected written invariants. No live library, device, tracker, provider account, repository or deployment was changed.
