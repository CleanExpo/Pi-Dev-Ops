---
name: crew
description: Dispatch the eight operational roles against a task, each grounded in the vault before it reads any code, with a live view of what is running. Use for work that wants several independent lenses at once — map, plan, build, verify, review, security, CI, release — rather than one agent doing everything.
argument-hint: "<task>"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, Write, Agent
---

# /crew — the operational roles, dispatched and visible

Eight roles from `~/Pi-CEO/.harness/agents/registry.yaml`, each with a lane and a risk
ceiling, fanned out against one task. Every step lands in an append-only evidence log, and
the log is the only thing the render reads — so what you see is what actually happened, not
what the dispatcher believed.

**Wave 1 clears five of Orchestrator V1's six components.** One queue, one dispatcher,
evidence logging, a dashboard, and no-deploys-without-approval all land. The **mini worker
over Tailscale does not** — the Mini is Codex-only and cannot authenticate Claude over SSH.
Any report that calls this "bar met" without that leg running is a false green.

## Run it

```
/crew <task>
```

### 1. Preflight

```bash
python3 ~/.claude/skills/crew/scripts/crew_preflight.py
```

Returns the grounding stamp and the dispatchable roles with their ceilings.

`GROUNDING: OK` means the vault index is clean. `DEGRADED (n)` means it is drifting by `n`
issues and every role below inherits that gap — the run continues, carries the stamp into the
log, and shows it at the top of the render. This is deliberate: the estate stamps a weaker
reviewer DEGRADED rather than substituting it silently, and grounding gets the same rule. It
is not permission to ignore the number. `UNAVAILABLE` means brain.js was not found — say so
rather than reporting roles as vault-grounded.

### 2. Choose the roles

Not every task wants eight. Pick the lanes the task actually has, and say which you skipped
and why — a role omitted silently reads as a role that found nothing.

Check each before dispatch:

```bash
python3 ~/.claude/skills/crew/scripts/crew_preflight.py --role builder --tier 1
```

Exit 1 means refused, with the reason. The gate is an allowlist: a role is dispatchable only
if the registry names it and its ceiling covers the request. An unknown role, an unreadable
registry, or a missing ceiling all refuse. Do not dispatch a role the gate refused.

### 3. Dispatch

One `Agent` call per role, `subagent_type` matching the role file (`crew-scout`,
`crew-planner`, …). Send them in a single message so they run concurrently. Give each the
task verbatim plus the grounding stamp; the role file and `CONTRACT.md` carry everything else.

Log the run start, then each role as it resolves:

```bash
python3 ~/.claude/skills/crew/scripts/crew_log.py --type run_start --session "$S" \
  --field task="<task>" --field grounding="DEGRADED (619)"
python3 ~/.claude/skills/crew/scripts/crew_log.py --type done --role scout --session "$S" \
  --field note="mapped 12 files"
```

The logger serialises concurrent appends and mirrors to `~/Pi-CEO/.harness/swarm/` **when
that directory exists**. When it does not, the mirror is skipped and the skip is reported —
the directory is never created. Creating it on a machine with no Pi-CEO checkout would
fabricate harness state for a harness that is not installed there.

### 4. Render

```bash
python3 ~/.claude/skills/crew/scripts/crew_render.py --session "$S"
```

Offline, no network. Exit 0 rendered; exit 2 nothing to render **with the reason named** —
`NO LOG`, `LOG EMPTY`, and `SESSION NOT FOUND` are three different states and never share a
message. A renderer that draws an absent run the same way it draws a broken one is the
failure that check exists to catch.

## What it will not do

- **No writes to a real repository.** `builder` runs in proposal mode; write authority is a
  waterline point and a separate decision.
- **No flipping a registry role from `status: shadow` to active** — that changes runtime
  routing for systems beyond this command.
- **No publishing.** The phone view was scoped out of wave 1: it needs an external host, so
  it is not offline and nothing here depends on it.
- **No Pi-CEO server dependency.** The terminal render and the log are the primary visual and
  work with Pi-CEO absent entirely.

## Verifying it still works

```bash
python3 ~/.claude/skills/crew/tests/test_crew.py     # 22 controls
python3 ~/.claude/skills/crew/tests/mutate_crew.py   # 8 of those 22, proven able to fail
```

The mutation harness is the one that matters. It reintroduces each defect into a throwaway
copy and asserts the guarding control goes red — concurrent appends, the optional mirror,
absent-is-not-broken, the fail-closed risk gate, and the registry parser's scope. One mutant
is declared survivable with its reason rather than quietly counted as covered.

**Its scope is 8 mutants against 22 controls, not all 22.** Six of the seven test classes have
at least one mutant; `GroundingStamp` has none, so the grounding stamp's controls have never
been shown able to fail. That is the same guard whose seam defects F1 and F3 describe — the
suite stays green while both reproduce. Read a green mutation run as "these 8 defects are
guarded", never as "every control is proven".
