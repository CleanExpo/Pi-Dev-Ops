---
name: forward-planner
description: Research a project and plan 15+ moves ahead before building anything. Establishes the win condition (Definition of Done), reads the board (repo + PORTFOLIO registry + live external research), computes the gap, lays a roadmap spine of 15+ verifiable moves, forks branch points where outcomes are contingent, and red-teams the end-state to surface the "move-16 surprise" before it bites. Produces BOTH a human-readable foresight brief AND a machine-readable structured plan the swarm can execute. Use this FIRST whenever you (or the autonomous loop) are about to build, scope, or roadmap a project — and whenever someone asks "what's the full path to X", "what are we missing", "plan N moves ahead", "think this through", or talks about strategy, foresight, lookahead, sequencing, dependencies, or roadmaps. Use it even when the request just says "build project X" — map the whole path before executing the first step.
owner_role: Strategist
status: wave-5
automation: hybrid
intents: foresight, lookahead, forward-planning, roadmap, sequencing, dependency-planning, scope, win-condition, what-are-we-missing, plan-ahead, strategy
---

# forward-planner

Plan the whole game, not just the next turn.

## Why this exists

This system's most expensive failure is *false completion*: it decomposes the brief in front of it, finishes those tasks, reports "done" — and then a missing piece surfaces that was never a task because it was never in the brief. The brief was treated as the complete statement of work. It never is.

The root cause is structural, not a willpower problem: nothing computes *what the finished project actually requires*. Decomposition asks "what are the parts of this brief?" Foresight asks "given where we are and where we must end up, what is the full path — including the things nobody wrote down yet?" Those are different questions, and only the second one stops the "sorry, yes, it needed that" loop.

This skill is the second question. It runs *before* the build, names the destination, maps the route 15+ moves out, and deliberately hunts for what's missing — so the plan, not the human, is the thing that notices the gap.

It sits upstream of [`define-spec`](../define-spec/SKILL.md) and [`technical-plan`](../technical-plan/SKILL.md): forward-planner produces the project-level win condition and move sequence that those skills then refine into specs and technical detail. It operates inside [`launch-charter`](../launch-charter/SKILL.md) governance — it proposes; it never edits the rails, and any change to a project's defined "done" is surfaced for human approval rather than self-authored silently.

## When to use this

- Before any build, scope, or roadmap of a project — interactively or in the autonomous loop.
- When the goal is large, vague, or new enough that the brief is obviously incomplete.
- When someone asks "what's the full path to X", "what are we missing", "what's next after that", "plan this 15 moves ahead", or anything about strategy / sequencing / dependencies.
- As a periodic re-plan: re-read the board, recompute the gap, see if the spine still holds.

If the task is genuinely a one-liner with a known, complete scope (fix a typo, bump a version), skip this — foresight on a settled task is wasted motion. The value is proportional to how much is *unknown*.

## The method

Treat the project like a game tree with a defined win condition. Eight moves of your own, in order. Each step says *why* it matters, because skipping the "why" is how planners regress to brief-decomposition.

**1. Name the win condition first.** Before any move, state what "done / winning" looks like as *checkable* conditions — capabilities that must exist, surfaces that must respond, schema that must be present, integrations that must be wired, tests that must pass. This is the anchor. The entire reason the system keeps missing things is that it plans forward from a brief instead of backward from a defined end-state. You cannot find what's missing without first declaring what "complete" is. If a charter exists for the project (e.g. `.harness/business-charters/<project>.md`), mine it for the first draft of these conditions, but convert prose into checkable statements.

**2. Read the board.** Know where the pieces actually are before moving them.
- *Internal*: the repo, the registry (`.harness/projects.json`, `PORTFOLIO.yaml`), open Linear tickets, current deployment state.
- *External*: relevant technology, market, and best-practice research via web search / deep research — what's changed, what others do, what's coming.
Ground the plan in reality; a move that assumes a thing exists when it doesn't is a future apology.

**3. Compute the gap.** `win condition − current state` = the raw material of the plan: everything required that does not yet exist. This is a set difference, and doing it explicitly is what makes the plan self-aware about scope.

