# UNITE-GROUP NEXUS | PI-DEV-OPS | MISSION CONTROL
## NEXUS ONE | Final implementation blueprint 1.0

**Prepared:** 8 September 2026, Australia/Brisbane  
**Canonical repository:** `CleanExpo/Pi-Dev-Ops`  
**Observed remote main:** `2c4d346eb8d6723fe48db79c55e34eba1f33f09c`  
**Status:** researched design and implementation contract. Not installed, deployed, independently certified or authorised for production activation.

## Executive decision

Build the autonomy into the existing Mission Control. Do not build another orchestration platform above it, fork an editor, or make an LLM the authority service.

The operating principle is:

> Persist the objective. Retire failed methods. Find new evidence. Recover within authority and budget. Prove the outcome. Carry the learning forward.

Margot is the single conversational entry. Mission Control owns the durable state and execution policy. Native coding runtimes supply replaceable intelligence. The founder works from one interface on computer, tablet or phone; those devices do not each create a new orchestrator or consume a new model turn just to display state.

This is a convergence programme, not a collection of independent greenfield projects. Each new module must replace an identified responsibility or supply a demonstrated missing control.

### Evidence boundary

The repository already defines a 15–20-move horizon, anti-spin fingerprints, independent verification, capability promotion and a separate signed admission boundary. Those contracts are reusable. They also explicitly distinguish hooks and schema validation from real execution authority. [R01–R03]

The remote commit was re-read for this design. Host processes, local dirty roots, actual account balances, deployed database catalogues and production controls were not live-tested in this session. An older repository audit is historical evidence, not proof that a reported problem still exists today. An independent multi-provider review of this blueprint has not been performed.

## 1. Product outcome and non-goals

Phill states an outcome once. The system finds the current task, gathers admissible evidence, makes an appropriate plan, obtains an existing authority lease, selects a capable runtime, implements in an isolated workspace, tests, obtains independent review and returns a verified result. When it encounters a technical obstacle, it investigates and changes method instead of returning the obstacle to Phill as ordinary work.

The system escalates to Phill for an actual authority decision, a material business choice, a new spending commitment, an unacceptable risk or an ambiguity that changes the intended outcome. It does not ask him to choose a model, repeat a task, paste the same logs, or restart a recoverable technical workflow.

Non-goals: an unlimited subscription pool; an infallible predictor; a new general-purpose IDE; 200 constantly running models; a new graph database; a second Board; an autonomous power to change its own constitution; or a guarantee that every task can be completed without cost, access or evidence.

## 2. Minimal physical architecture

Retain the current FastAPI/Python backend and Next.js/TypeScript frontend. Implement a modular monolith with one durable store and a worker process from the same codebase where practical. A logical component is not a new microservice.

```text
Computer / iPad / phone / approved channel
                    |
           Margot + Mission Control UI
                    |
        AUTHENTICATED MISSION CONTROL API
                    |
  Control kernel: policy, budgets, leases, state machine
                    |
       +------------+------------------+
       |                               |
 Knowledge + context            Planning + recovery
       |                               |
       +-------------+-----------------+
                     |
            Provider/runtime broker
                     |
          Approved host worker agent
       +-------------+--------------+
       |             |              |
   Claude Code   Codex runtime   Cursor Agent
       |             |              |
       +-------------+--------------+
                     |
       Deterministic tests + independent review
                     |
         Receipts -> learning -> next work
```

Six implementation modules are sufficient:

| Module | Sole responsibility | Reuse first |
|---|---|---|
| Control kernel | Authority, reservations, state transitions, leases and cancellation | Senior Harness, admission enforcement, Unlazy |
| Knowledge/context | Scoped source records, currentness and ContextPacks | Librarian, conversation store, lessons, Wiki and VCC |
| Planning/recovery | Goal queue, horizon, gap discovery and uncertainty cases | SPM, NorthStar, Board, existing anti-spin contract |
| Runtime broker | Eligible account/model/runtime selection and execution adapters | Existing provider seams and model farm |
| Verification/learning | Evidence acceptance, independent review, replay and candidate learning | `/done`, judge, existing tests and receipt contracts |
| Founder cockpit | Margot, priorities, work, decisions and exploration | Existing `/control` and authentication |

No Kafka, Kubernetes, Neo4j, Temporal, new vector service or additional dashboard is justified by this blueprint. Reconsider a dependency only when measured requirements exceed the existing implementation and a reviewed decision records the benefit and migration cost.

