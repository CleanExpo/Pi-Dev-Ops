# SPM Scope: Nexus `model-router` + `unlazy`

**Status:** Planning artifact only. No skill, adapter, hook, runtime, or provider configuration is implemented by this document.
**Date:** 2026-08-21
**Research commit baseline:** `8600b4c9da5b68fc51c424e47cdf6136041ef3dc`
**Current `origin/main` evidence baseline:** `304d2ce89b592e79bb8bc4b5adb07d76d50c50b9`
**Public Unlazy evidence baseline:** `Leonxlnx/unlazy@ed9e8d2b5919698cf2c54bda270d507e10b69617`

> Implementation must start from a fresh isolated worktree at the then-current `origin/main`, not from this planning worktree. Rebind every code, test, provider, price, and model claim after fetching because the planning branch is behind the exact-main evidence baseline.

---

## 1. Task being planned

| Field | Detail |
|---|---|
| Original request | Define the correct prompt pathway and skills for routing work among Claude Code, Codex, and VS Code/OpenRouter while using the best-fit model for subagents, senior agents, and orchestrators; combine it with the public Unlazy `tree N` completion method and the rolling-dispatch ideas shown in the supplied video frame. |
| Interpreted task | Specify two Nexus-owned skills, `model-router` and `unlazy`, plus a shared decision schema, tested rolling orchestration, thin harness adapters, exact-run evidence, and cost/credit telemetry. |
| Target outcome | An implementer can build the skills and adapters without inventing task classes, tier meanings, tree semantics, ownership rules, prompts, gates, receipts, tests, rollout controls, or completion criteria. |
| Non-build clarification | This document does not install upstream Unlazy, reproduce the private AI LABS patch, select permanent model IDs, or perform the requested Obsidian-to-Wiki content transfer. |

## 2. Current project context

| Field | Detail |
|---|---|
| Repo | `CleanExpo/Pi-Dev-Ops` |
| Branch | `codex/unlazy-model-router-scope` |
| Working tree | Dedicated external-storage worktree. Only this `.spm` artifact is owned by this planning slice. |
| Relevant systems | Canonical `skills/` library and projection sync; Claude Code; Codex; VS Code/OpenRouter; existing provider router, model policy, Tier-0 lane, budget tracker, and agent registry. |
| Sources inspected | `docs/RESEARCH-unlazy-model-routing-2026-08-21.md`; all three supplied screenshots; `skills/skill-authoring-standard/SKILL.md`; its frontmatter schema and review checklist; exact-main routing files named below. |
| Current routing truth | `app/server/model_policy.py` is the role/model guard; `app/server/provider_router.py` resolves role tiers to providers/models; `app/server/provider_openrouter.py` executes OpenRouter calls; `app/server/tier0_lane.py` and `tier0_runner.py` handle capacity-aware gathering; `swarm/budget_tracker.py` records spend but does not enforce it at every call site. |
| Current duplication | `swarm/model_router.py` has a separate `FRONTIER/WORKING/REMEDIAL/LOCAL` vocabulary and fallback ladder. The new skills must not become a third provider-routing implementation. |
| Existing agent roles | `config/harness/agents/registry.yaml` already defines scout, planner, builder, verifier, reviewer, security, CI recovery, and release-monitor roles with evidence expectations. |
| Known unknowns | Exact model availability, prices, context windows, tool/structured-output support, harness-level model overrides, and subscription-credit telemetry can drift and must be discovered at runtime. |

### Source boundary: public method versus private video patch

The public Unlazy repository provides Markdown skills, plan/gate references, three zero-dependency Node scripts, a sequential driver contract, and a Claude Code Stop hook. It does **not** contain:

- a `tree N` parser;
- a rolling scheduler;
- `Owns/Needs/Tier` plan metadata;
- a tested `--jobs` gate runner or shared-check de-duplication;
- OpenRouter, Codex, or VS Code adapters;
- model routing or savings telemetry.

The third screenshot and video describe a private/refined patch. They are requirements evidence only. Implementation must be a Nexus-owned, clean-room design. Do not claim that public Unlazy supplied or tested those private features. Retain the upstream MIT notice for any copied public text or code.

## 3. Problem statement

| Field | Detail |
|---|---|
| User | Phill and the major-agent stack spanning Claude Code, Codex, and VS Code/OpenRouter. |
| Pain | Expensive models are used for work that lower-cost models can safely do, while model routing, fan-out, completion proof, and credit usage are expressed as scattered prose and overlapping runtime policies. |
| Current workaround | Manually name a model, role, tree depth, or subagent pattern; rely on host-specific habits and independent provider routers. |
| Business impact | Avoidable paid inference and subscription-limit consumption; slow wall-clock delivery from lockstep orchestration; weak evidence for claimed savings or completion. |
| Technical impact | Provider names leak into task policy, harnesses have unequal enforcement, concurrent agents can collide on files, and an apparently green leaf can bypass root integration proof. |
| Why now | The public Unlazy method supplies a useful completion contract, the video exposes the lockstep bottleneck, and exact-main already has provider/cost primitives that should be reused rather than replaced. |

## 4. Desired outcome

Build a two-skill control plane:

1. **`model-router`** classifies substantive work, decides inline/delegate/fanout, assigns an orthogonal task class, worker role, quality floor, effort, privacy posture, verifier floor, escalation rules, and spend bounds, then emits a machine-readable route decision. It never dispatches work or declares completion.
2. **`unlazy`** turns substantial work into a dependency tree, freezes ownership/contracts, writes leaf/branch/root gates, asks `model-router` for each executable node, performs bounded rolling dispatch through the active harness adapter, verifies returns, and refuses a success claim until root gates pass.

Provider resolution remains downstream:

```text
user request
    |
    v
model-router skill -----> RouteDecision (capability, lane, effort, budget)
    |                                  |
    | substantial / explicit tree      | inline
    v                                  v
unlazy skill                       current major agent
    |
    v
tree + contracts + gates + ready queue
    |
    v
harness adapter (Claude | Codex | VS Code/OpenRouter)
    |
    v
existing model_policy + provider_router + provider clients
    |
    v
workers -> verifier -> branch/root gates -> evidence + cost receipt
```

The skill names, policy vocabulary, and receipt schema stay stable while provider/model mappings are versioned configuration refreshed from current primary data.

## 5. Scope

### In scope

- Canonical `model-router` plain-technique skill, route request/decision schema, deterministic decision policy, escalation policy, prompt pathway, and golden evals.
- Canonical `unlazy` command skill, natural-depth tree semantics, contract/ownership schema, gate format, rolling scheduler, prompts, Stop-hook support, and verifier behavior.
- Thin adapters for Claude Code, Codex, and VS Code/OpenRouter with capability probing and truthful degradation.
- Reuse of existing `model_policy`, `provider_router`, `provider_openrouter`, Tier-0 lane, budget tracker, agent registry, and skill-sync conventions.
- Exact run/model/provider/SHA/gate/cost receipts, per-leaf and per-run caps, and a comparable baseline for savings claims.
- Unit, contract, golden, scheduler, mutation-control, integration, and harness smoke tests.
- Shadow-mode rollout, bounded enforcement, rollback, and migration from prose-only routing.

### Out of scope

- Replacing Claude Code, Codex, VS Code, OpenRouter, or their native agent runtimes.
- Training or fine-tuning a router model.
- Selecting one permanent vendor/model for each tier.
- Deleting every legacy router in the first slice. The two known executable `swarm.model_router` consumers must migrate to the canonical provider seam before enforcement, but the compatibility module may remain until zero-call evidence exists.
- Global installation, production deployment, or enabling paid traffic during the planning phase.
- Copying undisclosed AI LABS Pro code or representing private benchmark claims as reproducible evidence.
- Moving/deleting the Obsidian source item. That separate content operation must verify a 2nd Brain destination receipt with matching title and URL before deletion.

