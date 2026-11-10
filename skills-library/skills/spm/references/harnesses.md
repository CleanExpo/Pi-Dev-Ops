# Self-building harness: when /spm hands work to a loop, and which one

/spm owns the loop, not just the spec. When a job is bigger than one pass, route it here instead of
running it by hand, turn after turn.

## Routing table

| The job | Route | What /spm does |
|---|---|---|
| A repeat job (the same multi-agent shape twice, or a fan-out over many items) | Claude Code dynamic workflow | Write `.claude/workflows/<name>.js` from the spec (load `workflow-authoring` first: a Claude Code built-in skill, not in this repo), pilot it on a small slice, read the pilot's output, then save it and run it as `/<name>`. Commit the script with the work so the next run reuses it. |
| A capability the estate does not have | `forge` | Hand over the gap as a verdict; forge returns a quarantined, evaluated skill. Never write the skill inline. |
| "Beat X" / make something that exists better | `gauntlet-loop` | Bar mode against a named reference, or prove mode against the current version. |
| An overnight backlog (several PRs, branches or specs) | `shipyard` | Queue the items; it runs each to merge-ready and writes a morning report. |
| A `/goal` judge repeating the same "not met" verdict | `goal-circuit-breaker` | Classify the stuck residual and break the loop instead of rewording status. |

## The four kinds of loop

From the Claude Code team's "loop engineering" guidance (claude.com blog, 30/06/2026), checked
against code.claude.com on 22/10/2026:

| Loop | What keeps it going | In Claude Code |
|---|---|---|
| Turn | Claude keeps calling tools until the job needs none | every session |
| Goal | keeps going until a stated finish line is met; a small model judges each stop | `/goal` |
| Time | wakes on a clock | `/loop` (while the session is open), `/schedule` (cloud routine, durable) |
| Proactive | starts itself when something happens | routines on events |

Pick the smallest loop that ends on a deterministic check (a command's exit code) rather than a
model's opinion, and keep state between passes in files and git, not chat.

## Cost caveat

Anthropic's multi-agent research system beat a single agent by about 90%, but used about 15 times
the tokens of a chat. So a harness goes where waiting is the cost (independent reviews, fan-out
look-ups, long check runs), not everywhere. A workflow script must state its agent count before
the pilot; the default size is under ten agents. Honour `~/.claude/HARD_STOP` and
`TAO_MAX_COST_USD`, and never move subscription work onto metered API-key billing (`--bare` and SDK
runs bill the API key).

## Limits worth knowing before writing a workflow

A workflow script cannot take input from Phill mid-run, and has no filesystem or shell of its own
(its agents do). So interviews stay in the main session, and a decision a workflow needs goes on a
decision card before the run starts.