Use the existing durable queue where it meets the contract. Supabase Queues is an available Postgres-native option, not a mandate to replace a working queue. Its visibility-window delivery semantics do not remove the need for application idempotency and fencing. [D10]

### Hosting and devices

Keep the current authoritative deployment location during the first slices. A future move is an explicit migration, not an incidental configuration edit. Use the Mac Mini as the preferred always-on worker only after host readiness is proved. The MacBook remains interactive and optionally supplies admitted workers. Windows remains review-only until native containment, signed identity, fencing, checkpoint and recovery have passed their acceptance tests.

One logical controller does not require one fragile physical computer. Conversely, closing a browser does not keep a laptop worker alive: continued execution needs an awake, connected, admitted host. Closing Phill's client must not stop work already running elsewhere.

During a control-plane outage, a worker can finish only explicitly leased local steps whose authority remains valid. It cannot renew its own authority, start new remote mutations or perform a protected release. Buffer receipts durably, then reconcile on reconnect. No disconnected multi-master authority.

## 3. Identity and context: one experience, separate scopes

Use a stable founder workspace with explicitly scoped conversation threads, rather than one lifetime transcript mixed across every business.

Identity layers:

- **Founder workspace:** Phill's authenticated access to the system.
- **Scoped thread:** company/project/task context, including a separate private-personal scope.
- **TaskContract revision:** immutable objective, constraints, acceptance criteria and source bindings.
- **Run:** one attempt against that revision, with events, candidate and receipts.
- **Runtime session:** a disposable Claude/Codex/Cursor process or thread.

`FounderSession` is the continuity view across these records. `TaskPacket` is a compiled handoff view over the existing TaskContract and evidence, not another competing task database. Existing IDs and APIs stay compatible through mapping adapters.

Device bindings require authenticated ownership, not matching names or email-shaped strings. Telegram/Slack identity is explicitly linked to the founder or a scoped collaborator. Public or shared channels never inherit the full private founder context.

A device switch loads state and an event cursor. It does not ask an LLM to reconstruct the session. Two devices can submit distinct commands safely; duplicate submissions reuse an idempotency key. Conflicting task changes require a contract revision rather than last-writer-wins overwriting authority. Per-device scroll and layout preferences are separate from shared business state.

## 4. Human-out-of-loop execution with a stable authority boundary

The objective is to remove routine supervision, not remove ownership.

A trusted service issues an **AutonomyEnvelope** from existing policy or explicit founder authority. It binds principal, repository, exact contract revision, permitted operation classes, worktree, data destinations, quality floor, time/spend ceilings, expiry, revocation generation and approval requirements.

Agents propose actions. Deterministic enforcement grants or denies them. A model cannot mint or renew the envelope, increase the budget or change the acceptance tests to pass its own work.

| Lane | Intended unattended behaviour | Boundary |
|---|---|---|
| Discovery | Search approved sources, inspect repositories, classify failures, prepare a plan | No extra data destinations or unapproved spending |
| Delivery | Edit in admitted isolation, run approved tests, repair, prepare evidence and review | Existing mutation grant and exact scope required |
| Recovery | Change technical approach, refresh evidence, retry eligible transients, choose an approved alternate worker | Same parent budget and authority; no permission escalation |
| Release/business | Merge, deploy, send externally, spend, migrate production, delete, change accounts/credentials | Existing founder gate remains in force |

A later policy may authorise a very specific recurring operation, subject to existing constitutional approval. It must name the allowed environments, maximum impact, rollout, rollback and independent evidence requirements. This document does not activate such a policy. Production release, budget increases and changes to the control kernel remain protected.

The repo's current admission design requires an external signer, tightly scoped consumer roles, revocation and fresh-child resume evidence. Hook presence alone does not meet this standard. [R02–R03]

## 5. The persistent objective engine

One state machine owns continuation. Native `/goal`, scheduled loops, Stop hooks and framework retries may operate only as subordinate mechanisms with a declared owner and shared limits. Do not stack them so that each silently restarts another. Claude's current native `/goal` is useful, but is not independent cross-vendor acceptance or portfolio authority. [D05]

Proposed durable task states:

```text
PROPOSED -> ADMITTED -> READY -> RUNNING -> VERIFYING -> ACCEPTED
                               |             |
                               +-> INVESTIGATING -> READY
                               +-> WAITING_FOR_CAPACITY
                               +-> WAITING_FOR_EVIDENCE
                               +-> NEEDS_AUTHORITY
                               +-> CANCELLED
```

