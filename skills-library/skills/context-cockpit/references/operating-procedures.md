# Conditional operating procedures

Read the relevant section when reviewing/releasing, interpreting quality claims, or recovering context. Current user instructions, the compact CLAUDE.md, installed capability, and fresh vendor evidence take precedence over dated incident details. Historical release incidents are retained in a separate reference and do not establish current entitlement. A metered lane is ineligible under a zero-incremental-spend task.

## Release review and account recovery

Before release, read `skills/pr-release-gate/SKILL.md` and use its current scripts and installed lane registry. Required checks and independent non-builder review bind to the exact final commit; changed HEAD invalidates them. Inspect the complete report, including executed negative controls, rather than trusting process exit status. Obtain the required receipt before push; observe GitHub's required checks at the pushed SHA before opening or readying a PR. Preserve default human merge and the limited, fully gated UG-AUTONOMY-001 exception in CLAUDE.md. Never manufacture exemptions, force push or bypass hooks.

Discover current eligible review lanes through `lane_registry.py --list`. Diagnose a failed lane, then select the next eligible lane explicitly. Respect current task cost/authority limits; a zero-incremental-spend task excludes metered fallback even when a historical default chain includes it. An unavailable vendor alone does not establish that every authorized independent lane is unavailable.

Subscription sign-in, fresh quota/account evidence, a successful inference probe and an actual review report prove different things. An authentication or usage error can have several causes. Diagnose the actual error with current vendor documentation and account evidence; never infer an expired token solely from its wording. Do not buy credits or silently switch to an API key. Login that needs founder interaction remains founder-gated. Resolve credentials through the documented resolver without opening or printing secret values.

Dated release incidents are preserved in `release-incidents-202608-09.md` for investigation only. They must not decide current billing, lane eligibility or credentials.

## Quality claims

### The quality bar — AAA is a rung, not an adjective

A rung is earned against a bar chosen **per run**, which must be **Named · Fetchable ·
Comparable**. There is deliberately no fixed estate-wide rubric. Three ladders share rung names
and do not share meanings, so always say which one:

- **Ladder-C** (`gauntlet-pair`) — artefacts with a fetchable exemplar: copy, design, imagery,
  video, research, course content. Binary comparisons only; no number is ever assigned.
- **Ladder-S** (`gauntlet-ship`) — production behaviour. Rung A means the gate was **watched
  failing** on the live defect. Repo rung AAA = the eight criteria in `prompts/ship-gauntlet.md`.
- **Judge-100** (`judge`) — decision readiness only. **A judge 100 is not an AAA rung.**

**Claim grammar — mandatory.** An unqualified `AAA`, `AAA+` or `100% AAA+` is `[UNCONFIRMED]` by
definition and may be discarded by any reader:

```
AAA-C(bar=<named fetchable artefact>, critic=<fresh-context run ref>, rounds=<n>)
AAA-S(gate=<exact command>, red-observed=<sha|ts>, prod-observed-by=<agent that did not build it>)
```

Full doctrine: `skills/waterline/references/estate.md` — the fallback pack any project without
its own inherits. It grants no autonomy; the waterline still comes live from the project.


## Context and model changes

Before changing a model or prompt, read current official documentation for that exact provider/model and inspect the installed CLI/configuration. Keep task roles, hard constraints, privacy and included-capacity limits. API and subscription CLI paths require separate compatibility/access evidence. Record requested model, observed model, client version, input/output identity, usage availability and failures. Never replace unknown billing/usage with zero.

Use native compaction plus a small checkpoint: user objective and corrections; locked constraints/authority; current paths and revision; accepted decisions; source URLs and retrieval dates; tests/review tied to candidate; remaining work and next command. Keep native opaque compaction state unchanged. Retrieve relevant project/skill material when needed; do not paste every playbook into the initial prompt.

Compare representative old/new inputs in fresh sessions with the same task/model/effort and quality gates. Record correctness, completeness, interventions, latency and measured tokens where exposed. Reduced file bytes alone prove context reduction, not better output. Recheck on a model/client/workflow change.

## Known-fact recall

Use the existing 2nd Brain lookup before broad text search when it is installed. Locate the actual brain.js through the documented vault roots; never execute an empty glob result. On a miss, use a scoped search and record the missing index entry within the user's authorized scope. Resolve credential locations through skills/library/connections.md and bin/find-cred; never expose values.