### Explicit non-goals

- `tree N` is not a promise of `2^(N-1)` effort, agents, tokens, or quality.
- Parallelism is not presented as token savings. It is a wall-clock optimization whose cost can increase.
- A cheap classifier is not called on every request. Obvious routes use deterministic rules; ambiguous cases may use one bounded classifier call.
- A Stop hook is not proof of completion. Only rerun gates bound to the candidate SHA are proof.
- `ABANDON` is not success. It produces `blocked` or `partial`, never root completion.
- Lack of per-call billing under a subscription is not proof of zero credit/quota consumption.

### Assumptions

- The root/driver remains on a strong, policy-allowed model and cannot change itself mid-session on most harnesses.
- Model selection is reliable only for newly delegated work where the host exposes a model/effort override.
- Concurrent editing uses isolated worktrees by default. Shared-folder concurrency is allowed only for verified disjoint paths and a harness that can enforce the boundary.
- Public gate commands are trusted-repository code. Untrusted externally supplied checks are never executed automatically.

### Constraints

- Preserve current Opus/frontier allow-list rules in `model_policy.py`; a task router cannot grant a model a role policy forbids.
- Skill frontmatter and bodies must pass `skill-authoring-standard`: correct archetype, `SKILL.md` at most 200 lines, references under `references/`, single source of truth, and review checklist clean.
- Add no runtime dependency merely for orchestration. Use the Python standard library or existing dependencies; keep any Node hook zero-dependency.
- Preserve the dirty shared checkout; implementation and verification happen in isolated worktrees on `/Volumes/Storage Unit`.
- Hard provider/model names live in versioned configuration, not skill prose.

## 6. Existing capability review

| Capability | Exact-main source | Reuse decision | Required change |
|---|---|---|---|
| Role/model ceiling and effort defaults | `app/server/model_policy.py` | Reuse as policy gate | Add no bypass. Adapter must call it or the existing provider path. |
| Role-to-provider/model resolution | `app/server/provider_router.py` | Reuse as the executable routing SSOT | Add a quality-floor translation layer, not another provider ladder. Preserve per-role downgrade correction. |
| OpenRouter execution and best-effort cost | `app/server/provider_openrouter.py` | Reuse | Normalize usage tokens, actual provider/model, finish status, and request/run IDs into receipts. Redact upstream bodies in user-facing errors. |
| Free/paid/local gathering chain and privacy gate | `app/server/tier0_lane.py`, `tier0_runner.py` | Reuse for non-mutating cheap-floor and local-only work | Make its confidentiality decision part of `RouteDecision`; test capacity and all-fallback failure. Refresh stale free-slug configuration live before enabling. |
| Cost ledger | `swarm/budget_tracker.py` | Extend | It is visibility-first. Add enforceable reservations/caps, route IDs, outcome/gate linkage, usage units, and baseline metadata. |
| Alternate swarm router | `swarm/model_router.py` | Compatibility only | Inventory call sites; adapt behind the canonical translation. Do not delete until parity, migration, and deprecation gates pass. |
| Agent roles/evidence | `config/harness/agents/registry.yaml` | Reuse | Add router lane/capability defaults or a referenced routing profile without duplicating purposes. |
| Skill authoring | `skills/skill-authoring-standard/**` | Mandatory | Use the archetypes and split branch-only material into references. |
| Skill projections | `scripts/skill_sync.py` and drift workflow | Reuse | Canonical source remains `skills/<name>`; projections are generated/checked, not hand-diverged. |

### Exact-main blockers found by the independent routing audit

The implementation gate starts at **84/100, not approved** until these current-main defects are either fixed or explicitly isolated with evidence:

1. **One executable seam:** `swarm/model_router.py` duplicates OpenRouter HTTP already owned by `app/server/provider_openrouter.py`, while model IDs also appear outside `app/server/model_registry.py`. Make `app/server/provider_router.py` the sole executable routing seam, migrate the two known consumers (`swarm/closed_loop.py` and `swarm/nexus/store_factory.py`) through a compatibility adapter, and prohibit new provider HTTP or hard-coded model IDs elsewhere.
2. **Truthful enforcement and receipts:** `provider_router.py` currently accepts `task_class` without using it, its Claude CLI path can receipt a configured model without passing the model override, OpenRouter usage can become zero-token ledger entries, and missing `role` at callers can bypass intended enforcement. Correctness gates precede cost or entitlement optimization.
3. **Honest optimizer boundary:** `fleet_value_optimizer.py` is a post-quality-floor entitlement/cost tie-breaker only. It must not choose a quality floor. Its advertised live-apply behavior and Claude-plan utilization mapping require proof before enforcement.
4. **Safe client errors:** upstream OpenRouter response bodies may contain sensitive operational detail. Preserve full diagnostics only in protected logs and emit a redacted, bounded client receipt.
5. **Whole-folder host deployment:** `install_skills.sh` projects full skill folders only to Claude, while `fence/deploy_skills.py` deploys only explicitly listed `SKILL.md` files and omits references, templates, and scripts. Replace this split with one host-aware whole-folder deployment path for Claude, Codex, and the VS Code/CLI surface.
6. **External-drive regression:** the focused current-main audit produced `109 passed, 2 failed, 1 skipped`; both failures are in `tests/test_skill_sync.py:103-139`, where approval parsing truncates a source path containing `/Volumes/Storage Unit/...`. Fix and gate paths containing spaces before claiming this machine can deploy the new skills.
7. **Stale routing prose:** existing `token-budgeter`, `claude-max-runtime`, `model-farm`, and tier skills contain stale prices, model/package names, subscription claims, or permissive evaluator thresholds. They are migration inputs, not current truth, and must not be copied into the new skills.

The reusable base remains `model_policy.select_model/assert_model_allowed/reasoning_effort`, `provider_router.ProviderModel` and unified dispatch, `provider_openrouter` response parsing, `model_registry`, `budget_tracker` receipt concepts, `evals/test_provider_router_golden.py`, and `skill_sync` promotion/manifests.

## 7. Specialist board review

| Role | Finding | Risk | Scope decision |
|---|---|---|---|
| Senior Product Manager | Users need one automatic pathway, not a menu of provider names. | Configuration choice leaks into every prompt and increases cognitive load. | Default to automatic routing with an explicit receipt and deterministic user overrides. |
| Senior Software Architect | Task policy, orchestration, harness control, and provider resolution are different layers. | A monolithic skill becomes untestable and a third provider router. | Two skills plus schemas/adapters; existing provider router stays downstream. |
| Senior Security Reviewer | OpenRouter/free providers and arbitrary gate commands can cross data and execution boundaries. | Client data exfiltration or unreviewed shell execution. | Fail closed on sensitivity; confidential data local-only unless a separately approved provider policy permits it; checks must be repository-owned and diff-reviewed. |
| Senior QA/Test Lead | A routing decision can be cheap but wrong, and a green count can hide unhandled errors. | Savings come from lowered quality or incomplete verification. | Compare only runs with the same root-gate outcome; require exit zero, no teardown errors, and mutation controls. |
| Developer Experience Reviewer | Host capabilities differ sharply. | Skill prose promises model selection or Stop enforcement the host cannot perform. | Capability probe first; unsupported automation degrades to inline/advisory with a receipt. |
| Devil's Advocate | Calling a model to decide which model to call can erase savings. | Extra latency/cost on every request. | Local heuristics first; invoke a classifier only for an unresolved decision above a configurable value/risk threshold. |