A task never disappears merely because a process exits. Every non-terminal state has an owner, last checkpoint, next eligible action, wake trigger and deadline/expiry. No new evidence means no blind repeated attempt.

Use a transactional state change plus outbox event. Consumers deduplicate, report completion and retain the external correlation ID. An ambiguous timeout on an external mutation means reconcile the prior outcome, not issue the action again blindly.

### Recovery matrix

| Failure | Automatic response inside authority | Stop condition |
|---|---|---|
| Transient network/rate limit | Bounded backoff with jitter, reuse idempotency key, honour retry timing | Retry/time budget or provider reset reached |
| Code/test regression | Capture failing gate, isolate hypothesis, repair the owned candidate, re-test | Existing anti-spin threshold or scope change |
| Missing knowledge | Query the appropriate authoritative source; compare alternatives | Evidence cannot be obtained within the admitted scope/budget |
| Runtime/model unavailable | Route to an eligible tested alternative at the same or higher quality/privacy floor | No eligible target or reserve breach |
| Worker death | Fence old lease; verify checkpoint and workspace; obtain fresh resume lease | Identity, containment or checkpoint cannot be proved |
| Security/authority violation | Contain affected run, preserve evidence, stop the prohibited action | No automated bypass or weaker fallback |
| Ambiguous requirement | Resolve from source hierarchy and existing decisions | A material business decision genuinely remains |
| Budget exhausted | Checkpoint and wait; pursue unrelated eligible work | No extra spending or larger allowance inferred |

Preserve the existing rule: after two materially distinct failed attempts, or its configured evidence-stagnation boundary, stop the pathway and open an uncertainty case. Do not silently relax the current five-minute evidence rule. If it proves inappropriate for an observable long command, propose and test a narrowly defined policy change instead of ignoring it. [R01–R02]

The uncertainty case assigns at least two distinct diagnostic perspectives and an arbiter, with fresh contexts and a discriminating experiment. It can execute sequentially to respect capacity. All costs belong to the original objective's parent budget. A second uncertainty case cannot reset that budget. If the new evidence supports a genuinely different method, admit a new attempt. Otherwise retain a resumable waiting state and work on another eligible objective.

## 6. Fifteen to twenty moves ahead, without pretending to predict the future

Use a **receding horizon**: maintain a linked 15–20-move strategic path, but execute only the next admitted frontier. Near moves are detailed; distant moves are conditional options. Re-plan when evidence changes, not on every UI refresh or every token.

Each move names a state change, dependencies, source evidence, owner, value, confidence basis, counter-case, cost ceiling, reversibility, trigger, expiry and required authority. Scenarios are not forecasts. A numerical forecast additionally needs a resolution question/date/source and a scoring method. [R02]

Default design limits are in the inactive policy proposal. They are tuning proposals, not measured optimal values or a live grant. The existing contract must be reconciled before adopting them.

### Example 20-move Mission Control horizon

| Move | Observable state change | Admission |
|---|---|---|
| 01 | Current branch/PR/host bindings recorded without touching dirty roots | Read-only |
| 02 | Pilot's critical sources and deployed-schema requirements identified | Read-only |
| 03 | Existing capability owners mapped; duplicate proposed stores rejected | Read-only |
| 04 | Exact bounded pilot outcome and acceptance tests frozen | Spec review |
| 05 | Eligible host/runtime and billing identities proved | Approved probes |
| 06 | Trusted authority and root budget reservation validated | Existing grant |
| 07 | One canonical task linked to Margot and the founder thread | Isolated build |
| 08 | One bounded ContextPack assembled with provenance | Isolated build |
| 09 | One worker obtains fenced ownership and checkpoints | Isolated build |
| 10 | Candidate completes the target user journey | Isolated build |
| 11 | Mandatory local gates run against that candidate | Test authority |
| 12 | Independent reviewer either accepts or files evidence-bound findings | Review authority |
| 13 | Recovery loop resolves findings without duplicate ownership/spending | Same scope |
| 14 | Desktop-to-phone continuity survives disconnect without model restart | UI test |
| 15 | Usage, attribution and cancellation receipts reconcile | Test |
| 16 | Protected-action request binds exact candidate and environment | Request only |
| 17 | Approved rollout/rollback mechanism passes a contained rehearsal | Separate authority |
| 18 | Pilot outcome and operating cost measured against baseline | Read-only |
| 19 | A useful lesson passes independent replay; ineffective scaffolding is proposed for removal | Learning policy |
| 20 | Next portfolio pilot is chosen from evidence, not automatic expansion | New admission |

