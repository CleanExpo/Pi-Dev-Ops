---
name: northstar-shipit
description: NorthStar add-on for /northstar and /ship-it. Removes noisy branches, picks the highest-value straight path to ShipIt, and hands only the approved launch-ready lane into the existing launch-charter → ship-it → ship-chain machinery.
owner_role: Senior PM
status: wave-6
automation: manual
intents: northstar, ship-it, launch-readiness, noise-removal, straight-path
---

# northstar-shipit

The NorthStar specialised skill is the noise-removal layer that sits in front of the current `/northstar` idea and the existing `/ship-it` launch crew.

It does not invent a new shipping pipeline. It narrows messy portfolio/project context into one straight pathway to ShipIt, then hands that pathway into the existing governed chain:

`northstar-shipit → launch-charter → ship-it → launch-project-audit → launch-review → launch-enhance-debloat → pi-dev-linear-contract → ship-chain / tao-loop / ship-release`

## Purpose

Phill often has enough information in the system, but too much of it is scattered, noisy, partially built, or competing. This skill turns that mess into a single NorthStar lane:

- remove noise,
- identify the highest-leverage outcome,
- preserve only inputs that move the project toward ShipIt,
- convert the chosen lane into a launch-ready packet,
- stop before irreversible action unless the existing human gate is satisfied.

## Triggers

Use this skill when the user says or implies:

- `/northstar`
- `northstar`
- `what is the straight path`
- `remove the noise`
- `get this to shipit`
- `what is the one thing to ship`
- `cut through the clutter`
- `take this from idea to production`
- `find the pathway to ShipIt`
- `make this easy and just tell me the path`

## Core Rule

NorthStar is a forcing function, not another brainstorm.

The output must choose one primary path and explicitly reject or defer the rest. If there are multiple plausible paths, rank them but nominate exactly one default path unless a hard approval gate blocks it.

## Inputs to Load

Read only what is needed to choose the path:

1. `launch-charter` — safety/governance first.
2. Current project or repo charter / `CLAUDE.md` / `AGENTS.md` when present.
3. Relevant Obsidian/Wiki pages or source notes if the request depends on product/strategy memory.
4. Current repo status and existing build/test/deploy evidence when working inside a repo.
5. Existing `ship-it`, `launch-project-audit`, `launch-review`, and `launch-enhance-debloat` outputs if already generated.
6. Linear/queue state only through the existing `pi-dev-linear-contract` conventions.

Do not perform a broad archive crawl unless the task is explicitly discovery-shaped. NorthStar is a narrowing pass.

## Noise Removal Filter

Reject or defer anything that is:

- not required for the next ShipIt lane,
- speculative but not evidence-backed,
- a second product direction,
- a refactor with no launch impact,
- a vendor/platform change without approval,
- client communication, deploy, billing, secrets, or production DB work,
- a duplicate of an existing `ship-it` / `ship-chain` / `tao-loop` phase,
- a “nice to have” that does not unblock launch readiness.

## Straight Path Method

Produce the following in order:

1. **NorthStar outcome** — one sentence: the business/product outcome to ship.
2. **Current state** — what exists, what is missing, and what evidence proves it.
3. **Noise removed** — list discarded branches and why they do not matter now.
4. **Default ShipIt lane** — the one lane to pursue next.
5. **Gate check** — whether the lane is local-safe, approval-gated, or blocked.
6. **Handoff** — exact next skill/phase to call.

## Output Shape

```markdown
# NorthStar ShipIt Path

## NorthStar outcome
<one sentence>

## Evidence read
- <path/id> — <why it mattered>

## Noise removed
- <branch> — deferred because <reason>

## Default ShipIt lane
1. <next concrete step>
2. <next concrete step>
3. <next concrete step>

## Gate check
- Status: LOCAL_SAFE | NEED_APPROVAL | BLOCKED
- Reason: <short reason>

## Handoff
- Next skill: <launch-charter | ship-it | launch-project-audit | launch-review | ship-chain>
- Next artifact: <file/path or Linear queue target>
```

## ShipIt Handoff Rules

- If the project has not had a launch-readiness pass, hand off to `ship-it` after `launch-charter`.
- If the build-state is unknown, hand off to `launch-project-audit`.
- If build-state is known but launch quality is unknown, hand off to `launch-review`.
- If the issue is bloat, dead code, weak critical path, or security hardening, hand off to `launch-enhance-debloat` in propose-only mode.
- If a single feature is already specified and build-ready, hand off to `ship-chain` or `tao-loop` through the existing queue.
- If review score is below threshold, do not ship; feed the concrete fixes back into the queue.

## Safety Boundaries

- No deploys.
- No production DB writes.
- No public publishing.
- No client communications.
- No billing/payment actions.
- No secrets, password, token, permission, or spend-cap changes.
- No direct push to `main`.
- No replacement of `ship-it`, `ship-chain`, `tao-loop`, `tao-judge`, or `ship-release`.

NorthStar can choose the path. Existing gates decide whether it may run.

## Verification

A compliant NorthStar run has:

1. `launch-charter` loaded before any build or ShipIt path.
2. Exactly one nominated default ShipIt lane.
3. At least one concrete evidence path or ID for the decision.
4. Noise explicitly removed/deferred.
5. A gate status of `LOCAL_SAFE`, `NEED_APPROVAL`, or `BLOCKED`.
6. A handoff to an existing skill; no invented shipping path.

## Out of Scope

- Deep research without an active ShipIt target.
- Rewriting the launch crew.
- Creating new vendors or connector platforms.
- Automating human approval gates.
- Doing the build/test/ship work inside this skill.

## References

- `launch-charter` — immutable governance first.
- `ship-it` — launch-readiness pre-flight.
- `launch-project-audit` — build-state map.
- `launch-review` — multi-lens launch review.
- `launch-enhance-debloat` — propose-only strengthening/de-bloat.
- `ship-chain`, `tao-loop`, `tao-judge`, `ship-release` — existing gated build/test/ship machinery.