## 8. Judge challenge

This is a planning-level challenge, not a substitute for the mandatory repo `$judge` report. Implementation remains gated until a current Judge Report is attached to the implementation issue/PR.

| Category | Score | Notes |
|---|---:|---|
| First-source evidence | 22/25 | Public repository pinned and code behavior inspected; private patch remains unverified and is explicitly excluded as code. |
| Clear user/business problem | 19/20 | Cost, subscription limits, bloat, latency, and role fit are explicit. |
| Reuse of existing capability | 13/15 | Design reuses current policy/provider/Tier-0/budget/registry surfaces, but executable routing is still duplicated. |
| Security/privacy safety | 11/15 | Architecture is fail-closed; upstream error redaction and exact provider data-use policies need implementation evidence. |
| UX clarity | 8/10 | One automatic pathway with explicit override and receipt; cross-host behavior is not yet deployed equivalently. |
| Testability | 8/10 | Decisions, DAGs, caps, gates, and receipts have contracts, but the current external-drive skill-sync regression is red. |
| Deployment readiness | 1/5 | Claude-only whole-folder installation and SKILL-only manifest deployment cannot yet project the same skill package to all hosts. |
| Cost/control simplicity | 2/5 | Policy is bounded, but usage/cost receipts and entitlement optimization are not yet truthful enough for enforcement. |

**Independent-audit decision: 84/100, do not begin implementation until the deployment/path-space, canonical-seam, and truthful-receipt blockers in section 6 are accepted into the first build slice.** After those blockers are represented by RED tests, rerun the repo Judge and live provider-capability refresh.

## 9. Proposed solution

### 9.1 Two-skill architecture

#### `model-router`: autonomous plain technique

Purpose: answer, before substantive work, **who should do it, at what capability/effort, with what privacy/budget/verifier constraints, and whether to delegate at all**.

Proposed canonical frontmatter:

```yaml
---
name: model-router
description: Use before substantive work when choosing whether to work inline, delegate, fan out, or escalate based on ambiguity, stakes, scope, repetition, privacy, and prior failure.
allowed-tools: Read, Grep, Glob, LS, Bash
---
```

Contract:

- Input: normalized `RoutingRequest`.
- Output: exactly one valid `RouteDecision` plus a short human explanation.
- Does not execute, dispatch, modify files, or choose a hard-coded provider itself.
- May return `inline` when delegation overhead is larger than the task.
- May return `bailout` when the harness cannot honor the required isolation, privacy, model, or verifier contract.
- Lower tiers can escalate; they cannot self-downgrade a verifier or high-stakes task.

#### `unlazy`: user-invoked command skill

Purpose: transform explicit `/unlazy [tree N] <task>` requests and qualifying substantial delivery work into a verified dependency tree and drive it to a truthful terminal state.

Proposed canonical frontmatter:

```yaml
---
name: unlazy
description: Turn substantial delivery work into a dependency tree with owned files, rolling dispatch, executable gates, and exact completion evidence.
argument-hint: "<tree N> <task>"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, LS, Bash
---
```

Contract:

- Normalizes `/unlazy tree 5 ...`, `tree 3 ...`, or no supplied depth.
- Writes the plan/contracts/gates before implementation.
- Calls `model-router` for each executable node and verifier, never embeds provider-specific tier prose.
- Dispatches only nodes whose dependencies are passed and whose ownership does not collide.
- Returns only `passed`, `blocked`, `partial`, or `cancelled`; `passed` requires strict root gates on the exact candidate SHA.

### 9.2 Orthogonal routing taxonomy

Keep four fields independent. This prevents the incompatible current vocabularies (`frontier/working/remedial/local`, `top/mid/cheap`, and `orchestrator/specialist/worker/evaluator`) from leaking into one another:

| Field | Allowed values | Meaning |
|---|---|---|
| `task_class` | `mechanical|bounded|deep|high_stakes|long_horizon` | What reasoning/risk shape the work has. Gathering is `mechanical` or `bounded` with mutation disabled. |
| `worker_role` | `driver|senior|worker|verifier` | Responsibility and authority. Planning is performed by `driver` or `senior`; gathering by a non-mutating `worker`. |
| `quality_floor` | `cheap|mid|top` | Minimum reasoning/capability tier after task and role policy. It is not a vendor/model name or execution location. |
| `execution_location` | `local_only|remote_allowed` | Data-egress constraint computed independently from quality. |

| Worker role | Responsibility | Typical floor | Effort | May mutate? | Verification rule |
|---|---|---|---|---:|---|
| `driver` | Holds intent, plans, dispatches, integrates, reports | `top` | high | Integration-only | Never verifies its own leaf; owns root result. |
| `senior` | Architecture, subtle debugging, migrations, security design | `mid` or `top` | high/xhigh | Bounded owned paths | Independent verifier at equal or higher floor. |
| `worker` | Decided implementation, mechanical edits, or non-mutating gathering | `cheap` or `mid` | low/medium | Owned paths only | Verifier is never below the worker's floor; production mutation defaults to `mid` verification. |
| `verifier` | Reruns gates, inspects diff, rejects unsupported claims | `mid`; `top` for auth/payments/security/root integration | high/xhigh | No candidate edits | Fresh context/worktree; exact-SHA receipt. |

The backend resolves `quality_floor` through current registry/config data. `cheap` fits mechanical low-stakes work; `mid` fits bounded production work; `top` fits deep/high-stakes/long-horizon work. `execution_location=local_only` constrains that resolution to a local model that still meets the floor; it never lowers the floor. Exceptional model allow-lists remain policy configuration, not a fourth skill vocabulary. The adapter must not bypass `OPUS_ALLOWED_ROLES`, `FABLE_ALLOWED_ROLES`, downgrade correction, privacy policy, or provider allow-lists.

After the floor is fixed, resolve capacity in this order unless live policy says otherwise:

1. deterministic local tooling for work that does not need a model;
2. a policy-approved local model that meets the floor when `execution_location=local_only`;
3. an already-paid Claude/Codex entitlement that truthfully supports the required role, tools, context, and floor when remote execution is allowed;
4. a current OpenRouter model/provider for bounded worker leaves, overflow, or cross-model verification when it is policy-allowed and offers a measured cost/latency advantage;
5. an allowed direct paid provider fallback;
6. `bailout` when none can preserve the floor, privacy, budget, or receipt contract.

This order is a cost tie-breaker after correctness, not a quality decision. A subscription route records marginal billed cost separately from quota/credit use; an OpenRouter route uses the live model catalog and price snapshot rather than prose or stale constants.

### 9.3 Routing request and decision schemas

`RoutingRequest` required fields:

```json
{
  "schema_version": "1.0",
  "request_id": "uuid",
  "task": "verbatim bounded task",
  "harness": "claude-code|codex|vscode-openrouter",
  "signals": {
    "determinism": "high|medium|low",
    "ambiguity": "low|medium|high",
    "scope": "inline|bounded|multi-file|subsystem|project",
    "dependency_count": 0,
    "reasoning_depth": "shallow|normal|deep",
    "stakes": ["none|customer|auth|payment|privacy|security|legal|release|migration"],
    "volume": 1,
    "expected_minutes": 20,
    "context_tokens_estimate": 12000,
    "modalities": ["text", "code"],
    "required_tools": ["read", "edit", "test"],
    "sensitivity": "public|internal|confidential|client",
    "prior_failures": 0,
    "ownership_disjoint": true
  },
  "limits": {
    "max_cost_usd": 0.10,
    "max_quota_units": null,
    "deadline_seconds": 900,
    "max_parallel_workers": 3
  }
}
```