This horizon includes authority gates; it is not a script granting permission to perform all twenty moves.

## 7. The specialist bench and constructive pressure

Represent the proposed 200 specialists/verticals as a capability catalogue, not 200 resident model processes. The number is a capacity/design ambition until actual registered capabilities are inventoried and tested.

A specialist pack contains domain scope, approved sources, skills/tools, data restrictions, representative tasks, acceptance rubrics, costs, freshness and version lineage. A title does not establish expertise. Australian/New Zealand restoration, training and operational requirements remain domain-specific evidence, not generic imported assumptions.

Retain the current Board, SPM and engineering seats. Do not add another executive hierarchy. Board output is advisory, never legal corporate authority. Named public figures may inspire principle packs, but are not simulated participants or endorsers.

The delivery driver challenges each material proposal with: what is the smaller solution; what evidence is missing; what breaks next; what can be reused; what alternative advances the goal faster; and what test would falsify this claim? It rewards verified progress, not confident prose or larger task lists.

Use a single specialist when sufficient; two or three for a cross-disciplinary change; all five engineering seats only for a consequential design or unresolved uncertainty. Existing independent-review requirements always take precedence. Fresh-context seats reduce anchoring but do not by themselves establish cross-vendor diversity.

Record runtime vendor, model developer/family and actual served model. Cursor using an Anthropic model is not a different model family from Claude. Unknown provenance cannot satisfy a strict different-family requirement. An arbiter preserves factual dissent; majority voting never overrules an unaddressed invariant violation.

Anthropic's multi-agent research reports substantial token amplification in its own system, and its later harness study shows that removing no-longer-useful scaffolding can be valuable. Treat both as reasons to measure, not universal promises about this estate. [D06–D07]

## 8. Native runtime fabric

The broker handles selection; native products retain their documented execution and authentication mechanisms.

| Adapter | Preferred integration | Required verification |
|---|---|---|
| Claude subscription | Existing Agent SDK where it preserves controls; documented programmatic Claude Code for bounded jobs | Actual subscription identity, clean inherited environment, supported permission path, timeout, output and quota telemetry |
| Codex subscription | Documented non-interactive/SDK surface for bounded jobs; App Server custom-client integration is a version-gated canary | ChatGPT auth, protocol schema, cancellation, approval and account quota scope |
| Cursor subscription | ACP for a structured custom client; headless stream-json for bounded jobs | CLI version, cursor_login/account identity, supported permissions/hooks, output and billing attribution |
| DeepSeek direct | One approved API adapter with isolated credentials and current tariff | Data-use policy, model compatibility, preflight cost bound, usage settlement |
| OpenRouter API | Existing adapter behind broker admission | Model/provider allowlist, data policy, per-key and task budget |
| MiniMax drain | Existing eligible adapter only | Confirmed remaining prepaid balance, no recharge, scope/privacy suitability |

OpenAI documents App Server integration, authentication and rate-limit reads, but its current page also warns that the app-server command and WebSocket transport are experimental and not supported for production workloads. Use the documented SDK/non-interactive surface for the first bounded production pilot; keep App Server integration opt-in and non-load-bearing until the targeted version and transport have an acceptable support posture. Stable protocol fields do not negate a transport-level warning. Cursor documents ACP and headless streaming. Claude documents programmatic execution and subscription rate-limit fields. [D01–D04, D08–D09]

Do not emulate users to evade product restrictions, recycle tokens into unofficial model proxies, share personal accounts between people or assume subscriptions are resellable capacity. Use only supported personal-account/runtime access and honour the provider's applicable terms and limits. Store no account emails, keys or bearer tokens in task context.

### Capability manifest

At enrolment record actual installed binary version/digest, supported protocol schema, tool restrictions, isolation, model discovery, cancellation semantics, usage coverage and observed billing account. Capabilities are `supported`, `unsupported` or `unknown`. Probe the exact host/version; a webpage describing a feature is not proof it works on that host.

CLI hooks are defence in depth. Workers must also be constrained by host isolation, limited credentials and the runtime authority boundary. A git worktree is source isolation, not a security sandbox.

