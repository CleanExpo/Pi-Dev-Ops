# Unlazy and model-routing research for the Nexus agent stack

**Date:** 2026-08-21
**Scope:** Research only. This note examines the public `Leonxlnx/unlazy` repository, the linked AI LABS video and transcript, the supplied screenshots, and one related public Claude model-router implementation. It does not install a skill, modify a vault, or select current OpenRouter model IDs.

## Executive conclusion

Unlazy should be treated as a **completion and verification protocol**, not as a model router or a complete orchestration runtime.

The public repository gives us useful primitives:

- acceptance gates written before work;
- a machine-readable gate format with runnable checks and evidence;
- depth-based task decomposition;
- fresh-context leaf agents for large work;
- file-ownership contracts before fan-out;
- branch-level integration gates;
- a Claude Code-only Stop hook;
- a simple model-tiering principle: cheap models for mechanical leaves, strong models for design, integration, verification, and the driver.

It does **not** provide:

- a `tree N` parser or tree generator;
- an agent scheduler;
- rolling parallel dispatch;
- a `--jobs` gate runner;
- a model-router implementation;
- OpenRouter, VS Code, or Codex provider adapters;
- a cost ledger or proof of savings;
- worktree isolation;
- automated tests or CI for the shipped scripts.

The linked video demonstrates and describes a faster, parallelized variant, then recommends pairing it with a separate model-router. The presenter says that refined variant is available through the paid AI LABS Pro community. The public Unlazy repository at the pinned SHA does not contain the shown rolling scheduler, `Owns/Needs/Tier` plan schema, or `--jobs` checker. Those ideas are suitable inputs to our scope, but they are not public code we can adopt as-is.

The recommended Nexus design is therefore three-layered:

1. **Model-router policy:** classify the work and return a structured route decision expressed in capability tiers, not hard-coded vendor model names.
2. **Unlazy execution contract:** convert substantial work into `PLAN.md` plus leaf and branch gates, and define what evidence closes each gate.
3. **Harness adapters:** translate a route decision into Claude Code, Codex, or VS Code/OpenRouter execution without changing the core policy.

This keeps cost policy, execution discipline, and provider mechanics separate. It also lets current model IDs and prices change without rewriting the skill.

---

## Evidence baseline

### Public Unlazy repository