`RouteDecision` required fields:

```json
{
  "schema_version": "1.0",
  "route_id": "uuid",
  "policy_version": "git-sha-or-config-digest",
  "action": "inline|delegate|fanout|bailout",
  "task_class": "mechanical|bounded|deep|high_stakes|long_horizon",
  "worker_role": "driver|senior|worker|verifier",
  "quality_floor": "cheap|mid|top",
  "execution_location": "local_only|remote_allowed",
  "reasoning_effort": "low|medium|high|xhigh",
  "confidence": 0.91,
  "reasons": ["stable-pattern", "disjoint-ownership"],
  "privacy": {"data_class": "internal", "provider_constraints": []},
  "execution": {
    "max_parallel_workers": 3,
    "timeout_seconds": 900,
    "max_attempts": 2,
    "owns": ["path/a"],
    "needs": ["leaf-1"]
  },
  "budget": {
    "max_cost_usd": 0.10,
    "max_quota_units": null,
    "reservation_required": true
  },
  "verifier": {
    "quality_floor": "mid",
    "reasoning_effort": "high",
    "independent": true
  },
  "escalation_on": ["two-failed-attempts", "low-confidence", "contract-drift", "security-signal"],
  "fallback": ["mid", "top", "bailout"]
}
```

Post-resolution `RouteReceipt` adds:

- resolved harness, provider, exact model ID, provider backend, and selection source;
- actual input/output/reasoning/cache tokens where exposed;
- billed cost, marginal cost, quota/credit units, and `unknown` markers rather than invented zeroes;
- start/end time, latency, fallback chain, attempt count, and terminal status;
- repo, worktree, base SHA, candidate SHA, plan/leaf/gate IDs;
- root/leaf gate outcomes and verifier receipt ID;
- baseline policy version and comparable-outcome flag.

### 9.4 Routing decision algorithm

Compute and intersect every applicable constraint; safety rules are not first-match alternatives.

1. **Baseline class:** mechanical -> `worker/cheap`; bounded production -> `worker|senior/mid`; deep or long-horizon -> `driver|senior/top`.
2. **Privacy constraint:** `confidential|client` -> `execution_location=local_only` unless an explicit current provider policy allows that data class. This changes location, never quality.
3. **High-stakes floor:** auth, payment, privacy, security, legal, irreversible release, or migration -> at least `senior/top` plus independent `verifier/top`; never `cheap` or `mid` solely because work is local.
4. **Constraint intersection:** a confidential high-stakes task is `local_only + top` for both worker and verifier. If no policy-approved local model can meet that floor, return `bailout`; never silently route remote or downgrade.
5. **Inline bypass:** only after floors are computed; trivial work under ten focused minutes may remain inline when there is no fan-out benefit and no high-stakes, privacy, or independent-verifier requirement.
6. **Gathering:** search/summarise/classify/deduplicate -> non-mutating `worker/cheap`, constrained to `local_only` when required by privacy.
7. **Fan-out:** only if there are at least two ready nodes, disjoint ownership, useful parallel work, enough budget, and adapter capacity.
8. **Classifier:** only if deterministic rules leave a material decision unresolved. Classifier output is schema-validated; low confidence escalates upward and never routes downward.
9. **Failure:** one ordinary failure may retry the same floor with named feedback; second comparable failure escalates monotonically (`cheap -> mid -> top -> bailout`); fallbacks never downgrade the quality or verifier floor, and contract/security failures stop dispatch immediately.

### 9.5 Tree semantics

- `tree N` is the maximum requested decomposition depth, not an exact leaf count.
- The planner records `requested_depth`, `effective_depth`, and `adjustment_reason`.
- Choose the smallest effective depth whose leaves follow natural task joints.
- A leaf is one coherent deliverable worth at least about ten focused minutes, with one owner and one gate file.
- Work below about 30 minutes stays solo even if a large tree was requested, unless the user explicitly needs the plan artifact.
- Internal nodes own decomposition/integration; leaves own implementation.
- Leaves may split further only before implementation and only if the parent contract/gates are re-frozen.
- If the requested depth produces toy leaves, reduce it. Do not reset blindly to three.

| Effective depth | Default execution |
|---|---|
| 1 | Inline/no tree artifact unless explicitly requested. |
| 2-3 | Solo driver, two to four sequential leaves, one root/branch gate set. |
| 4-5 | Orchestrated when there are genuine independent leaves; bounded rolling dispatch. |
| 6-7 | Project/subsystem program only; isolated worktrees, explicit integration nodes, hard spend/time/concurrency caps. |
| >7 | Reject or reduce with rationale; depth is not a substitute for architecture. |

### 9.6 Plan, node, ownership, and contract schema

Each `PLAN.md` has an immutable contract section plus append-only status/receipt references.

```yaml
plan:
  schema_version: "1.0"
  plan_id: "uuid"
  task: "..."
  requested_depth: 5
  effective_depth: 4
  base_sha: "..."
  worktree: "..."
  max_parallel_workers: 3
  max_cost_usd: 2.00
  max_elapsed_seconds: 7200
  contract_digest: "sha256:..."
node:
  id: "1.2.1"
  type: "leaf|branch|root"
  purpose: "..."
  owns: ["src/a.py", "tests/test_a.py"]
  needs: ["1.1.2"]
  exports: ["InterfaceName", "schema:v1"]
  route_ref: "route-id"
  gates: "gates/leaf-1.2.1.md"
  state: "pending|ready|running|verifying|passed|blocked|cancelled"
  attempt: 0
```

Before any fan-out, freeze:

- exact owned production, test, migration, generated, and documentation paths;
- shared interfaces and exported symbols/schemas;
- data ownership and migration ordering;
- naming, error, logging, and compatibility conventions;
- dependency outputs a child may consume;
- allowed commands/tools and forbidden paths;
- leaf, branch, and root acceptance gates;
- contract digest.

Rules:

1. No two concurrently runnable nodes may own overlapping paths, parent/child directory wildcards, generated outputs, or migration ordering slots.
2. A shared file gets one integration-node owner. Workers propose an interface change through their return artifact rather than editing it.
3. The adapter checks the returned diff against `owns`. Out-of-contract changes fail verification and stop dependent dispatch.
4. A dirty or moving base invalidates the candidate receipt; rebase/replan and rebind gates before continuing.

### 9.7 Bounded rolling dispatch

The scheduler is a dependency-aware ready queue, not “launch N agents and hope.”

```text
validate plan + ownership + budget
while terminal root state not reached:
  mark pending nodes ready when every need is passed
  select ready nodes with no ownership collision
  reserve budget and slots
  dispatch up to min(plan cap, harness cap, budget cap)
  on each return:
    freeze candidate SHA/diff
    verify owned paths + leaf gates immediately
    pass -> record receipt; unlock dependants
    fail -> retry with named unmet gates or escalate
  when all children of a branch pass:
    integrate once; run branch gates once for that integration SHA
  trip circuit breaker on drift, collision, hard failure, privacy violation, cap, or cancellation
run strict root gates in clean verifier context
```

Defaults and bounds:

