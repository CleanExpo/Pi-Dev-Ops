---
name: wayfinder
description: Chart a foggy, bigger-than-one-session effort as a shared map of decision tickets on Linear, then work the map one decision per session until the way is clear.
argument-hint: "<the foggy effort/destination, or 'work' to continue an existing map>"
disable-model-invocation: true
---

# /wayfinder — decision maps for efforts too big to hold

Plans, it doesn't do. When an effort is more than one session can hold and the route is still
foggy — you feel the shape but can't yet write the spec — chart it as a shared map of
**decision tickets** on Linear. When the way is clear, hand off: shaped decisions →
`grill-me`/`grill-with-docs` transcripts → Pitch → `spm`/`technical-plan` → execution ADWs.
Estate synthesis + provenance: [[wayfinder-x-agentic-engineering-2026-07-14]],
[[pocock-skills-v11-wayfinder-pipeline-2026-07-14-ingest]] (adapted from Matt Pocock's
/wayfinder, mattpocock/skills v1.1).

## When NOT to use

- Scope already specifiable → go straight to `spm`/`technical-plan`.
- Fits one session → just do it, or run a single `grill-me`.
- Execution work → the factory side (pm-core, ADWs), never this skill.

## The map (Linear-native)

- One parent issue labelled `wayfinder:map` holds: the **destination** (naming it is the first
  act of charting — it shapes every ticket), a decisions-so-far index, the **fog** ("not yet
  specified" — intentionally incomplete), and out-of-scope.
- Child issues are the tickets. Blocking uses Linear's native blocked-by relations. The
  **frontier** = open, unblocked tickets — always visible without reopening the map.
- Refer to tickets by **title, never number**. A wall of RA-4021/RA-4022 is illegible.

## Ticket types

| Type | Mode | Resolves via |
|---|---|---|
| Research | AFK | subagent fan-out at charting time, sources cited |
| Grilling | HITL | live `grill-me`/`grill-with-docs` exchange — never self-answered |
| Prototype | HITL | throwaway artifact that clarifies the decision |
| Task | either | manual work that unblocks a decision |

## Mode 1 — chart

1. Name the destination with the operator; write the map issue.
2. Walk the frontier breadth-first: ticket every question **sharp enough to phrase precisely**;
   leave the rest in the fog (don't fake-ticket vague unease).
3. Wire blocked-by relations; fire all Research tickets to parallel subagents immediately.
4. Stop. Charting and working are separate sessions.
- Completion: map issue + named tickets + blocking exist on Linear; research is in flight.

## Mode 2 — work

1. Load the map; claim ONE unclaimed frontier ticket (assign yourself first).
2. Resolve it with the matching skill (grilling → grill-me; prototype → sketch/build throwaway).
3. Record the answer as a **resolution comment** (never edit it into the ticket body); update
   the map's decisions index and fog; ticket any newly-sharp questions.
4. Stop. **One decision per session** (Research tickets excepted) — decisions never parallelise;
   only AFK research and downstream execution do.
- Completion: exactly one decision recorded, map current, next frontier visible.

## Done

The map is done when the fog is empty or explicitly parked out-of-scope. The exit artifact is a
shaped backlog `spm` can spec — the go/no-go gate between planning and the factory. If Linear
is unreachable, chart the same structure as a vault file (`2nd Brain/Plans/`) and migrate when
auth returns; never let tracker downtime cancel the discipline.