- Repository: [`Leonxlnx/unlazy`](https://github.com/Leonxlnx/unlazy)
- Pinned main SHA reviewed: [`ed9e8d2b5919698cf2c54bda270d507e10b69617`](https://github.com/Leonxlnx/unlazy/commit/ed9e8d2b5919698cf2c54bda270d507e10b69617)
- Repository created: 2026-08-09; last code/docs push at the reviewed head: 2026-08-11.
- GitHub snapshot on 2026-08-21: 446 stars, 14 forks, one open issue, no tags exposed by the tags API, and no GitHub releases.
- Licence: [MIT](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/LICENSE#L1-L21).
- Runtime claim: Markdown plus zero-dependency Node 16+ scripts; hard Stop-hook enforcement is Claude Code-only ([README lines 13-14](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/README.md#L13-L14), [README lines 157-176](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/README.md#L157-L176)).

### Linked video

- Title: [“GitHub's #1 Trending Author's New Claude Skill Is Insane”](https://www.youtube.com/watch?v=c47uqR7XB_c)
- Channel: AI LABS
- Published: 2026-08-20
- Duration: 12:54
- YouTube ID: `c47uqR7XB_c`
- The title exactly matches the item the user asked to locate in the Obsidian source connection. It is the linked YouTube item, not a separate public article found during this research.
- Evidence used below comes from the video's first-party description and its English automatic captions. Timestamp links are included. Automatic captions can mis-hear product names, so repository source wins on code semantics.

---

## 1. Exact public commands and what they really mean

### Invocation examples

The public README gives these two examples ([README lines 22-34](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/README.md#L22-L34)):

```text
/unlazy tree 5 refactor the payment module
```

```text
tree 3 build the landing page and do not stop until every gate is checked
```

`/unlazy` and `tree N` are **prompt/skill triggers**, not executable commands implemented by a parser in this repository. The repository contains one `SKILL.md`, references, templates, and three Node scripts. No CLI handles `tree N`; the active model is expected to interpret the instruction and author the plan and gates.

### Installation

The documented cross-agent install is ([README lines 36-58](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/README.md#L36-L58)):

```bash
npx skills add Leonxlnx/unlazy
```

The README says `-g` installs at user level and `--all` targets every detected agent. Manual locations are:

```bash
git clone https://github.com/Leonxlnx/unlazy ~/.claude/skills/unlazy
git clone https://github.com/Leonxlnx/unlazy ~/.codex/skills/unlazy
```

This confirms format portability, not equivalent enforcement. Claude Code can use the Stop hook. Other hosts receive Markdown discipline plus the Node checker only.

### Gate checker

Documented usage is defined directly in [`scripts/gate-check.mjs` lines 5-12](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/scripts/gate-check.mjs#L5-L12):

```bash
node <skill-dir>/scripts/gate-check.mjs [file ...]
node <skill-dir>/scripts/gate-check.mjs --status [file ...]
node <skill-dir>/scripts/gate-check.mjs --timeout 60 [file ...]
```

With no file arguments, it reads `GATES.md` and every Markdown file immediately under `gates/` in the current directory ([lines 25-42](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/scripts/gate-check.mjs#L25-L42)). Exit codes are:

- `0`: all gates are met or abandoned;
- `1`: unmet gates remain;
- `2`: no gate files, unreadable input, usage, or parse-level failure.

The checker is sequential. There is no public `--jobs` flag. It runs only gates that are unchecked or have pending evidence, and only when they have a `CHECK:` command ([lines 111-153](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/scripts/gate-check.mjs#L111-L153)). `--status` is read-only and executes no checks.

### Stop-hook installer

The public installer supports ([`install-hooks.mjs` lines 4-12](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/scripts/install-hooks.mjs#L4-L12)):

```bash
node <skill-dir>/scripts/install-hooks.mjs
node <skill-dir>/scripts/install-hooks.mjs --shared
node <skill-dir>/scripts/install-hooks.mjs --global
node <skill-dir>/scripts/install-hooks.mjs --uninstall
```

Default installation writes to the current project's `.claude/settings.local.json`; `--shared` uses `.claude/settings.json`; `--global` uses `~/.claude/settings.json`. The installer is idempotent and refuses to overwrite invalid JSON ([lines 27-78](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/scripts/install-hooks.mjs#L27-L78)).

---

## 2. Depth Tree semantics

The current v2 method explicitly rejects the v1 claim that effort multiplies as `2^(N-1)`. The author's six-run test found tree 6 cost roughly 1.0-1.5 times tree 3, so v2 treats depth as decomposition, not a spend or effort multiplier ([`references/method.md` lines 1-12](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/method.md#L1-L12)).

The operative rules are:

1. Layer 1 is the original task. Split at natural joints, binary only where natural. Leaves are work; internal nodes are decomposition and integration.
2. A leaf must be one coherent deliverable worth at least ten minutes of focused work with one gates file. If leaves become smaller, reduce depth.
3. Freeze interfaces, data ownership, naming, and error conventions in `PLAN.md` before fan-out.
4. No two leaves may own the same file. A shared file means the split is wrong or the shared surface belongs in the contract.
5. Leaves have delivery gates; internal branches have integration gates.
6. A leaf finishes only after its gates have evidence and a full improvement pass finds nothing more to improve.

These rules are in [`references/method.md` lines 14-40](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/method.md#L14-L40).

The scale guidance is ([method lines 51-64](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/method.md#L51-L64)):

- **tree 2-3:** feature, bug hunt, or document; solo mode; one gates file; two to four leaves worked sequentially in one session.
- **tree 4-5:** subsystem, refactor, or serious review; consider orchestration; the method warns that 8-16 leaves exceed what one context handles well.
- **tree 6-7:** whole project; orchestrated, disjoint work units, parallel where supported, integration gates at merge points.
- **No depth supplied:** choose the smallest depth whose leaves match natural task joints.

### Video discrepancy

The video says a depth that creates sub-ten-minute tasks is automatically lowered to a default of three ([06:24-06:58](https://www.youtube.com/watch?v=c47uqR7XB_c&t=384s)). The public repository does not implement automatic depth calculation, and the written method says to back off a layer or choose the smallest natural depth, not always reset to three. For implementation, use the repository's natural-leaf rule and make the planner's chosen depth explicit and reviewable.

---

## 3. Gates and evidence architecture

The gate contract is deliberately plain Markdown ([`references/gates.md` lines 7-34](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/gates.md#L7-L34)):

```markdown
- [ ] G1: <observable outcome>
  CHECK: <shell command>
  EXPECT: <substring or /regex/>
  EVIDENCE: pending

ABANDON: G1 <reason>
```

Semantics verified from the parser and runner:

- A checked box with missing or `pending` evidence is still unmet.
- `EXPECT:` is a substring match unless wrapped as a JavaScript regex.
- `ABANDON: <id> <reason>` treats the gate as resolved and must be surfaced in the final report.
- Passing a runnable check flips the checkbox and stores at most the final two non-empty output lines, capped at 200 characters ([`gate-check.mjs` lines 79-90](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/scripts/gate-check.mjs#L79-L90)).
- Recommended gate density is five to twelve outcomes per leaf ([`references/gates.md` lines 46-59](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/gates.md#L46-L59)).
- Every number intended for the final report should have a measurement gate ([lines 61-66](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/gates.md#L61-L66)).

### Important checker constraints for adoption

1. **`EXPECT` can override a failing exit code.** When `EXPECT:` exists, a matching output string decides success even if the command exits non-zero ([`gate-check.mjs` lines 120-128](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/scripts/gate-check.mjs#L120-L128)). Nexus should require both an acceptable process exit status and the expected success marker unless a gate explicitly declares another rule.
2. **Checks are arbitrary shell commands.** Importing a gates file from an untrusted source and running it is code execution. Gate creation and modification must remain inside the trusted repository boundary and be diff-reviewable.
3. **`--status` does not re-run checks.** The orchestration reference tells the parent to use `--status` and then spot-check commands ([`references/orchestration.md` lines 20-24](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/orchestration.md#L20-L24)). A production verifier must actually execute the leaf's full approved check set in a clean environment; ledger inspection alone is not re-verification.
4. **Bare invocation scans the whole gate directory.** For a large tree this can repeatedly traverse unrelated leaf and branch ledgers. The public checker has no changed-scope selection or shared-check de-duplication.
5. **No cryptographic binding.** Evidence is text written back into Markdown; it is not bound to a commit SHA, command digest, environment, or timestamp. Nexus release claims should bind evidence to the exact commit and run identity.

---

## 4. Public orchestration architecture

The public driver contract is explicit: the main session plans, dispatches, verifies, and integrates; it does not implement the leaves ([`references/orchestration.md` lines 7-14](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/orchestration.md#L7-L14)).

The shipped prose describes this loop:

1. Write `PLAN.md` with the contract, tree, and one gate file per leaf and branch.
2. Dispatch **one leaf** with only the contract section, that leaf's gates verbatim, and the four-pass completion instruction.
3. On return, inspect the ledger and re-run checks; send the leaf back with named unmet gates when needed.
4. Append status, then dispatch the next leaf.
5. When children are complete, run branch integration gates.
6. Report only after root gates close.

Source: [`references/orchestration.md` lines 12-29](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/orchestration.md#L12-L29).

Parallelism is permitted for leaves with disjoint file ownership, but the repository supplies no scheduler. The reference correctly notes that parallelism saves wall-clock time, not tokens, and that shared ownership requires fixing the plan rather than hoping agents coordinate ([lines 31-37](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/orchestration.md#L31-L37)).

The plan template contains only the contract, a static tree, and an append-only status log ([`templates/PLAN.md`](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/templates/PLAN.md)). It has no dependency DAG, ready queue, concurrency cap, tier field, retry state, or provider/model receipt.

### The video's parallel refinement

At [10:27](https://www.youtube.com/watch?v=c47uqR7XB_c&t=627s), the presenter reports that the original one-leaf-at-a-time flow ran for three to four hours and produced only a login page. The presenter attributes the delay to lockstep dispatch. The supplied video frame shows the prompt used to request a refactor:

- launch all ready leaves at once;
- verify each leaf when it returns;
- dispatch newly unblocked leaves;
- add `Owns`, `Needs`, and `Tier` per leaf plus a dispatch schedule to `PLAN.md`;
- keep leaf gates leaf-local;
- move whole-project checks to branch gates and run them once;
- hand model-tier prose to a separate `model-router`;
- retain the gate format, exit codes, Stop-hook compatibility, zero dependencies, and existing voice.

The presenter then claims ten agents ran concurrently and completed a first demo app in nearly two hours ([12:01-12:13](https://www.youtube.com/watch?v=c47uqR7XB_c&t=721s)). No public code, fixture, run log, commit, cost receipt, or demo repository was linked for this modified variant. Treat the timing and completeness claims as first-party testimony, not reproducible evidence.

The screenshot also says `gate-check.mjs` was already rewritten with `--jobs`, shared checks, and `jobs: 1` but still needed testing. That rewrite is not present in public Unlazy main at the pinned SHA.

---

## 5. Stop-hook behavior

The optional Stop hook scans gate files in the payload's current working directory and blocks a Claude Code stop when any gate is unchecked or has pending evidence ([`stop-hook.mjs` lines 36-91](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/scripts/stop-hook.mjs#L36-L91)).

Its release behavior is intentionally permissive:

- gate-file content is hashed;
- any content change resets the no-progress counter;
- stops 1 through 6 without gate progress are blocked;
- the next stop is allowed with a warning;
- an `ABANDON:` line resolves a named gate;
- state is stored in `.unlazy-hook-state.json` beside the gates.

Source: [`stop-hook.mjs` lines 93-115](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/scripts/stop-hook.mjs#L93-L115).

Adoption implications:

- This is a **turn-stop guard**, not a proof that work is complete.
- It is Claude Code-specific. Codex, VS Code/OpenRouter agents, and other harnesses need equivalent native lifecycle enforcement or must operate with advisory discipline only.
- Any gate-file edit counts as progress, even if it does not close a gate.
- `ABANDON` is deliberately easy; policy must distinguish an honest blocked handoff from successful completion.
- The hook only scans the current directory's `GATES.md` and immediate `gates/*.md`, so worktree and working-directory discipline matter.

---

## 6. What Unlazy actually says about model routing

Unlazy contains a policy fragment, not a router:

- Mechanical leaves such as rename sweeps, fixture generation, and applying a decided pattern may go to a cheaper model or lower reasoning effort.
- Design leaves, integration branches, and every verification pass stay on a strong model.
- The driver remains on a strong model because a weak driver invalidates higher-level verification.

Source: [`references/orchestration.md` lines 57-64](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/orchestration.md#L57-L64).

The token-economy reference adds four useful rules ([`references/token-economy.md`](https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/token-economy.md)):

- use shell checks instead of model re-reading;
- give each leaf only the contract and its gates;
- append status instead of rewriting the plan, preserving stable prompt-cache prefixes;
- do not orchestrate work below roughly half an hour because context setup costs more than it buys.

At [12:15](https://www.youtube.com/watch?v=c47uqR7XB_c&t=735s), the video recommends a separate model-router that sends simple mechanical work to a cheaper model and hard work to a strong model to reduce limit consumption. It does not disclose an executable OpenRouter mapping or measurable routing benchmark.

### Supplied model-router screenshot

The supplied screenshot shows a `model-router` skill description that says it should:

- be consulted before every substantive request;
- route well-specified mechanical work down;
- escalate architecture, deep debugging, and security reasoning;
- fan independent work across parallel subagents;
- trigger without requiring the user to mention models, speed, cost, or subagents.

This is useful policy language. It is not sufficient as an implementation because it lacks a structured decision schema, provider adapters, an abstain/inline path, routing receipts, failure escalation, and live model/cost discovery.

### Related public Claude-only router

A separate public project, [`TyRobbins/claude-model-router`](https://github.com/TyRobbins/claude-model-router), implements a similar four-tier policy. I did not find evidence proving it is the same artifact shown in the video, so it should be treated as an independent reference.

At pinned SHA [`91ea2651bbe49f8b3263281d91f07f70e09c8c85`](https://github.com/TyRobbins/claude-model-router/commit/91ea2651bbe49f8b3263281d91f07f70e09c8c85), it provides:

- Fast/Haiku for deterministic, mechanical, high-volume work;
- Balanced/Sonnet as the default for bounded implementation, tests, review, and routine debugging;
- Deep/Opus for architecture, ambiguous specifications, subtle root-cause debugging, and high-stakes work;
- Frontier/Fable for only the largest or longest autonomous work;
- six routing signals: determinism, scope, reasoning depth, stakes, volume/latency, and prior failure;
- deliberate escalation when a lower tier stalls or uncertainty/stakes rise;
- model-pinned Claude subagents for interactive sessions;
- a headless Python script that uses a Haiku classification call and then runs `claude -p --model <tier>`.

Sources: [`SKILL.md` lines 23-112](https://github.com/TyRobbins/claude-model-router/blob/91ea2651bbe49f8b3263281d91f07f70e09c8c85/skills/model-router/SKILL.md#L23-L112), [`README.md` lines 14-40](https://github.com/TyRobbins/claude-model-router/blob/91ea2651bbe49f8b3263281d91f07f70e09c8c85/README.md#L14-L40), and [`README.md` lines 96-118](https://github.com/TyRobbins/claude-model-router/blob/91ea2651bbe49f8b3263281d91f07f70e09c8c85/README.md#L96-L118).

Constraints:

- Claude Code/Anthropic only; no OpenRouter or Codex adapter.
- Interactive routing changes delegated workers, not the already-running main model.
- Auto-delegation is heuristic; explicit worker mention is the deterministic lever.
- The headless path spends one model call on classification before the work call.
- It hard-codes a then-current Frontier model ID while using aliases for lower tiers.
- The repository is MIT but very early: created 2026-06-09, two releases, and one GitHub star at the research snapshot.

Reuse the signal taxonomy and escalation idea, not the provider-specific identifiers.

---

## 7. Recommended scope for Nexus skills

### A. `model-router` core policy

Consult it on substantive work, but allow a zero-delegation result. It should return a small structured decision rather than prose alone:

```yaml
route:
  action: inline | delegate | fanout
  task_class: mechanical | bounded_implementation | deep_reasoning | high_stakes | long_horizon
  capability_tier: fast | balanced | deep | frontier
  reasoning_effort: low | medium | high
  confidence: 0.0-1.0
  reasons: []
  escalation_on: []
  verifier_tier: balanced | deep
```

Required signals:

- determinism and ambiguity;
- scope and dependency count;
- reasoning depth;
- stakes, especially auth, payments, privacy, legal, and security;
- volume and latency sensitivity;
- context size and expected duration;
- tool/modality requirements;
- prior model failure or low confidence;
- whether subparts have disjoint ownership and can safely run concurrently.

The core policy should name capability tiers only. A versioned provider configuration resolves those tiers to current Claude, Codex, or OpenRouter model IDs at runtime.

### B. `unlazy-orchestrator` execution policy

Use Unlazy only for substantial work:

- default solo mode for work below roughly 30 minutes or tree 3 and under;
- orchestrated mode for tree 4+, multi-sitting builds, or clearly independent workstreams;
- choose depth by natural leaf size, not by a promised effort multiplier;
- write gates before implementation;
- bind evidence to exact commit/worktree/run identity;
- keep leaf checks leaf-local;
- place cross-leaf and whole-project checks at branch/root nodes;
- require all root gates before a completion claim;
- surface abandonment as blocked/partial, never as success.

### C. Rolling scheduler

Extend `PLAN.md` with machine-readable leaf metadata:

```yaml
leaf:
  id: 1.2.1
  owns: [path/a, path/b]
  needs: [1.1.2]
  tier: balanced
  gates: gates/leaf-1.2.1.md
  state: pending | ready | running | verifying | passed | blocked
```

Scheduler rules:

1. Dispatch all ready leaves up to a configurable concurrency cap.
2. Never concurrently dispatch overlapping `owns` paths.
3. Give each leaf only the fixed contract, owned paths, dependencies' exported interfaces, and its own gates.
4. Verify a returned leaf immediately in the parent environment.
5. Record the exact model/provider, run ID, commit, gate results, duration, and usage/cost receipt.
6. Dispatch newly unblocked leaves without waiting for unrelated running leaves.
7. Run branch/root gates once per relevant integration state, not once per leaf.
8. Stop dispatch on contract drift, shared-file collision, hard gate failure, or spend/concurrency cap.

### D. Harness adapters

- **Claude Code:** model-pinned workers plus native Stop/PreTool hooks where available.
- **Codex:** native subagent model selection and Codex-specific completion enforcement; do not assume Claude hook semantics.
- **VS Code/OpenRouter:** resolve capability tiers through a current, configurable OpenRouter catalogue; record the exact provider and model actually selected because aliases and provider availability can drift.

OpenRouter model names, context limits, prices, tool support, and availability must be refreshed from current primary documentation during implementation. They were deliberately not frozen into this research note.

### E. Cost and credit controls

The lowest-cost safe routing pathway is:

1. deterministic local heuristics for obvious mechanical/inline cases;
2. optional cheap classifier only for ambiguous routing;
3. smallest sufficient worker tier;
4. strong driver and verifier for integration and high-stakes gates;
5. escalate only on named failure/uncertainty signals;
6. hard per-leaf and per-run spend caps;
7. route and usage ledger so savings are measured against an explicit baseline.

Parallelism is a latency optimization, not a token-saving claim. Any report that claims savings must compare actual routed usage and cost with the declared baseline at the same acceptance-gate outcome.

---

## 8. Adoption and licence constraints

### Safe to reuse

- Unlazy's MIT licence permits use, modification, distribution, sublicensing, and commercial adoption as long as the copyright and licence notice are retained.
- Its Markdown gate format and zero-dependency scripts are small enough to audit.
- The leaf/branch gate separation and driver/worker verification hierarchy fit existing Nexus completion goals.

### Do not adopt blindly

- The repository is days old at the evidence date and has no formal release, tag, automated test suite, or CI workflow.
- `CONTRIBUTING.md` asks maintainers to exercise script paths manually rather than providing committed tests.
- The GitHub repository description still states the retired v1 `2^(N-1)` effort-multiplication claim, while main's README and method explicitly reject it. Use pinned source files, not the repository summary.
- Gate checks execute arbitrary shell commands.
- The public parent verification recipe is not a clean full rerun.
- The Stop hook is Claude-only and intentionally releases after repeated no-progress stops.
- The video's high-concurrency variant is unpublished and its performance/completeness claims are not independently reproducible.
- The related public model router is Claude-specific and does not satisfy the requested OpenRouter/VS Code/Codex portability.

The right adoption posture is **fork the concepts into Nexus-owned skills and adapters, retain MIT notices for copied material, add tests and receipts, and keep upstream pinned as evidence**. Do not install upstream globally as the production routing/control layer before those gaps are closed.

---

## 9. Evidence and uncertainty register

### Confirmed from public source at pinned SHA

- Gate-before-work rule and file format.
- Solo versus orchestrated threshold guidance.
- Depth Tree v2 natural-leaf semantics.
- Sequential public driver loop.
- Parallel permission only for disjoint ownership.
- Gate checker parsing, execution, evidence, and exit-code behavior.
- Claude Code Stop-hook behavior and installer targets.
- Mechanical-down / design-integration-verification-up tiering policy.
- MIT licence.

### Confirmed from first-party video/description, not public code

- AI LABS experienced a slow lockstep run and requested rolling parallel dispatch.
- The shown refactor prompt adds `Owns`, `Needs`, `Tier`, a dispatch schedule, leaf-local gates, and branch-level shared gates.
- The presenter claims ten concurrent agents and a roughly two-hour successful demo run.
- The presenter recommends pairing the workflow with a separate model-router.
- The presenter says the refined skill is in AI LABS Pro.

### Not confirmed

- The exact private skill files or their licence.
- The shown `--jobs` checker implementation or tests.
- The demo repository, exact acceptance gates, run logs, model mix, token usage, or cost.
- That the supplied model-router screenshot is the same project as `TyRobbins/claude-model-router`.
- Any current OpenRouter model-to-tier mapping or price advantage.
- The author's six-run Unlazy benchmark beyond the summary committed to the README; raw run artefacts are not in the reviewed repository tree.

### Source-transfer boundary

The requested Obsidian item is identifiable as the linked YouTube video. This research subtask did not access or mutate the user's Obsidian source connection, did not write to the 2nd Brain Wiki, and did not delete the source. Any later move should verify a destination receipt with matching title, URL, and content before source deletion.

---

## Primary sources

- Unlazy repository: https://github.com/Leonxlnx/unlazy
- Unlazy reviewed commit: https://github.com/Leonxlnx/unlazy/commit/ed9e8d2b5919698cf2c54bda270d507e10b69617
- Unlazy `SKILL.md`: https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/SKILL.md
- Depth Tree method: https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/method.md
- Gates specification: https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/gates.md
- Orchestration reference: https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/orchestration.md
- Token economy reference: https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/references/token-economy.md
- Gate checker: https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/scripts/gate-check.mjs
- Claude Stop hook: https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/scripts/stop-hook.mjs
- Hook installer: https://github.com/Leonxlnx/unlazy/blob/ed9e8d2b5919698cf2c54bda270d507e10b69617/scripts/install-hooks.mjs
- AI LABS video: https://www.youtube.com/watch?v=c47uqR7XB_c
- Related independent model-router reference: https://github.com/TyRobbins/claude-model-router
