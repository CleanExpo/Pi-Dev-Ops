---
name: senior-harness
description: Use before substantive project work that requires governed discovery, delegation, verification, or recovery from repeated failure.
allowed-tools: Read, Grep, Glob, LS, Bash
---

# Senior Harness

Put the control contract above the Lead LLM. The model may discover, propose, route, and report; it
may not expand authority, accept its own work, repeat a failed pathway, or promote a capability.

## Usage

In trusted Pi-Dev-Ops sessions, project lifecycle hooks run the setup driver before mediated local
tools. The first user prompt is frozen byte-for-byte as the primary objective; later prompts are
subordinate until a new task starts. The receipt binds the Git worktree, exact HEAD and dirty-state
digest, this driver, and the installed `senior-harness`, `model-router`, and `unlazy` skill folders.
It also executes the provider-neutral router and binds its `RoutingRequest` and `RouteDecision`, then
requires Unlazy as the downstream decomposition, gate, integration, and receipt controller.

For normal Codex and Claude delivery sessions, startup also binds a parallel-first orchestration
policy. Before the root performs implementation, load Unlazy, prove disjoint leaf ownership, admit
the delivery contract, and dispatch the independent leaves up to the four-worker cap. The root owns
coordination and final proof; bounded leaf and integration workers own every mutation. The lifecycle
hook denies root mutation tools throughout a parallel-required session. Grill interactions remain
locked and never receive an early dispatch instruction.

Install the same control stack into all three skill discovery roots with:

```bash
bash skills/senior-harness/scripts/install_senior_harness.sh
```

Add `--dry-run` to print the exact link plan without changing anything. The installer refuses to
replace a real directory and rolls every link back if any root fails, so a partial install cannot
leave the three roots on different control stacks.

This aligns `senior-harness`, `model-router`, and `unlazy` under `~/.codex/skills`,
`~/.claude/skills`, and `~/.agents/skills`. Codex and Claude have lifecycle-hook adapters; the
Agents root is discovery-only unless its host separately proves a lifecycle adapter.

Lifecycle hooks invoke `scripts/run_setup_driver.sh`. The runner prefers an explicit
`SENIOR_HARNESS_PYTHON`, then the canonical checkout's `.venv`, and uses ambient `python3` only when
it is version 3.10 or newer. If none is available, prompt submission and tool use fail closed.

Run the same driver explicitly from any Git project when hooks are unavailable or untrusted:

```bash
bash ~/.codex/skills/senior-harness/scripts/run_setup_driver.sh start \
  "<literal request>" --project "$(git rev-parse --show-toplevel)" --surface codex
```

Use `--surface claude` or `--surface vscode-openrouter` for the other hosts. Exit `0` plus a
`startup-admitted` JSON receipt proves deterministic startup only. It never grants mutation,
business, financial, privacy, deployment, or irreversible authority.

Explicit skill invocation also remains available when automatic triggering is uncertain:

```text
Codex:      $senior-harness <literal request>
Claude:     /senior-harness <literal request>
```

Locate the canonical source, then create the immutable intake envelope from any project:

```bash
python ~/.codex/skills/senior-harness/scripts/senior_harness.py where
python ~/.codex/skills/senior-harness/scripts/senior_harness.py intake "<literal request>" --horizon-required
```

Claude Code uses the same path under `~/.claude/skills/`. Do not assume the active project contains
Pi-Dev-Ops scripts.

Use `--horizon-required` for strategic, architectural, multi-project, product, or repeatedly stalled
work. Omit it for routine bounded work. Exit `0` plus valid JSON is an intake receipt, not execution
proof.

Project hooks cover normal trusted Codex/Claude lifecycle paths. Codex hosted or specialised tools,
Claude `--bare`/`--safe-mode`, disabled or untrusted project hooks, direct shells, and other hosts can
bypass them. Never claim universal interception; use the explicit driver and downstream scheduler
gate on those surfaces.

The hooks mechanically require a valid startup receipt before the first mediated local tool and keep
injecting the frozen objective afterward. In a `/grill-me` or `/grill-with-docs` interaction they
fail closed: only evidence discovery and the Grill state driver may run; edits, pushes, deploys, sends,
and worker dispatch are denied. Outside a Grill, existing host/repository policy still controls generic
mutations. `guard-dispatch` rejects every Grill delivery move until a confirmed shared-understanding
session is supplied and continues rejecting mutating moves until a trusted authority adapter exists.

Recovery is deliberately asymmetric. A missing or invalid session receipt may still admit exact,
read-only discovery tools such as `Read`, `Grep`, `Glob`, `ToolSearch`, web search, and the named
read-only Exa tools, with an explicit zero-authority warning. Mutation, provider, worker, browser
computer-use, send, and deploy tools remain denied. Installed Harness control digests are strict at
startup and the first tool. After a normal delivery session has admitted its first tool, later
Harness-code drift is surfaced as stale-control evidence rather than denying the whole session;
normal host and repository policy still decides generic tools, and a fresh session is required to
produce new control-code evidence. Grill interactions continue revalidating project and control
bytes on every tool, with recovery reads as the only carve-out.

Governed Grill-Me entry, and the authority its receipt withholds, is specified in [`references/grill-contract.md`](references/grill-contract.md).

