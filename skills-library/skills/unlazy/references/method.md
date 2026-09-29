# Natural-Depth Tree Method

Load this method when parsing `tree N`, choosing an automatic depth, or deciding whether a leaf may
split. `tree N` is a maximum decomposition depth, not a promised number of agents, leaves, tokens,
or quality.

## Choose the depth

Record `requested_depth`, `effective_depth`, and `adjustment_reason`. Choose the smallest depth whose
leaves follow real dependency, ownership, or verification joints.

- A leaf is one coherent deliverable worth about ten or more focused minutes, with one owner and one
  gate file.
- Work below about thirty focused minutes stays solo unless the user explicitly needs a plan
  artifact.
- Reduce requested depth when it creates toy leaves. Do not reset blindly to a favourite number.
- A leaf may split only before implementation and only after the parent contract/gates are updated
  and re-frozen.
- Depth above seven is reduced or rejected with a reason; depth is not architecture.

| Effective depth | Default execution |
|---|---|
| 1 | Inline; no tree artifact unless explicitly requested. |
| 2-3 | Solo driver; two to four sequential leaves; one branch/root gate set. |
| 4-5 | Orchestrated only for genuine independent leaves; bounded rolling dispatch. |
| 6-7 | Project/subsystem program; isolated worktrees, explicit integration nodes, hard caps. |

Internal nodes own decomposition and integration. Leaves own implementation. A leaf is ready only
when every dependency has passed and its required exports are available.

## Decomposition test

Each proposed leaf must answer yes:

1. Is its outcome independently understandable and gateable?
2. Does one owner control every changed production/test/docs/generated path?
3. Are its inputs and exports explicit?
4. Is it large enough that delegation overhead is justified?
5. Can it run without colliding with another ready leaf?

Merge a leaf that fails 1 or 4. Serialize or redraw ownership when 2 or 5 fails. Add a dependency or
freeze an interface when 3 fails.

## Root shape

Every node must lead to one root. Branches integrate sibling exports and own their shared checks.
Disconnected nodes, cycles, wildcard ownership collisions, or a root with no observable acceptance
outcome invalidate the plan.

The method passes when effective depth reflects natural work, leaves are coherent and owned, the DAG
is root-reachable, and orchestration overhead is justified.