- Default active workers: `3`; the driver is not counted as a worker. Adapter may lower but never exceed the user/repo/harness cap.
- Default leaf attempts: `2` (initial plus one targeted repair). A third attempt requires an explicit escalation receipt and stronger tier, not an unbounded loop.
- Verify each leaf on return; do not wait for an entire wave.
- Dispatch newly unblocked work immediately if capacity remains.
- Stop launching new work when 80% of run budget or deadline is reserved; allow running nodes to return, then reassess.
- Cancel dependants when a hard dependency is blocked.
- Branch/root checks run once per distinct integration SHA and check digest; cache is invalidated by relevant file or command changes.

### 9.8 Gate format and enforcement

Retain the public Markdown shape so upstream plans remain legible:

```markdown
- [ ] G1: <observable outcome>
  CHECK: <repository-owned command>
  EXIT: 0
  EXPECT: <substring or /regex/>
  TIMEOUT: 60
  EVIDENCE: pending
```

Nexus rules tighten behavior:

- Success requires an allowed exit code **and** `EXPECT` when present. Matching text cannot override a failing process.
- Capture command digest, cwd, base/candidate SHA, environment allow-list digest, timestamp, exit code, bounded stdout/stderr digest, and runner version.
- Full command output stays in an artifact; Markdown stores a safe summary and receipt pointer.
- Redact secrets and upstream response bodies before user-facing storage.
- `--status` is read-only and never counts as re-verification.
- Leaf gates check leaf-local outcomes. Cross-leaf/shared checks belong to branch/root gates and run once per integration SHA.
- Shared checks use a stable command+cwd+environment+input digest, not matching text labels.
- `ABANDON: G1 <reason>` is recorded but makes strict root result `partial|blocked`.
- A public-compatible checker exit `0/1/2` may remain for tooling compatibility, but strict orchestration separately requires `failed=0`, `pending=0`, `abandoned=0`, and `runner_errors=0`.
- Gate files and checks must originate inside the trusted repository and be diff-reviewed before execution.
- If a Nexus-owned `--jobs N` mode is built, default `N=1`, cap it, de-duplicate shared commands, preserve deterministic output order, and test failure/timeout/signal behavior. Do not treat the screenshot’s untested private rewrite as an implementation.

### 9.9 User flow

1. User asks normal work or invokes `/unlazy tree 5 <task>`.
2. `model-router` silently handles obvious inline work or emits a visible one-line routing receipt for delegated work.
3. `unlazy` displays requested/effective depth, leaf count, active-worker cap, budget cap, high-risk/privacy constraints, and root completion gate.
4. Rolling execution reports only state changes: leaf started, verified, retried/escalated, branch integrated, circuit breaker, root passed/blocked.
5. Final report states exact SHA, passed/failed/abandoned gates, providers/models actually used, spend/quota evidence, and whether savings are measured or unknown.

### 9.10 Failure and rollback flow

- Invalid route/plan schema -> no dispatch; return actionable schema errors.
- Adapter cannot honor model/isolation/privacy contract -> route `bailout` or run inline at a safe higher tier; never silently weaken.
- Provider unavailable/rate-limited -> use only declared fallback ladder and receipt each attempt.
- Leaf gate failure -> one targeted repair with named gate evidence, then tier escalation or blocked node.
- Ownership collision/contract drift -> stop affected branch; do not merge around it.
- Budget/deadline cap -> stop new dispatch, verify returns, emit partial receipt.
- Root gate failure -> status remains incomplete even if every leaf agent claimed success.
- Rollback is feature-flag/config rollback to advisory/serial mode plus removal of hook registration. Existing provider router remains usable throughout.

## 10. Prompt pathway and UX requirements

### 10.1 Normalized pathway

```text
INTAKE
  -> deterministic inline/safety check
  -> model-router RouteDecision
  -> if inline: execute in current agent
  -> if delegate/fanout and substantial: unlazy plan/contract/gates
  -> adapter capability probe
  -> rolling dispatch
  -> independent verification
  -> root receipt
```

### 10.2 Router prompt template

```text
Classify only. Do not execute the task.

Task: {task}
Harness capabilities: {capability_probe}
Repository policy: {role_model_constraints}
Signals: {routing_signals_json}
Limits: {limits_json}

Return one RouteDecision JSON object conforming to schema {schema_version}.
Choose the smallest sufficient capability. Privacy and high-stakes floors override cost.
Use inline when delegation overhead exceeds the benefit.
Use bailout when the harness cannot honor the minimum contract.
Do not name a provider/model; provider resolution happens downstream.
```

### 10.3 Planner prompt template

```text
Plan only before implementation.

Task: {verbatim_task}
Requested tree depth: {requested_depth_or_auto}
Repository/base SHA: {repo}@{base_sha}
Constraints: {repo_instructions}
Root acceptance outcomes: {root_outcomes}

Choose the smallest natural effective depth. Every leaf must be a coherent deliverable,
have disjoint owned paths, declared dependencies/exports, a route request, and observable gates.
Move shared checks to branch/root gates. Freeze interfaces, data ownership, naming, errors,
and migration order before dispatch. Return a schema-valid PLAN plus gate files; write no product code.
```

### 10.4 Leaf prompt template

```text
You own leaf {leaf_id} only. You are not alone in the repository.

Purpose: {purpose}
Immutable contract digest: {contract_digest}
Owns: {owned_paths}
Needs/available exports: {dependency_exports}
Forbidden paths: every path not in Owns
Required route: {worker_role}/{quality_floor}, effort {reasoning_effort}
Gates (verbatim):
{leaf_gates}

Implement only this leaf. Do not redesign shared interfaces, dispatch other agents, weaken gates,
or edit outside Owns. Run the leaf checks and return: candidate SHA/diff, files changed, checks with
exit codes, unmet gates, contract questions, and no completion claim beyond this leaf.
```

### 10.5 Verifier prompt template

```text
Verify; do not repair.

Candidate: {candidate_sha}
Base: {base_sha}
Leaf/branch/root: {node_id}
Contract: {contract_and_owns}
Gates: {gates}
Claimed receipt: {worker_receipt}

First prove the candidate touched only owned paths. Rerun approved checks in the verifier context.
Require allowed exits, expected markers, no unhandled teardown/worker errors, and non-vacuous positive
or mutation controls. Return pass/fail/blocked with exact evidence. Do not accept agent summaries.
```

### 10.6 Interaction requirements

- Keep the user-facing route line compact: `fanout 3 | worker cheap | verifier mid | cap $X | privacy internal`.
- Explain only material escalations, degradation, spend-cap trips, contract changes, and terminal proof.
- User overrides may raise capability, lower concurrency, tighten privacy, or lower spend. A downward override below a safety floor is rejected with the governing signal.
- Never ask the user to choose among raw provider model IDs for a known task class.
- `tree N` errors state requested depth, effective depth, and why it changed.

## 11. Technical requirements

### 11.1 Cross-harness adapter contract

Every adapter implements:

```text
probe_capabilities() -> HarnessCapabilities
resolve(RouteDecision) -> ResolvedRoute
dispatch(LeafPrompt, ResolvedRoute, IsolationSpec) -> RunHandle
poll/wait(RunHandle) -> WorkerReturn
cancel(RunHandle) -> CancelReceipt
collect_usage(RunHandle) -> UsageReceipt
```

`HarnessCapabilities` includes per-dispatch model override, effort override, subagents, maximum active agents, isolated worktrees, tool allow-list, structured output, lifecycle hooks, cancellation, usage/cost reporting, and exact-model reporting.

#### Claude Code adapter

