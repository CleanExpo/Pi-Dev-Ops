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
bash scripts/install_senior_harness.sh
```

This aligns `senior-harness`, `model-router`, and `unlazy` under `~/.codex/skills`,
`~/.claude/skills`, and `~/.agents/skills`. Codex and Claude have lifecycle-hook adapters; the
Agents root is discovery-only unless its host separately proves a lifecycle adapter.

Run the same driver explicitly from any Git project when hooks are unavailable or untrusted:

```bash
python ~/.codex/skills/senior-harness/scripts/setup_driver.py start \
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

### Governed Grill-Me entry

First create or select a fat-marker sketch in the real Obsidian vault's `Sketches/` directory. Then
freeze the Grill interaction explicitly:

```bash
python ~/.codex/skills/senior-harness/scripts/setup_driver.py start \
  "/grill-me <literal project objective>" --project "<git-root>" --surface codex \
  --interaction grill-me
```

Use `grill-with-docs` for an existing codebase. Build a dependency-ordered decision-tree JSON, then
start the session with `grill_session.py start`. Keep its state below
`$SENIOR_HARNESS_STATE_DIR` or `~/.local/state/senior-harness/`; never store control state in the
project. The machine exposes an evidence query or exactly one human question. Human questions must
carry a recommendation and rationale. Record the user's words verbatim as `DECIDED`, `RABBIT_HOLE`,
or `NO_GO`. Confirmation requires the exact phrase printed by the driver and cannot succeed while a
leaf is unresolved. Only then may `materialize` write the bound transcript under the vault's sibling
`Grills/` directory.

Load [`references/grill-contract.md`](references/grill-contract.md) for the state schema and authority
boundary. A shared-understanding receipt proves the interview resolved; it grants no mutation,
business, financial, privacy, deployment, or irreversible authority.

### Post-Grill advisory-board composition

After — and only after — a Grill session carries a valid `grill-shared-understanding` receipt, a
strategic task may prepare a five-persona advisory-board **proposal**. It is a decision-support
input, not a delivery, hiring, or agent-activation authority:

```bash
python ~/.codex/skills/senior-harness/scripts/advisory_board.py init \
  --grill-session CONFIRMED_GRILL.json \
  --task-id BOARD_TASK_ID \
  --decision-question "<bounded decision>" \
  --data-class internal \
  --max-cost-usd 20 \
  --deadline-seconds 900
```

The proposal fixes five complementary functional personas: outcome, systems, customer value, risk,
and economics. For each role, approved discovery lanes must benchmark at least two functional
candidate profiles before proposing one. They are prompt cards, not real people, celebrity
simulations, personality diagnoses, or psychometric profiles. A later routed run must return exact
provider/model/usage receipts, five independent first passes, at least two provider families, no
model reuse across personas, an anonymised claim ledger, and an independent top-floor arbiter.
Missing telemetry, silent fallback, an unsourced fact, or unresolved critical risk returns no
decision.

Before any provider dispatch, resolve and bind one approved route for every persona and the arbiter
with `advisory_board.py bind-routes`. Each route fixes provider family, exact model, endpoint,
execution location, provider-registry identity, policy digest, and reserved cost. Every later run
receipt must reproduce those values plus observed token usage and cost; a mismatch is blocked.

`advisory_board.py verify-run` proves only that a supplied run receipt meets the protocol. It never
activates a board, a persona, a worker, or a delivery task. Activation requires independent
verification and explicit owner approval in a trusted authority runtime. Do not administer or claim
Belbin, Hogan, or any other proprietary psychometric assessment; use the custom evidence and
capability matrix in [`references/advisory-board-contract.md`](references/advisory-board-contract.md).

When the confirmed Grill objective explicitly requests advisory-board composition, create this
proposal before routing board candidates or any downstream delivery. Do not auto-create boards for
unrelated Grill sessions, and do not route provider work until the proposal passes `lint`.

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