## 1. Ground

Preserve the literal request verbatim. Inspect repository instructions, current state, project
history, authoritative connectors, conversations, skills, tests, and vendor sources before proposing
new machinery. Keep the current user instruction above portfolio goals. Record inferred outcomes with
provenance, confidence, and `authorization_status: proposal`.

**Complete when:** the literal request is the only automatically authorised scope, source coverage
and missing sources are visible, and every inference remains a proposal.

## 2. Horizon

For horizon-bearing work, create a linked graph of 15–20 meaningful state transitions, not a list of
predictions or filler research steps. Every move needs a state delta, owner, prerequisites, evidence,
confidence, counter-case, value, cost, reversibility, observable trigger, expiry, status, and authority.
Discovery may broaden topically, but each scan run remains bounded by a question, source/privacy
allowlist, spend, retention, value-of-information threshold, and stop condition.

The normative machine contract and lifecycle rules are in
[`references/control-contract.md`](references/control-contract.md); load them whenever creating,
validating, retrying, accepting, or promoting a Senior Harness task.

**Complete when:** the deterministic checker proves the graph is acyclic, structurally distinct,
within its node and branch limits, and has a longest state-bearing path of 15–20 moves when required;
an independent verifier has rejected semantic filler.

## 3. Admit

Keep Horizon advisory. It cannot dispatch, edit, spend, deploy, publish, migrate, delete, or accept.
Only evidence-backed moves inside the literal request may enter delivery automatically. Any inferred,
business, ethical, financial, privacy, or irreversible decision stays a proposal until existing policy
or the human grants the specific authority.

**Complete when:** every execution move names the authority it would require, remains a proposal until
an external trusted runtime authenticates that authority, and no Horizon move connects directly to
execution. Schema v1 deliberately cannot approve mutations from request text alone.

When Pi-CEO is the consumer, load
[`references/admission-enforcement.md`](references/admission-enforcement.md) before configuring,
issuing, consuming, resuming, restoring, or promoting an enforce-mode admission. Production stays
`off` or `observe` until the external signer, function-only database roles, dedicated consumer token,
public key ring, revocation route, and live accept/replay evidence all exist.

## 4. Route

Call `skill.model-router` for each admitted executable node and for its verifier. Translate capability
floors through existing provider seams; never add a model ladder here. Give the admitted dependency
tree, file ownership, gates, integration, and exact-candidate proof to `skill.unlazy`. In Claude Code,
use `/spm` as the terminal builder when its isolated pipeline and human gates apply. Reach canonical
specialists by logical skill ID; do not copy their prompts.

Use specialists deliberately:

- `judge` challenges a new build or architecture before implementation.
- `storm` gathers public evidence when repository evidence cannot answer the question.
- `wayfinder` maps genuinely foggy pathways; skip it for an already precise task.
- an independent technical arbiter resolves evidence conflicts after specialist experiments.

**Complete when:** every ready node has a schema-valid route, disjoint ownership or a single integration
owner, bounded parallelism, executable gates, and a verifier independent from its builder.

## 5. Break spin

Fingerprint the route decision, immutable input digest, problem, method, tool path, order-normalised
source set, and model class before dispatch. Record the hypothesis, but exclude its free-text wording
from the fingerprint so paraphrasing cannot create a new pathway:

```bash
python ~/.codex/skills/senior-harness/scripts/senior_harness.py bind-attempt CONTRACT.json ATTEMPT.json
```

The binding command derives the input digest and stable route handle from the frozen task, then emits
the fingerprint; caller-supplied relabels fail lint. Reject a repeated fingerprint before spending model work. After two distinct failed attempts on one
problem, or five minutes without new authoritative evidence, stop the pathway. Open an uncertainty
case, dispatch at least two independent specialists using materially different evidence or methods,
and give the evidence packet to an arbiter who is neither specialist. Only unresolved authority or
business decisions reach the human.

**Complete when:** the stopped route cannot dispatch again, new attempts differ materially, and the
uncertainty case names its specialists, arbiter, evidence, experiment, and resolution criterion.

## 6. Prove and learn

Validate the frozen candidate contract before execution and query admitted delivery work:

```bash
python ~/.codex/skills/senior-harness/scripts/senior_harness.py lint CONTRACT.json
python ~/.codex/skills/senior-harness/scripts/senior_harness.py ready CONTRACT.json
```

Treat exit `2` or invalid JSON as a hard stop. `lint` proves contract structure only; identity strings,
receipt labels, and its own tests are not independent proof. Schema v1 accepts candidate Capability
Packs only. Provisional or durable promotion must fail until a trusted adapter verifies signed Unlazy
receipts bound to the contract, base SHA, exact candidate SHA, command result, and independent
principal. Durable promotion additionally requires a qualified replay in a fresh workspace without
cache reuse. Bound vendor, model, runtime, or dependency changes mark the pack stale until revalidated.

The downstream driver may return only `passed`, `blocked`, `partial`, or `cancelled`. `passed` requires
contract digest, exact candidate identity, authenticated independent receipts, zero
pending/failed/abandoned/runner-error gates, and honest known-or-unknown usage.

**Complete when:** terminal status matches the receipts, promotion state matches replay evidence, and
no self-report or model grade is treated as proof.