- Keep the main session as driver; route only delegated workers.
- Use model-pinned workers only when the installed Claude runtime exposes a deterministic per-task model control.
- Install the optional Stop hook only through an idempotent project/global installer. The hook blocks premature turn stop but root completion still comes from strict gates.
- If model override is unavailable, use the current safe driver/worker model and record `model_override_honored=false`; do not pretend credits were saved.
- Use isolated worktrees for concurrent mutating leaves.

#### Codex adapter

- Keep the root as orchestrator. Use registered subagent roles/model/effort overrides only when the active Codex runtime exposes them.
- Enforce completion in the driver/scheduler because Claude Stop-hook semantics do not exist.
- Prefer isolated worktrees and exact task ownership. If only a shared workspace is available, allow concurrency only for proven disjoint paths and verify diffs on every return.
- If a requested lower-cost model is unavailable under the active account, continue at the smallest available safe tier or return `bailout`; receipt the substitution.

#### VS Code/OpenRouter adapter

- Treat “VS Code” as a host capability profile, not one assumed extension. Probe the installed agent/extension for per-request model selection, tool calling, structured JSON, cancellation, usage, and workspace isolation.
- Resolve quality floors through the current OpenRouter catalog/config and the existing provider client; record the exact underlying provider/model returned.
- If the extension cannot expose per-call selection or lifecycle control, operate advisory/serial or through the repo CLI helper; do not claim automatic routing/enforcement.
- Apply sensitivity/provider policy before any prompt leaves the machine.

### 11.2 Canonical file layout

Final names may adjust to current-main conventions, but ownership and SSOT boundaries are fixed:

```text
skills/model-router/
  SKILL.md                         # <=200 lines, autonomous plain technique
  references/
    routing-policy.md              # signals, floors, escalation
    route-decision-schema.md       # RoutingRequest/Decision/Receipt SSOT
    prompt-pathway.md              # router + harness pathway
    harness-adapters.md            # capability/degradation contracts

skills/unlazy/
  SKILL.md                         # <=200 lines, command skill
  references/
    method.md                      # natural-depth semantics
    plan-contract-schema.md        # plan/node/ownership SSOT
    gates.md                       # gate semantics
    orchestration.md               # rolling scheduler/circuit breakers
    prompt-templates.md            # planner/leaf/verifier/integrator

config/harness/model-routing.yaml  # capability->current role/tier mapping, caps, feature flags
app/server/task_routing.py          # deterministic task policy; no provider HTTP
app/server/routing_schema.py        # typed route/receipt contracts
swarm/unlazy_scheduler.py           # ready queue, reservations, state machine
scripts/model-route.py              # host-neutral JSON CLI
scripts/unlazy-plan.py              # plan/schema/lint CLI
scripts/unlazy-gate-check.mjs        # compatible strict checker, zero dependency
scripts/unlazy-stop-hook.mjs         # Claude-only optional hook, zero dependency
tests/test_task_routing.py
tests/test_routing_schema.py
tests/test_unlazy_scheduler.py
tests/test_unlazy_gate_check.py
tests/test_model_router_adapters.py
evals/golden/task_routing.yaml
evals/golden/unlazy_plans.yaml
```

Do not duplicate provider ladders in `task_routing.py` or skill references. `config/harness/model-routing.yaml` maps stable capability terms to existing role/tier APIs; `provider_router.py` resolves the exact provider/model.

### 11.3 Cost and credit telemetry

For every delegated attempt record:

- route/policy/plan/node/attempt IDs;
- requested and resolved lane/tier/effort/provider/model;
- model mapping/catalog snapshot digest and selection timestamp;
- input, output, reasoning, cached tokens where available;
- billed cost, marginal cost, subscription/quota/credit units, and explicit `unknown` fields;
- reservation, cap, actual spend, released amount, and fallback attempts;
- duration/latency and work/gate terminal outcome;
- base/candidate/verifier SHA and receipt links.

Controls:

1. Atomically reserve estimated maximum spend before dispatch; release the unused amount on terminal receipt.
2. Refuse new leaves when per-leaf, per-run, daily, or provider caps are reached.
3. Existing `check_ceiling()` becomes an enforced pre-dispatch gate for routed paid work, not only an informational helper.
4. Provider call success with missing usage remains `usage_unknown`, not `$0`.
5. Subscription paths record `billed_cost_usd=0` only when true, while quota/credit consumption stays a separate known/unknown measure.
6. Parallel cost is summed across workers; wall-clock improvement is reported separately.
7. “Saved” requires a declared baseline policy (normally all comparable leaves on the driver tier), the same root acceptance outcome, actual routed usage, and a timestamped price snapshot. Otherwise report routed cost only.

## 12. Security and privacy requirements

- Classify sensitivity before routing. Client/confidential prompts are local-only by default.
- Store no API keys, tokens, raw customer data, or full upstream error bodies in route/gate ledgers.
- Use environment key presence only; never read or print values during capability probes.
- Gate commands are arbitrary code. Execute only repository-owned, reviewed commands in an isolated worktree with explicit cwd, timeout, environment allow-list, and output cap.
- Workers receive least context: immutable contract, owned paths, dependency exports, and their gates. Do not send the entire conversation or unrelated repository secrets.
- Adapter model/provider substitutions may only preserve or raise the safety floor.
- Require independent security verification for auth, payment, privacy, secrets, network, permissions, migrations, and remote-data changes.
- Prevent prompt injection from source text from changing routing policy, owned paths, tools, caps, or gate commands.
- Protect ledgers against concurrent corruption with atomic append/replace and stable IDs.
- Bind every final receipt to candidate SHA, gate digest, runner version, and verifier identity.

## 13. Verification plan

### 13.1 Static and authoring gates

- Both skill `SKILL.md` files are at most 200 lines.
- Frontmatter matches the chosen archetype and contains no banned fields.
- Every branch-only reference is under `references/` and reached by a conditional context pointer.
- Canonical/projection drift check passes through the existing skill-sync workflow.
- One whole-folder deployment command projects `SKILL.md`, references, scripts, templates, and assets to each supported host; a fixture rooted under a path containing spaces passes.
- Existing `tests/test_skill_sync.py:103-139` path-with-spaces regressions pass before either new skill is promoted.
- Schema examples validate and no hard model ID appears in skill prose.

### 13.2 Unit and property tests

- Same request and policy snapshot produce the same deterministic decision.
- High-stakes or confidential signals can never route below their floor.
- `execution_location` and `quality_floor` compose: every confidential/client plus high-stakes combination returns `local_only + top` for worker/verifier or `bailout`.
- Low confidence and repeated comparable failures monotonically escalate capability/effort or bail out.
- Unsupported harness capabilities never render as honored.
- Plan DAG is acyclic; every dependency exists; terminal root is reachable.
- Concurrent ready sets never overlap owned paths, generated outputs, or migration slots.
- Budget reservations remain within leaf/run/daily caps under concurrent completion/failure.
- Gate pass requires allowed exit and expectation; timeout, signal, invalid regex, parse error, and teardown error fail closed.
- Abandoned gates can satisfy public-compatible status but can never satisfy strict root completion.
- Shared command de-duplication keys include command, cwd, environment, runner, and relevant input digest.

### 13.3 Routing golden-eval matrix

