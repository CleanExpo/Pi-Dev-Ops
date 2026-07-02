---
name: autonomy-ladder
description: Capability-tiered autonomy gating for all agent action — maps the DeepMind AGI→ASI continuum (arXiv:2606.12683) onto four autonomy tiers (L0 advise → L3 strategic/irreversible), each with an explicit gate. Use to decide "can this agent do this action un-gated, or must it stop for a human/Board?" before any autonomous or multi-move execution, and to design where the gate is ENFORCED. Triggers on "autonomy ladder", "autonomy gate", "can the agent do X autonomously", "gate this action", "should this escalate", multi-move executor design. The formal, capability-scaled version of the decision-rights matrix.
---

# autonomy-ladder — how much autonomy, gated by capability × reversibility

The decision-rights matrix says WHAT the agent owns vs escalates. This skill is
its **capability-tiered spine**: as an action moves from bounded single-domain
work toward cross-domain "group-agent" strategic action, the required gate rises.
Framing borrowed from DeepMind *"From AGI to ASI"* (arXiv:2606.12683), whose
Pathway-4 "group agency" is exactly the ASI-shaped work that must not run
un-gated, and whose named failure mode ("solipsistic" isolated optimization)
motivates the cooperation + oversight gates.

## The ladder (assess EVERY autonomous action against this)

| Tier | Shape of action (AGI→ASI analogue) | Examples | Gate |
|---|---|---|---|
| **L0 — Advise / Read** (Emerging) | Read-only, analysis, drafts. No state change. | grep/read, survey, write a spec/recommendation, draft (not send) | **None.** Just do it. |
| **L1 — Reversible single-domain act** (Competent) | Local, non-destructive, single-domain, undoable. | commit local change, run tests, push a `feat/*` branch, file a Linear ticket, update memory/wiki | **None** — but MUST smoke-test + leave a trail (TaskUpdate, ticket). Matches decision-rights "you own". |
| **L2 — Cross-domain / outward-facing** (Expert) | Reaches another domain or an external surface; still reversible. | open a PR (not merge), cross-specialist synthesis via `specialist-council`, draft outbound comms, provision within an existing system | **Self-verify + structured stamp.** Council cooperation-gate applies; PR opened but human merges. policy.py records the action. |
| **L3 — Irreversible / strategic / group-agent** (Virtuoso→Superhuman) | Hard to reverse, or a strategic commitment, or coordinated multi-agent action producing effects beyond any single agent. | merge to main / deploy prod, prod DB migration, secret rotation, spend > $1k, new service, branch-strategy change, drop a business, migrate a substrate | **STOP → human/Board review BEFORE acting.** This is the ASI-shaped work; never self-authorize. |
| **KILL** | any tier | — | `~/.claude/HARD_STOP` / `/panic` halts everything instantly. |

**Decision rule:** rate an action by (a) reversibility and (b) domain breadth.
The HIGHER of the two picks the tier. A "small" but irreversible action (a prod
migration, a secret) is L3 regardless of size. When genuinely unsure between two
tiers, take the higher (more gated) one.

## The enforcement gap (the part that actually matters)
A ladder is theatre unless the gate is *enforced where the action happens*.
Today (`pi-dev-ops-autonomy-gate-layer`): `policy.py` only gates **pre-stamped
structured actions** — it does NOT intercept raw tool calls inside a
`bypassPermissions` generator turn, so an autonomous coding loop can execute L3
actions unguarded. **Requirement:** before ANY multi-move executor ships, the L3
gate must live at the **SDK permission / hook layer** (a `PreToolUse` hook or the
SDK `permission_mode` callback that inspects each tool call), not only at
policy.py's stamp. The hook classifies the pending tool call to a tier and blocks
L3 pending human approval. That is the one engineering task that makes this real.

## Cooperation / oversight (anti-solipsism)
For L2+ multi-agent work, an agent's output is accepted only if it engaged at
least one peer's objection (the `specialist-council` cooperation gate). Isolated
optimization that ignores peers is rejected — the paper's "solipsistic
superintelligence" failure mode, gated in practice.

## How to use
1. Before an autonomous action, classify it L0–L3 by the table.
2. L0/L1 → proceed (trail for L1). L2 → act but stop short of the human-only step
   (open PR, don't merge). L3 → STOP and surface for human/Board.
3. When designing an executor/loop, put the classifier at the tool-call hook, not
   downstream of it.

## Anti-duplication
This governs; it does not replace. It formalizes the decision-rights matrix,
leans on `kill-switch-binding` for KILL, `specialist-council` for the cooperation
gate, and points the enforcement at the existing SDK/hook layer. It adds no new
runtime — it says WHERE the existing gates must sit and WHAT tier triggers them.
See `pi-dev-ops-autonomy-gate-layer`, `feedback-autonomy`.
