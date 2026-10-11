Moved from SKILL.md. Read when rendering the Linear ticket body or extracting target_repo.

## The Linear ticket body template

Bridge renders this using research body + extracted action:

```markdown
# {{proposed_action}}

> Originated by Margot (`mcp__margot__deep_research_max`) — interaction `{{interaction_id}}`
> Approved by Founder via Telegram draft `{{draft_id}}` on {{ts}}
> Routed to AFK execution via Sandcastle (`sandcastle:high-isolation`)

## Research summary

{{research_body}}

## Proposed action

{{proposed_action_detail}}

**Target repo:** `{{target_repo}}`
**Proposed branch:** `{{proposed_branch}}`
**Complexity tier:** `{{complexity_tier}}` (basic/detailed/advanced)
**Estimated max files modified:** {{max_files}}

## Acceptance criteria

{{acceptance_criteria}}

## Out of scope

{{out_of_scope}}

## How this will run

1. autonomy.py picks up this ticket (label `pi-dev:autonomous`, status `Ready for Pi-Dev`)
2. session_phases.run_build hits the branch point (label `sandcastle:high-isolation` present)
3. sandcastle-runner spawns Sandcastle in Docker container with the parallel-planner-with-review template
4. Sandcastle internally: plan → 3 parallel implementers → reviewer → merger → final branch
5. Pi-CEO _phase_evaluate scores the result; _phase_push opens a PR
6. Founder reviews PR, merges via dual-key gate

Kill-switch: `TAO_SANDCASTLE_ENABLED=0` falls through to weak-sandbox path.

## References

- Original Margot interaction: `{{interaction_id}}`
- Bridge skill: `Pi-Dev-Ops/skills/margot-sandcastle-bridge/SKILL.md`
- Sandcastle runner: `Pi-Dev-Ops/skills/sandcastle-runner/SKILL.md`
- Wave 5 epic: <issue id="RA-1856">RA-1856</issue>
```

The `target_repo` is extracted from the research body via:
- Explicit mention (e.g. "we should fix RestoreAssist's Stripe webhook" → `CleanExpo/RestoreAssist`)
- Match against `config/harness/projects.json` repo names
- Fallback: ask the founder via the draft body itself ("Confirm target repo? Detected: [list of candidates]")