| Case | Signals | Expected action/role/tier | Required verifier |
|---|---|---|---|
| Rename sweep across disjoint owned files | deterministic, low stakes, high volume | `mechanical/fanout/worker/cheap` | `mid` |
| Generate fixtures from a frozen schema | deterministic, bounded | `mechanical/delegate/worker/cheap` | `mid` |
| Implement a known API handler plus tests | bounded production change | `bounded/delegate/worker/mid` | `mid` |
| Refactor payment module | payment, subsystem, dependencies | `high_stakes/fanout` only after `driver/top` plan; `senior/top` floor | `verifier/top`, independent |
| Ambiguous architecture decision | low determinism, high ambiguity | `deep/delegate/senior/top` | `top` |
| Security/auth review | high stakes, no mutation | `high_stakes/delegate/verifier/top` | independent second pass/root driver |
| Search/summarise public sources | gathering, public | `mechanical/fanout/worker/cheap`, non-mutating | source/format gate |
| Summarise client records | confidential | `bounded/delegate/worker/cheap + local_only`, non-mutating | privacy + output gate |
| Review confidential payment logic | confidential + payment | `high_stakes/delegate/senior/top + local_only`, or `bailout` if unavailable | independent `verifier/top + local_only` |
| Two failures on cheap worker | prior failure=2 | `bounded/delegate/worker/mid` or `bailout` | `mid` |
| Overlapping ownership | fanout requested, collision | no parallel dispatch | planner fixes contract |
| Tree 7 for 20-minute task | toy leaves | inline/solo; effective depth reduced | root gate |
| Host lacks model override | route asks `cheap` | safe inline/same-model/advisory with substitution receipt | normal verifier |
| Spend cap exhausted | any paid route | `bailout/partial`; no new dispatch | ledger consistency |

### 13.4 Scheduler/integration tests

- Ready leaves launch up to cap, not one-at-a-time.
- A return is verified immediately and newly unblocked work dispatches while unrelated leaves remain running.
- Failed dependency cancels only its dependants; independent branches continue within caps.
- Branch/root gates run once per integration SHA and rerun after relevant change.
- Concurrent receipts and cost reservations remain consistent under out-of-order return.
- Cancellation cleans active reservations and records a terminal receipt.
- Contract drift and out-of-owned-path diffs trip the circuit breaker before integration.

### 13.5 Adapter contract tests

Use fake adapters for deterministic CI, then one no-spend or capped smoke per available harness:

- Claude: model override honored/unavailable, Stop-hook loop guard, exact worktree, cancellation.
- Codex: subagent role/effort mapping, driver-enforced gates, shared-workspace refusal on overlap.
- VS Code/OpenRouter: capability probe, exact returned model/provider, malformed/empty/truncated response, 429/fallback, missing usage, privacy block.
- Provider seam: `closed_loop.py` and `nexus/store_factory.py` execute only through the canonical provider router; compatibility calls cannot perform direct provider HTTP.
- Receipt truthfulness: Claude dispatch passes the claimed model override, all enforcement callers pass a role, missing OpenRouter tokens remain unknown rather than zero, and client errors contain no raw upstream body.
- Deployment: whole skill folders land byte-for-byte on Claude, Codex, and the supported VS Code/CLI projection; update/remove operations are idempotent and paths containing spaces pass.

### 13.6 Mutation and positive controls

- Force a high-stakes request toward `cheap`; policy test must fail.
- Mutate confidential high-stakes routing to either remote execution or a floor below `top`; policy and golden tests must fail.
- Remove one dependency edge; DAG/root reachability test must fail.
- Add an out-of-owned-path edit; verifier must fail.
- Make a check print the expected word and exit non-zero; gate must fail.
- Introduce one `ABANDON`; strict root completion must fail.
- Disable actual dispatch while returning fake success; adapter E2E must fail on missing run/candidate receipt.
- Corrupt cost ledger/reservation; scheduler must stop paid fan-out rather than exceed cap.

### 13.7 Evidence required before declaring implementation done

- Exact candidate SHA and clean isolated worktree receipt.
- Repo Judge Report and skill-authoring checklist pass.
- Focused suites plus repository-required full test/import gates exit zero with no teardown/worker errors.
- Golden routing evals pass, including mutation controls.
- Three adapter contract suites pass; unsupported live capabilities are explicitly recorded.
- Demonstration run proves rolling dispatch with at least two concurrent ready leaves and no ownership collision.
- Demonstration root failure proves no success claim despite all leaf self-reports.
- Cost receipt reconciles provider usage or marks unknown fields honestly; no unproven savings claim.

## 14. Loop testing and stress testing

- DAGs: 1, 4, 16, and 64 leaves; chains, diamonds, wide fans, disconnected invalid graph, and cycle.
- Concurrency caps: 1, 2, 3, host cap lower than plan cap, and cap changed mid-run.
- Returns: instant, slow, out of order, duplicate, lost, malformed, cancelled, and late after cancellation.
- Providers: 401, 404 model drift, 429, timeout, empty 200, truncated content, missing usage, and all fallbacks exhausted.
- Files: exact overlap, parent/child overlap, generated-file collision, migration-order collision, symlink/path traversal, and dirty base.
- Budgets: simultaneous reservations at boundary, missing costs, negative/invalid usage, daily cap, and partial release.
- Gates: large output, secret-shaped output, regex error, non-zero with expected string, hanging child process, teardown failure, shared-check duplicate, changed command digest.
- Hooks: six no-progress stops, content-only gate edits, hook unavailable, hook state corruption, and cwd mismatch; none may create a false root pass.
- Routing: adversarial prompt asking to ignore privacy/tier floors; embedded source text attempting to change tools/ownership; repeated failure escalation.

## 15. Acceptance criteria

- [ ] Repo `$judge` report passes against current implementation scope before build begins.
- [ ] `model-router` and `unlazy` are separate canonical skills with the declared archetypes; both pass the complete skill-authoring checklist.
- [ ] `model-router` emits schema-valid, deterministic decisions and names no provider/model in policy output.
- [ ] Privacy location and quality are orthogonal: confidential/client high-stakes routes prove `local_only + top` worker/verifier or fail closed with `bailout`.
- [ ] `unlazy` records requested/effective depth, uses natural leaves, and produces a valid acyclic dependency/ownership plan before implementation.
- [ ] Existing `model_policy` and `provider_router` remain the model/provider enforcement path; no third provider ladder is introduced.
- [ ] The two production `swarm.model_router` consumers are routed through the canonical provider seam, with compatibility behavior covered and no duplicated provider HTTP reachable from them.
- [ ] Whole-folder host-aware deployment covers Claude, Codex, and VS Code/CLI projections, including references/scripts/templates and external-drive paths containing spaces.
- [ ] Claimed model, role enforcement, token usage, cost unknowns, and redacted errors are proven truthful by positive and negative controls.
- [ ] Claude, Codex, and VS Code/OpenRouter adapters pass the common contract and truthfully record unsupported controls.
- [ ] Rolling dispatch starts all safe ready leaves up to the cap, verifies each return immediately, and dispatches newly unblocked leaves without lockstep waiting.
- [ ] No concurrent nodes overlap ownership, shared outputs, or migration order; an injected collision stops dispatch.
- [ ] Leaf, branch, and root gates are bound to exact SHAs and require allowed exits plus expectations; injected false-greens fail.
- [ ] `ABANDON`, missing evidence, runner errors, teardown errors, or root gate failures cannot produce `passed`.
- [ ] Per-leaf/per-run/daily budget reservations are enforced before paid dispatch and reconcile after every terminal attempt.
- [ ] Receipts record exact provider/model, usage/cost/quota knowns and unknowns, fallback, latency, SHA, gates, and verifier.
- [ ] A savings claim is produced only for comparable root-gate outcomes against a declared baseline and timestamped price snapshot.
- [ ] Confidential/client fixture data never reaches a remote adapter in tests.
- [ ] Shadow mode completes without unauthorized mutations, cap breaches, false completion, or secret leakage before enforcement is enabled.
- [ ] Rollback to advisory/serial mode is documented and proven without changing existing provider routing.