### Current billing detail

The Claude support page currently retains a prominent notice that its proposed Agent SDK billing change is paused: SDK and `claude -p` continue to draw from subscription limits. Its old text remains below the notice. Never build a tariff parser that reads the superseded section as current policy. [D02]

Claude's documented status-line quota fields appear for subscribed accounts after a model response and can be individually absent. Do not burn paid model calls merely to refresh a gauge. Codex App Server exposes `account/rateLimits/read`, subject to the experimental-integration restriction above; use supported usage readback rather than introducing an unsupported production dependency solely for a gauge. Cursor quota visibility must use the supported actual surface; no fabricated individual-plan endpoint or guessed percentage. [D01, D03]

## 9. Resource control and economics

Optimise completed, accepted work, not equal tokens or equal numbers of turns.

Selection order: authority and privacy -> capability and quality floor -> host readiness -> independent-verifier capacity -> budget/reserve -> measured expected value and latency. Cheap is not eligible when it violates a hard floor.

Default initial operating proposal: three concurrent model jobs globally, no more than one expensive active job per subscribed account, and a root-level experimental budget. The council can run in waves. Raise concurrency only after measuring memory/CPU pressure, quota burn and queue latency. Local lint, tests and indexing use machine resources, not LLM turns.

Keep separate ledgers for subscription fee, observed provider quota windows, API cash charges, prepaid credits, and total infrastructure/voice/search costs. A subscription job may have zero incremental invoice cost while consuming scarce included capacity. API-equivalent token price is not necessarily the user's actual bill.

Reserve capacity per account/window, including planned verification and recovery. Reserves are admission guard bands, not perfect hard predictions of opaque native billing. Headroom forecasts carry uncertainty and age. Unknown or stale state permits only the separately approved conservative diagnostic lane, never a false '100% available'.

For API calls: atomically reserve the safe maximum charge for the request, including bounded output/reasoning/tool costs and retries, then settle against authoritative usage. Deduplicate settlement. Hold unresolved reservations after ambiguous timeouts. For unknown tariffs or unbounded cost surfaces, automatic spend is ineligible until bounded. All parallel jobs, nested agents and reroutes share the same root ceiling.

Use provider-side spend controls as a second boundary. OpenRouter documents per-key limits/reset periods and usage; keep its management credential out of inference workers. Cursor documents turning usage-based billing off. [D11–D12]

No autonomous recharge, subscription purchase, account cancellation, budget increase, paid-provider fallback or automatic redemption of a scarce reset without its specific existing authority.

### Illustrative budget, not a billing change

Using Phill's stated amounts in one common billing currency:

- Current subscriptions: Cursor 260 + Claude 600 + OpenAI 200 = 1,060/month.
- Current OpenRouter allowance: 25/week × 52/12 = 108.33/month average.
- Current combined ceiling: approximately 1,168.33/month, excluding further MiniMax recharge.
- Requested retained core: Cursor 60 + Claude 200 + OpenAI 200 = 460/month.
- Add a proposed DeepSeek cap of 25/month and proposed OpenRouter reduction to 10/week: approximately 528.33/month.
- Difference: 640/month, or 7,680/year, before tax, FX and additional hosting/search/voice costs.

The optional DeepSeek and lower OpenRouter limits are proposals until approved. Keeping OpenRouter at the user's current 25/week would make that target approximately 593.33/month. Existing MiniMax credit is not a new monthly subscription. No account action was performed.

## 10. Clean knowledge and cheap context

Do not introduce one mutually exclusive state enum that tries to represent every property of data. A verified calculation can also be derived, stale and confidential. Represent these separately:

```text
origin: human | connector | repository | model | simulation
verification: unchecked | supported | disputed | rejected
lifecycle: current | superseded | expired | revoked
sensitivity: public | internal | confidential | client | personal
authority: none | proposal | authenticated_grant
```

Every source has scope, source ID/revision/hash, observed/known/valid times and provenance. A hash proves byte identity, not truth. Repeated summaries of one source count as one lineage, not independent corroboration. Simulation lineage propagates through derived results. A model can propose a claim; it cannot self-promote that claim to authority.

Treat the current Wiki and lessons as useful existing investments. Do not rewrite the entire estate before the pilot. Admit new material through staging and provenance checks; repair high-impact existing contamination first. Generate views only where existing consumers support the transition. Preserve human notes, history and rollback.

