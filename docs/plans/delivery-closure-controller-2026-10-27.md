# Delivery Closure Controller: no accepted project left unfinished
Date: 27/10/2026 AEST | State: **local prototype tested; live connectors, scheduler and enforcement NOT activated**
Tracking: [RA-8099](https://linear.app/unite-group/issue/RA-8099) (new closure epic); reuse RA-7820 (missing Done), RA-7814 (deploy receipt), RA-7815 (false complete at merge), UNI-2654 (founder/Rana authority).

## What the founder means by "finished"
One accepted request = one durable mission ID + named delivery owner + exact repo/PR/revision + acceptance criteria + delivery environment + approval boundary. A PR is a transitional object, not a project completion. **Done** is only recorded once approved source code reaches its intended live target, the actual running revision is verified and the scoped acceptance test passes. Non-deployable work needs an approved signed delivery receipt instead.

The system can accept several projects concurrently, but every open commitment must have a next action, owner, deadline and follow-up lease. Existing accepted work gets priority over unlimited new tasks. Human-held approvals remain visible and stop publication, not the independent work of other projects.

## Why existing code did not solve this
- `app/server/linear_pulse.py` runs every 15 minutes but largely reads **active in-memory build sessions**. A PR blocked in review after its session ends can disappear from that pulse.
- `app/server/agents/build_stall_watchdog.py` stops stalled subprocesses, not stalled PR/release flows.
- `app/server/session_linear.py` logs build complete and leaves the Linear issue In Review; there is no reliable verified-live-to-Done path. See RA-7820.
- `app/server/gc.py` deletes old terminal workspaces; durable work obligations and review receipts must live **outside** ephemeral worktree/session stores.
- Prior Linear issues SYN-1035 and UNI-2150 were labelled Done for cleanup/completion features, but these labels do not prove the cross-repo Pi Dev Ops runtime path is enforced. Check actual caller before reuse.

## Scope-preserving architecture
- **Intake:** Pi Dev Ops admission records mission, sponsor, measurable goal, per-project finite scope and protected actions (existing authority object; no duplicate authority ledger).
- **Monitor:** read-only collector (next slice) polls **authorised** GitHub PR state, current CI/review data, scoped Linear status, Vercel/live deployment health/commit SHA, worker lease and active blocker. Record source timestamps and API failures; a failed API read is `UNKNOWN` not PASS.
- **Evaluator:** `app/server/delivery_closure.py` (this slice) classifies stages, finds aged work, refuses unsupported Done and emits stable alert fingerprints. Pure logic, no credentials or side effects.
- **Recovery:** existing Pi Dev Ops orchestration consumes findings, assigns owner and chooses bounded actions: retry reviewer at most twice (only authorised CLI subscription route), reassign reviewer if unavailable, flag failing CI for a builder, request human approval when necessary, reconcile a deploy. Never authorise itself to merge, spend, rewrite policy or deploy.
- **Ledger:** use existing persisted event/receipt schema and Linear links, extend narrowly as required for each stage transition; no second database or giant project-context blob.
- **Display:** Mission Control groups commitments by `READY_TO_FINISH`, `WAITING_ON_REVIEW`, `WAITING_ON_HUMAN`, `MERGED_NOT_LIVE`, `VERIFIED_DONE`, `BLOCKED`. Each row displays age, owner, exact next action and source evidence.

## SLA proposal (configurable by workstream/risk)
- Every 15–30 minutes: reconcile accepted missions and active PRs, regardless of whether a build process still exists.
- At 1 hour in review: one reviewer reminder or available-plan queue assignment.
- At 4 hours without valid state change: SPM reassigns reviewer or builds recovery plan and posts a deduplicated escalation.
- At 24 hours: founder/Mission Control escalation with named blocker and one proposed recovery; *never* a silent auto-approve.
- Reviewer retry cap: 2 attempts. Permanent failures escalate; preserve actual error.
- Each alert has stable `issue|stage|candidate revision|problem` fingerprint. Persistent outbox with acknowledged delivery is required before real notifications are activated.

## Queueing
Separate lanes: (A) finish/review/verify, (B) new builds, (C) human decisions. Default policy should reserve available **agent** capacity for overdue A work; it must not starve B because founder approval is pending in C. WIP limit and queue thresholds must come from actual throughput baselines, not arbitrary “10 projects max.” A change to scope creates a new versioned mission contract, not endless relabeling of Done.

## Verification and authority constraints
- One independently verified Codex **or** Cursor review satisfies the **review** requirement, where fleet policy allows. This does not satisfy **release authorisation**.
- Rana normally assesses risk-heavy technical changes; Phill retains founder access with logged continuity path; protected actions still observe governing approvals.
- `pr_head_sha` must equal review and approval receipts. Github merge SHA can be a separate commit: deployed/verified runtime SHA must equal **merge SHA**, not necessarily PR head.
- Never count cancelled work as delivered. A human decision to stop a project requires a recorded cancellation receipt; cancellations/exclusions cannot silently satisfy an active deliverable.
- The old session `status=complete` can describe a **build phase** but MUST NOT drive `linear_state=Done`.
- A project's scoped children must all individually satisfy verified completion before project close. Evergreen backlogs are not finite project scopes.

## Test proof in this local worktree
`python3 -m pytest tests/test_delivery_closure.py -q` (targeted tests). Tests include false Done on missing/stale receipts, 72-hour review escalation, missing owner, unverified merged deploy, pending human approval, repeated-scan idempotency, deliberate project scope, and non-production delivery verification.

## Next acceptance gates (not yet achieved)
1. Add a real read-only GitHub + Linear + deployment collector, with paging, privacy scoping, server-side credentials, rate-limit and stale-data handling.
2. Persist state transitions and alert fingerprints across worker restarts; simulate network errors, duplicate callbacks, review-head invalidation, and API outage.
3. Wire to the **existing 15-minute pulse or scheduler** with a single worker lease, not an independent 15-minute noisy cron; keep read-only mode until authorised.
4. Add receipt-bound publish/merge constraints and project closure transition **after** independent review, the correct human release authorisation and verified production.
5. Canary a real current review-stalled PR, capture timestamped evidence in Linear and Mission Control; verify alert/recovery end-to-end, no duplicate tickets and no premature Done.

**Not done:** This local code does not yet scan GitHub PRs, post alerts, release builds, mutate Linear, merge PRs or deploy to production. The founder's estimated quantity of unfinished projects is not verified.