## 16. Goal command

Run only after scope approval, a current exact-main refresh, and the mandatory Judge gate:

```text
/goal Build the Nexus model-router and unlazy skills plus shared schemas, rolling scheduler, three harness adapters, strict gates, and enforced cost receipts from a fresh isolated worktree. Do not stop until every acceptance criterion in .spm/2026-08-21-unlazy-model-router-scope.md is bound to exact-SHA evidence; never treat abandonment, missing usage, unsupported adapter controls, leaf self-reports, or private-video claims as proof.
```

## 17. Implementation sequence, migration, and rollout

### Phase 0: Rebind and inventory

1. Fetch current `origin/main`; create an isolated external-storage worktree and record exact SHA.
2. Run repo Judge and inspect nearest instructions.
3. Inventory all call sites of `model_policy`, `provider_router`, `swarm/model_router`, Tier-0, budget tracker, and skill projections; pin the two current executable consumers.
4. Reproduce the focused routing/deployment test baseline, including the two `tests/test_skill_sync.py` external-path failures.
5. Write RED controls for canonical provider execution, claimed-model override, required role, missing-token unknowns, redacted errors, whole-folder deployment, and paths containing spaces.
6. Refresh current primary provider/model capability, price, context, tool, data-use, and availability facts; store a versioned snapshot.
7. Freeze route schema, vocabulary, safety floors, and feature flags.

**Gate:** no policy contradiction, no stale hard model mapping in skill prose, every legacy router call site classified, and the current deployment/path-space blockers have failing tests that prove the defect.

### Phase 1: Skills and schemas in shadow/read-only mode

1. Write RED golden evals and schema tests.
2. Create `model-router` and `unlazy` skill/reference structures under the authoring standard.
3. Implement route/plan/receipt schemas and deterministic policy CLI.
4. Replace split installation with a host-aware whole-folder projection, then add canonical skill projections through that path.
5. Fix the path-with-spaces approval parser and prove it on `/Volumes/Storage Unit/...` fixtures.

**Gate:** checklist clean; golden decisions and full-folder projection checks pass on all three host profiles; the focused `skill_sync` suite is green; no dispatch or provider traffic.

### Phase 2: Strict planning and gates, serial execution

1. Implement tree normalization, plan lint, ownership collision detection, gate parser/runner, and exact-SHA evidence.
2. Run `unlazy` serially (`max_parallel_workers=1`) through fake adapters.
3. Add Claude Stop hook as optional guard, not completion authority.

**Gate:** false-green mutations fail; serial root pass/fail/abandon behavior is truthful.

### Phase 3: Adapters and cost enforcement

1. Implement common adapter interface and capability probes.
2. Add Claude, Codex, and VS Code/OpenRouter adapters with safe degradation.
3. Extend cost ledger with reservations, caps, exact route receipts, and usage unknowns.
4. Integrate quality-floor translation with existing provider/model policy.
5. Migrate `swarm/closed_loop.py` and `swarm/nexus/store_factory.py` behind `provider_router.py` compatibility and remove their reachable direct-provider path.
6. Correct model-override, role, token-usage, and redacted-error receipts before enabling entitlement/cost optimization.

**Gate:** adapter contract suites green; privacy, downgrade, cap, and missing-usage tests fail closed.

### Phase 4: Rolling dispatch in shadow mode

1. Implement ready queue, immediate return verification, dependency unlock, branch integration, cancellation, and circuit breakers.
2. Replay representative stored tasks with fake providers and no product mutation.
3. Run capped live smoke only where current account/harness capability is proven.
4. Compare proposed routes with existing execution without controlling production work.

**Gate:** measured parallelism, zero ownership collisions/cap breaches/false passes, and exact receipts.

### Phase 5: Controlled enforcement

1. Enable for low-risk gathering/mechanical leaves first.
2. Expand to bounded implementation after a defined shadow sample meets routing accuracy and root-gate criteria.
3. Keep auth/payment/security/release work at current strong policy until independent data supports any change.
4. Review route quality, fallback, latency, cap, and comparable-cost metrics weekly.

**Rollback:** one feature flag returns to advisory decisions and serial execution; remove hook registration idempotently; existing provider router continues unchanged.

### Legacy migration rule

Do not remove `swarm/model_router.py` in this delivery. Put its callers behind the canonical capability translation where practical, mark remaining calls in a migration ledger, and schedule deletion only after parity tests, zero-call evidence, and an exact-main review. This prevents a “consolidation” refactor from expanding the first delivery beyond the two skills and adapters.

## 18. Session handoff seed

- Start from a fresh external-storage worktree at current `origin/main`.
- Read this scope, the research note, repo instructions, and skill-authoring standard before writing any skill.
- Run `$judge` first; attach its report.
- First code move is RED schema/golden tests, not provider integration.
- Preserve `model_policy.py` role ceilings and use `provider_router.py` as the provider SSOT.
- Treat the private video patch as requirements evidence only.
- Keep implementation feature-flagged, shadow-first, and serial until strict gates pass.
- First completion proof to build: an injected expected-string/non-zero check must fail and block root success.

## 19. Final recommendation and explicit risks

Proceed with the two-skill architecture. It is the smallest design that separates “who should do this?” from “how do we decompose and prove this?” while reusing the provider machinery already on exact main.

| Risk | Failure if ignored | Mitigation/gate |
|---|---|---|
| Private/public source conflation | Claims nonexistent tested scheduler/`--jobs` code. | Clean-room implementation, pinned provenance, no private code claim. |
| Third router vocabulary | More drift between role, capability, provider, and model. | Canonical translation into existing provider/model policy; no new ladder. |
| Stale model IDs/prices | Wrong cost/quality route or unavailable model. | Runtime/current snapshot, versioned config, exact resolved receipt. |
| Cheap-classifier tax | Router call costs more than it saves. | Deterministic rules first; classifier only for material ambiguity. |
| Quality regression disguised as savings | Lower cost because acceptance quality dropped. | Same root-gate outcome required for comparison; strong independent verifier. |
| Parallel write collision | Lost work or corrupt integration. | Isolated worktrees, exact `owns`, overlap lint, diff boundary gate. |
| False-green gate | Expected text masks process/test failure. | Allowed exit + expectation + teardown scan + mutation controls. |
| Stop-hook overclaim | Turn continues but work is still incomplete. | Hook is guard only; strict exact-SHA root gates decide. |
| `ABANDON` overclaim | Blocked work reported shipped. | Abandon always partial/blocked in strict result. |
| Privacy leakage | Client/internal data sent to training/free provider. | Sensitivity first, local-only default, adapter egress gate. |
| Subscription accounting fiction | `$0` marginal billed cost presented as zero resource use. | Separate billed, marginal, quota/credit, and unknown fields. |
| Cost-ledger race | Parallel workers overspend caps. | Atomic reservations and reconciliation before/after dispatch. |
| Harness capability mismatch | Model/effort/hook claim not actually honored. | Probe, safe degradation, `*_honored` receipt fields. |
| Orchestrator weakness | Cheap driver invalidates decomposition/integration. | Strong policy-allowed driver and root verifier remain fixed. |
| Over-decomposition | Context overhead and toy leaves create bloat. | Natural leaf minimum, effective-depth reduction, solo threshold. |
| Legacy migration blast radius | First delivery becomes a broad routing rewrite. | Compatibility layer and deferred deletion ledger. |

The design is ready for current-main Judge review and implementation sequencing. It is not yet approved, implemented, hosted, or production-proven.