The Context Compiler filters permission, company/project, currentness and source trust before relevance. It packs complete evidence groups and records inclusions, omissions and token estimates. Reviewers can request needed dependencies through a bounded expansion path; a tiny packet that hides relevant code is not efficient review.

Keep mandatory constraints and negations intact. Do not apply whitespace/truncation transforms indiscriminately to source code, patches, signatures or language-sensitive material. Cache using scope, permission generation, source revisions, model/tokenizer and policy versions; revoke dependent caches when permissions or evidence change.

Local CLI execution does not imply local model inference or zero data egress. Destination approval applies to every provider, research query, embedding job, voice service and fallback.

## 11. Self-learning without self-corruption

Learning means improving versioned skills, failure signatures, routing estimates, retrieval and tests. It does not mean the running model magically retrains itself or acquires independent desires.

```text
Observed outcome -> candidate lesson/skill
 -> independent evidence check
 -> held-out replay in clean environment
 -> scoped canary
 -> promotion under an existing learning policy
 -> monitor and rollback/revoke
```

Record negative outcomes, failed repairs, elapsed time, total calls and stale-data mistakes, not just successful runs. Evaluate by comparable task class, difficulty and environment. Report sample counts and uncertainty; never use a global leaderboard to make a code reviewer appear better because it received easier tasks.

Promotion and tests are separate principals and write paths. An agent cannot edit the grader, delete a failing case or select only favourable results. Provider/model/policy/dependency changes invalidate affected evidence and trigger revalidation.

Changes to permissions, spending ceilings, release logic and the control kernel may be proposed and tested in isolation, but never auto-promoted by the system they govern. Preserve an external stop/recovery path and the last trusted control version.

## 12. Always-on intelligence and gap discovery

Always-on means event listeners, a durable queue, deterministic monitors and resumable work. It does not mean frontier models constantly thinking.

Use a single governed schedule registry for webhooks, host heartbeats, due-date checks, health signals, documentation changes, nightly changed-area tests and the weekly strategy review. Jobs have ownership, a dedupe key, leases, budgets, output contract and backoff. Inventory and retire duplicate cron/launchd loops only with evidence.

Discover gaps from a join of accepted goals, claimed capabilities, observed runtime behaviour, incident/test evidence and current source requirements. A missing capability becomes a candidate backlog item, not automatic scope growth.

The improvement backlog prioritises the critical path, revenue proximity and user pain. Include 'do nothing', reuse and removal as candidates. UI polish and research have explicit budgets so they cannot starve revenue delivery. Unchanged state produces no new research call. A failed technical task does not paralyse unrelated admitted work.

The five-seat council is a paid intellectual tool: load it only when expected information value warrants its cost. Preserve counter-cases without performing ceremonial disagreement.

## 13. Founder cockpit

The primary navigation is **Now / Work / Decisions / Explore**, with Margot always accessible. The phone starts with Margot and the few highest-value items. Desktop adds dockable work/evidence/log panes; iPad uses a two-pane mission view. Reuse the repo's gun-metal surfaces, signal colours, Geist typography and design tokens. [R07]

A task card answers: what is being achieved, current verified phase, last evidence, blocker/next step, resource use and any decision required. Avoid invented percentages; '7 of 10 specified checks passed' is different from '70% complete'. Quota percentages require actual provider evidence.

Controls: pause new dispatch; drain a provider; cancel a task; stop the fleet; inspect receipts; inspect source; and review a scoped action request. Cancellation displays requested/acknowledged/expired/reconciled, not instant success when a host is unreachable. An offline phone cannot claim to have stopped a remote machine.

Installable PWA, safe-area support, readable touch targets, keyboard/screen-reader access, reduced motion, clear empty/loading/stale/error states and responsive 320px+ layouts are requirements. Sensitive responses are not indiscriminately service-worker cached. Offline drafts may queue; approvals and privileged actions require live authentication, revocation and candidate checks.

Voice reuses the existing approved Margot voice path only after discovery. It needs microphone permission, interrupt/stop, visible transcript, sensitive-notification redaction and a distinct spend ledger. Transcription alone cannot approve a protected action. No voice impersonation or new voice vendor is activated by this blueprint.

`cockpit-preview.html` is a self-contained interaction prototype. Its data is synthetic, its actions do not reach the system, and it is not a production or safety-control implementation.

