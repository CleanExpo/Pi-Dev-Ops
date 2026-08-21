---
name: senior-harness
description: Use before substantive project work that requires governed discovery, delegation, verification, or recovery from repeated failure.
allowed-tools: Read, Grep, Glob, LS, Bash
---

# Senior Harness

Put the control contract above the Lead LLM. The model may discover, propose, route, and report; it
may not expand authority, accept its own work, repeat a failed pathway, or promote a capability.

## Usage

After installation and a new task reload, explicit invocation remains available when automatic
triggering is uncertain:

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
