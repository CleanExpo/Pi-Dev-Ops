# forward-planner — output templates

Two artifacts every run: a **foresight brief** (markdown, for humans) and a **structured plan** (JSON, for the swarm). Write the brief first — it's your reasoning — then derive the structured plan from it and validate.

---

## 1. Foresight brief template

Use this structure. Keep moves concrete and verifiable; keep prose tight.

```markdown
# Forward plan: <project / goal>

Generated: <date> · Horizon: <N> moves · Planner: forward-planner

## Win condition (Definition of Done)
What "complete" means, as checkable conditions. Mark each [auto] (machine-verifiable)
or [human] (needs judgment).
- [auto] <condition>
- [auto] <condition>
- [human] <condition>
...

## Board state
**Internal:** <repo / registry / tickets / deployment reality>
**External:** <relevant research findings, dated>

## The gap (win condition − current state)
| Win-condition item | Status (present/partial/absent) | Notes |
|---|---|---|
| ... | absent | ... |

## The spine — <N> moves
For each: deliverable, how it's verified, what it unlocks, prerequisites.
1. **<title>** — *Deliverable:* <one line>. *Verify:* <one line>. *Unlocks:* <…>. *Requires:* <…>.
2. ...
(15 or more)

## Branch points
- **After move <k> — <decider>:** if <X> → moves <…>; if <Y> → moves <…>. Re-converges at move <m>.

## Risk horizon
What could break across the plan, and the response.
- <risk> → <response / mitigating move #>

## Red-team findings (pulled forward)
Gaps found by walking the spine to its end and assuming "done" was a lie.
- <discovered gap> → inserted as move <#>

## Immediate next move
The single move to start now, and why it's first.
```

---

## 2. Structured plan — JSON schema

The machine-readable counterpart. The swarm/orchestrator consumes this to file tickets and to drive coverage-based completion. Conform to this shape:

```json
{
  "schema_version": "1.0",
  "project_id": "<id from .harness/projects.json, e.g. 'unite-hub'>",
  "goal": "<the original brief / goal>",
  "generated": "<ISO date>",
  "horizon": 15,
  "win_condition": [
    {"id": "wc1", "statement": "<checkable condition>", "check": "auto|human", "probe": "<how to verify, optional>"}
  ],
  "moves": [
    {
      "id": "m1",
      "title": "<short title>",
      "deliverable": "<concrete output>",
      "verify": "<how completion is checked>",
      "depends_on": [],
      "unlocks": ["m2"],
      "satisfies": ["wc1"],
      "is_branch_point": false,
      "branches": [],
      "linear": {
        "project_id": "<linear_project_id from projects.json>",
        "team_id": "<linear_team_id from projects.json>",
        "priority": "Urgent|High|Medium|Low"
      }
    },
    {
      "id": "m7",
      "title": "Password-reset email delivery",
      "deliverable": "Reset emails sent on request",
      "verify": "Integration test: request reset → email enqueued",
      "depends_on": ["m6"],
      "unlocks": ["m8"],
      "satisfies": ["wc4"],
      "is_branch_point": true,
      "branches": [
        {"decider": "managed email provider approved?", "if": "yes", "then": ["m7a"], "reconverge": "m8"},
        {"decider": "managed email provider approved?", "if": "no", "then": ["m7b"], "reconverge": "m8"}
      ],
      "linear": {"project_id": "...", "team_id": "...", "priority": "High"}
    }
  ],
  "risks": [
    {"id": "r1", "risk": "<what could break>", "response": "<mitigation>", "mitigated_by_move": "m10"}
  ]
}
```

### Field notes

- **`win_condition[]`** is the Definition of Done. Every `move.satisfies` should reference a real `wc*` id; every `wc*` should be satisfied by at least one move (the validator warns if not — that's a red-team miss).
- **`moves[]`** must contain ≥15 entries. `depends_on` and `unlocks` form the dependency graph; they must be acyclic and reference existing move ids.
- **`is_branch_point` / `branches[]`**: only `true` where outcomes genuinely diverge. Each branch names its `decider` and ideally a `reconverge` move.
- **`linear`** routing comes straight from `.harness/projects.json` for the project — this is what lets `gap_detector` / the orchestrator file each unmet move as a ticket in the correct Linear project and team.
- **`probe`** on a win condition is optional but valuable: it's the seed for the coverage check that lets the loop terminate on project completeness rather than per-task `GOAL_MET`.

Write the JSON to a file (e.g. `<project>-forward-plan.json`) and validate it with `scripts/validate_plan.py` before handing it to the loop.