## 14. Security and fault containment

Use per-host identities, minimum tool/credential privileges, short scoped execution leases, process-tree cancellation and OS-level isolation. Browser/MCP results and repository instructions from untrusted sources are data; they cannot expand permissions. Keep build output, authority credentials, signing keys and production release credentials in distinct trust boundaries.

Treat MCP as a tool protocol, not a safety guarantee or shared provider-billing bus. Apply audience validation, explicit consent and minimal scopes. Never relay a token indiscriminately to unrelated downstream APIs. [D13]

Keep authenticated user checks at the outer UI API as well as the upstream authenticated service. A shared backend session helper is not a substitute for checking the actual caller. Privileged database views/functions need their own permissions and row/scope checks.

Before resuming, re-check contract/candidate identity, authority expiry/revocation, worktree ownership and model/runtime policy. If a lost worker returns, its obsolete fencing generation cannot write accepted state. If a live side effect has uncertain outcome, reconcile using the existing external operation ID before retry.

Backups require restore tests. Store sensitive payloads separately from minimal audit metadata so approved retention/erasure can remove data and invalidate derived indexes without preserving secrets forever under the label 'immutable'.

## 15. Implementation sequence: one vertical pilot, then expansion

Do not delay the first usable result until every historical record or every provider is rebuilt. Do not launch an unbounded estate-wide refactor.

**Slice A | audit and freeze.** Read exact repo/branch/PR and the latest handoff; map only the pilot's critical state/authority/cost paths. Inspect the relevant current catalogue rather than treating old schema-drift notes as current proof. Reuse existing SPM and acceptance contracts. Produce one accepted bounded spec; leave dirty roots unchanged.

**Slice B | one working loop.** Connect Margot -> canonical task -> one admitted Mac worker -> deterministic gates -> independent review -> receipt. Add durable checkpoints, idempotency, root budget admission and cancellation on this path. Test a synthetic task first and a bounded real non-production task under authority. No cosmetic dashboard-only completion.

**Slice C | recovery and continuity.** Prove a failed first approach leads to a new evidence-based method, worker death cannot duplicate ownership, and phone/iPad reconnect restore the same scoped thread and task. No model call solely for device navigation.

**Slice D | capacity and context.** Shadow the broker and Context Compiler against current behaviour. Add verified native Claude/Codex/Cursor integrations one at a time. Add an API lane only under its explicit budget and data policy. Promote through approved canaries; retain rollback.

**Slice E | horizon and learning.** Wire the existing horizon/uncertainty contracts, specialist routing, gap discovery and held-out learning into the proven loop. Measure whether each mechanism improves the pilot. Remove ineffective scaffolding by reviewed change.

**Slice F | portfolio expansion.** Roll out to additional repositories with domain-specific gates. Bring Windows beyond review-only only when its controls are independently proved. Keep existing Unite-Group and RestoreAssist repair tasks/PRs separate; do not open competing repair branches or publish ChatGPT Sites.

Every slice: exact-base evidence, existing local CI-parity runner, focused tests, required independent exact-candidate review, remote check readback only after an authorised push, and a truthful handoff. Code exists != enabled != healthy != independently accepted.

## 16. Acceptance and economic proof

See `ACCEPTANCE.md`. Acceptance includes positive controls as well as failure cases. A system that blocks every action is not a successful autonomous system.

Hard properties within the tested scope: no unauthorised protected action; no successful stale-lease write; no unlabelled synthetic evidence in operational output; no self-acceptance; no duplicate admitted task from duplicate input; no lost acknowledged checkpoint; and no API dispatch whose reserved bound exceeds its approved root ceiling.

Initial performance targets, subject to measured baselines: at least 50% fewer founder interventions on comparable bounded work; at least 30% lower redundant context input without quality loss; zero LLM calls for navigation/handoff; and materially lower cash ceiling after actual authorised subscription changes. These are design targets, not achieved results.

Track accepted outcomes per week, total time to acceptance, cash and quota per accepted outcome, escaped defects, human interventions, false blocks, duplicate work, recovery success, privacy incidents and maintenance burden. The '10x' aspiration is accepted only for a named metric against an observed baseline. Faster unsafe output does not count.

## Final operating contract

The system may be ambitious in exploration, persistent in problem solving and economical in execution. It may not be vague about authority, evidence, money or completion.

The next step is the first approved vertical pilot, not another rewritten architecture or another subscription.
