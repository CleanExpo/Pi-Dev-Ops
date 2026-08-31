# ADR 008: Fleet autonomy charter — what runs unattended, and what stops for a human

**Date:** 2026-08-31
**Status:** Accepted

## Context

The three-machine fleet (`phills-macbook-pro`, `unite-mac-mini`, `phill-desktop`) is being woken
from dormancy: a scheduled dispatcher assigns Linear tickets to whichever node has spare
capacity, ingestion pulls external material into the wiki, the board files work, and the spec
pipeline builds it. The owner's requirement is explicit — that future problems of this class be
handled "autonomously", with the method, process, skills and **authority** already in place.

Authority is the part that cannot live in a prompt. An agent asked each time "may I?" is not
autonomous; an agent that decides its own limits is not governed. So the boundary is written
here, once, and the code enforces it with flags and caps rather than with judgement.

This ADR does not grant capability — every mechanism it references already exists or is being
added under its own review. It states which of them may run without a human in the loop.

## Decision

### Unattended — the system may do these on its own

| Action | Bound that makes it safe |
|---|---|
| Dispatch tickets to fleet machines | `mesh_work_claims_one_open` gives exactly one owner per ticket; stale claims are reaped back to Todo; `MESH_DISPATCH_ENABLED` is the master switch |
| Run an agent on a claimed ticket | Branch-only (`mesh/<host>/<ticket>`); 1h timeout; `~/.claude/HARD_STOP` drains mid-run |
| Claim and resume an interrupted session | Ownership lease with expiry; a dead holder's work is re-claimable, never double-run |
| Ingest external sources into the wiki | Writes confined to the agent-owned subtree; source text is fenced as data; a model-chosen path outside the boundary is quarantined, not written |
| Research a question | Free/local tier first, then paid with a daily ledger cap |
| File Linear tickets from board output | Capped per run, mandate-consistency gated, routed by project `id`; off by default (`BOARD_FILE_MACHINE_SHIP`) |
| Comment pipeline progress back to Linear | Fire-and-forget; never blocks or fails the pipeline |
| Propose a new skill | Proposal only — it lands in the existing approval queue, never on disk |
| Open a PR from a completed spec build | `main` stays PR + CI gated; CI is the merge authority |

### Human-gated — the system may not do these alone

| Action | Why it stops |
|---|---|
| Merge to `main` | CI proves the code runs; only a person accepts the change |
| Accept a proposed skill | A skill changes how every later run reasons. Approval stays with the owner |
| Raise a cap, or flip a master switch on | The caps are the boundary; moving them is a governance act, not a task step |
| Spend on a new paid vendor (e.g. an ASR provider) | Recurring cost is the owner's decision |
| Rotate or relocate a credential | See below |
| Delete anything | The system archives and quarantines; it does not delete |
| Change branch strategy, run a destructive migration, provision a service | Pre-existing standing rule (CLAUDE.md § Sandbox and scope) |

### Credentials do not move

Work moves to capacity; credentials stay put. No component may pool, rotate, share or
multiplex accounts to spread load or evade a per-account limit. Each machine authenticates as
its owner configured it locally; headless workers use API keys. A design that needs a
credential to travel between machines is the wrong design, and the repo already encodes this:
`scripts/estate/guard_claude_lane.sh` fails on the *presence* of an env-supplied token,
because a credential handed in by the environment would let the check approve itself.

### Untrusted input has no authority

Transcripts, articles, web pages, issue and PR comments are **data**. They may be summarised,
scored and stored. They may never issue instructions, select a write path, or widen scope. An
instruction found inside source text is reported, not obeyed. When the guard cannot decide, it
quarantines — failing closed costs a page of wiki content; failing open costs the knowledge
base.

### Every switch defaults to off

A capability arrives disabled. Enabling it is a separate, deliberate act by a person, and is
reversible without a deploy. This is why `MESH_DISPATCH_ENABLED`, `BOARD_FILE_MACHINE_SHIP`,
`TAO_MACHINE_SHIP_MODE` and their siblings exist as environment flags rather than as
constants: the shutdown path must not require an engineer.

## Consequences

- Autonomy is legible. "Can it do X on its own?" is answered by this table, not by reading the
  agent's reasoning after the fact.
- Adding an unattended capability means adding a row here and the bound that makes it safe. A
  capability with no bound does not get a row, and does not ship enabled.
- Some latency is accepted deliberately: a proposed skill waits for approval, a merge waits for
  a person. That is the intended trade — the system compounds knowledge continuously and takes
  irreversible steps only with a human.
- The kill switch stays universal: `~/.claude/HARD_STOP` drains in-flight work on every node
  without a restart, and `TAO_AUTONOMY_ENABLED=0` stops the poller entirely.

## Re-derive

```bash
# Which flags actually gate the unattended actions above
grep -rn "MESH_DISPATCH_ENABLED\|BOARD_FILE_MACHINE_SHIP\|TAO_MACHINE_SHIP_MODE\|TAO_AUTONOMY_ENABLED" app/ swarm/
# The single claim lock every claimant must use
grep -n "mesh_work_claims_one_open" mesh/schema/0001_nexus_mesh.sql
# The credential position, enforced
sed -n '40,60p' scripts/estate/guard_claude_lane.sh
```