**4. Lay the spine.** Order the gap into a mainline of **15 or more** concrete moves, current state → win condition, respecting real dependencies (you can't build B before A). Each move is a single verifiable deliverable — never a vague phase like "polish UX." If you can't state how a move is checked, it isn't a move yet; split it until you can.

**5. Look ahead at every move — "then what?"** This is the actual foresight, and the step decomposition skips. For each move ask:
- What does completing this *unlock* or make possible next?
- What does it *require* that doesn't exist yet (a hidden prerequisite to pull earlier)?
- What could *break* because of it, and what's the response?
- What *decision* does it force?
Pushing each move 3–5 steps downstream is what surfaces prerequisites before they block you.

**6. Mark branch points — spine where determined, tree where contingent.** Where the correct next move depends on an outcome (a test result, a user decision, an external event), fork: "if X → moves A…; if Y → moves B…". Do **not** branch everywhere — a fully branched tree explodes combinatorially and helps no one. Branch only where the divergence is real *and* consequential. Everywhere else, stay on the spine.

**7. Red-team the horizon.** Walk the spine to its end *as if it already happened* and ask the uncomfortable question: did we actually win, or is there a move-16 surprise we'll be apologizing for? Look specifically for the classes of missing work this system habitually drops — auth, migrations, error states, observability, rollback, docs, the integration nobody owned. Pull whatever you find back into the plan **now**. This step is the direct antidote to false completion; treat it as mandatory, not optional polish.

**8. Emit both artifacts.** A foresight brief (the reasoning, for humans) and a structured plan (the executable graph, for the swarm). Templates and the JSON schema are in [`references/output-templates.md`](references/output-templates.md). Validate the structured plan with the bundled script before handing it on (see below).

## Principles to hold throughout

- **Destination before route.** Name the win condition before listing moves. Always.
- **Every move is verifiable.** A move you can't check is a move you can't know you've finished — and unverifiable moves are where false completion hides.
- **Lookahead beats breakdown.** "What will this require and cause, several steps out" finds more than "what are the parts of this."
- **Branch sparingly.** Contingency is expensive; spend it only where outcomes genuinely diverge.
- **Assume you missed something.** The red-team pass exists because confidence is exactly when the gap goes unnoticed.
- **Grounded, not hypothetical.** Tie every move to the real repo/registry state, not an imagined one.

## Outputs

Produce both, in this order:

1. **Foresight brief** — markdown, human-facing. Follow the template in [`references/output-templates.md`](references/output-templates.md): win condition → board state → gap → the 15+ move spine → branch points → risk horizon → red-team findings → immediate next move.

2. **Structured plan** — JSON, machine-facing, conforming to the schema in the same reference. It carries the move graph (dependencies, unlocks, branch points) and Linear-ready routing so the orchestrator / [`gap_detector`](../../swarm/gap_detector.py) can file tickets against the right project via `projects.json`.

After writing the structured plan, validate it:

```bash
python skills/forward-planner/scripts/validate_plan.py <path-to-plan.json>
```

The validator checks the schema, confirms there are ≥15 moves, detects dependency cycles and dangling `depends_on` references, and prints a short summary (move count, branch points, unrouted moves). A plan that doesn't validate isn't ready to hand to the loop.

## How it fits the system

- **Upstream of build.** forward-planner → `define-spec` → `technical-plan` → the build loop (`tao_loop`). It supplies the win condition and sequence the rest refine and execute.
- **Feeds gap detection.** Its structured plan is the spec the coverage check diffs against, so the loop can stop on *project* completeness, not per-task `GOAL_MET`.
- **Governed.** Honors [`launch-charter`](../launch-charter/SKILL.md): proposes plans and scope, never rewrites guardrails; changes to a project's win condition are surfaced for human approval.

## Deeper detail

- [`references/method.md`](references/method.md) — the method expanded, with the branching discipline and a short worked example. Read it when a plan is large or heavily contingent.
- [`references/output-templates.md`](references/output-templates.md) — full brief template, the JSON schema, and a filled example. Read it before emitting outputs.
