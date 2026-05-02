---
name: margot-sandcastle-bridge
description: After a Margot Deep Research finding completes, classify "action-shaped vs informational" via existing intent_router, draft a Linear ticket body, route through draft_review HITL gate. On 👍, create the Linear issue with `sandcastle:high-isolation` + `pi-dev:autonomous` labels. The existing autonomy.py poller picks it up and the sandcastle-runner skill executes the work in an isolated container. Closes Wave 5 #4 (RA-1856 epic). This is what makes Margot autonomous.
owner_role: Margot (research) → Chief of Staff (HITL) → Builder (execution)
status: wave-5
---

# margot-sandcastle-bridge

The intent layer between **Margot proposes** and **Sandcastle disposes**. Without this, Margot's research is a text artefact that the founder reads and forgets. With this, every research finding either becomes a tracked action (with founder veto) or is logged as informational and recycled into the lessons corpus.

## Why this exists

Today (Wave 1 — DONE):
- Margot does deep research, returns text via `mcp__margot__deep_research_max` (async) or `deep_research` (sync)
- `swarm/margot_tools.py` is the bridge primitive
- The output lands in `.harness/swarm/margot_inflight.jsonl` for async runs, or returned directly for sync
- **There's nothing that converts a research finding into action**

This skill closes that loop. The four critical safety rails:

1. **Intent classification** — not every research finding should become an action. The `intent_router` (existing) classifies as `action-shaped | informational | unknown`. Below confidence 0.75 → never route to action.
2. **HITL gate** — every action drafts a Linear ticket BODY first; founder must 👍 in Telegram before any Linear issue is actually created.
3. **Single chokepoint** — the bridge does NOT directly call Sandcastle. It hands the ticket to the existing `autonomy.py` poller which already has rate-limit, idempotency, scope-violation enforcement.
4. **Reversibility** — failed Margot intents never silently leak into the codebase. Rejection / expiry / classification-too-low all write to `.harness/swarm/margot_intents.jsonl` for the lessons engine.

## Topology

```
Margot deep_research_max returns interaction_id
  ↓
swarm/orchestrator polls margot_inflight.jsonl every cycle
  ↓
margot_tools.check_research(interaction_id) → status=complete
  ↓
margot-sandcastle-bridge.process_completed_research():
  ├── load research body from .harness/swarm/margot_complete.jsonl
  ├── intent_router.classify(body) → {intent, confidence, ...}
  ├── if intent != "action_shaped" or confidence < 0.75:
  │     → log to margot_intents.jsonl as "informational"
  │     → optionally: scribe.draft_summary() for Telegram (existing path)
  │     → STOP
  ├── else: # action-shaped, confidence >= 0.75
  │     → extract: target_repo, proposed_action, proposed_branch, complexity_tier
  │     → render Linear ticket body using template
  │     → draft_review.post_draft(
  │           draft_text=<ticket_body>,
  │           drafted_by_role="Margot",
  │           originating_intent_id=<interaction_id>,
  │           destination_kind="linear_issue",  # NEW field, Wave 5 #5
  │           destination_meta={
  │             "team": "RestoreAssist",
  │             "project": <project_name>,
  │             "labels": ["pi-dev:autonomous", "sandcastle:high-isolation", "margot:originated"],
  │             "status": "Ready for Pi-Dev",
  │           }
  │         )
  │     → audit_emit.row("margot_intent_drafted", ...)
  ↓
draft_review.post_draft persists the draft + posts to Telegram REVIEW_CHAT_ID
  ↓
Founder sees draft, reacts:
  ├── 👍 → draft_review.mark_reaction triggers _do_send_for_linear():
  │           → calls mcp_linear_create_issue with the rendered body + labels + status
  │           → audit_emit.row("margot_intent_accepted", linear_issue_id=..., ...)
  │           → existing autonomy.py poller picks it up next cycle
  │           → existing session_phases.run_build branches on label → sandcastle-runner
  ├── ❌ → audit_emit.row("margot_intent_rejected", reason=<text>, ...)
  │        log to .harness/swarm/margot_intents.jsonl
  │        DO NOT create Linear issue
  ├── ⏳ → defer 24h (existing draft_review behaviour)
  └── 24h timeout → mark expired, log, do nothing
```

## The classification step

`intent_router.classify(text)` (existing, Wave 1) returns one of 6 intents. For Margot research output, only one matters: `action_shaped`. The rest route to informational.

`action_shaped` heuristics (documented in intent_router SKILL.md):
- Verbs: "should", "must", "needs to", "implement", "add", "fix", "update", "remove"
- Subject pattern: a specific code surface ("the Stripe webhook", "Cloudinary upload route", "iOS billing code path")
- Outcome: a measurable state change

Below confidence 0.75 → bridge defaults to informational, drafts a Telegram summary via Scribe (existing), and stops. This is conservative on purpose. False positives on action-shaped trigger HITL friction.

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
- Match against `.harness/projects.json` repo names
- Fallback: ask the founder via the draft body itself ("Confirm target repo? Detected: [list of candidates]")

## Why two-step (draft → ticket → poll → run) instead of direct

Reuses existing infrastructure that's already battle-tested:
- `draft_review` — HITL gate with pii-redactor, kill-switch awareness, expiry handling
- `autonomy.py` — Linear pickup with idempotency, rate-limit, orphan recovery, scope-violation enforcement
- `session_phases.run_build` — phase orchestration with audit trail, evaluator, push, smoke loop
- `sandcastle-runner` — execution with concurrency cap, secret hygiene, kill-switch

Going direct from Margot to Sandcastle would reinvent every one of those. The plan agent flagged this as a critical anti-pattern.

## Contract

### Input (per-research-completion)

```python
class MargotResearchCompletion:
    interaction_id: str
    body: str  # the research output from Margot
    originated_at: str  # ISO timestamp
    originating_session_id: str  # Pi-CEO session that requested the research
```

### Output (per-research-completion)

```python
class MargotIntentResult:
    interaction_id: str
    classification: Literal["action_shaped", "informational", "unknown"]
    confidence: float
    action_summary: str | None  # populated when action_shaped
    target_repo: str | None  # populated when action_shaped
    draft_id: str | None  # populated when action_shaped + draft posted
    skipped_reason: str | None  # populated when not action_shaped
```

### Output (post-reaction, when 👍)

```python
class MargotActionAccepted:
    interaction_id: str
    draft_id: str
    linear_issue_id: str  # the newly created issue
    linear_issue_identifier: str  # e.g. "RA-1900"
    labels_applied: list[str]
```

## State files

- `.harness/swarm/margot_intents.jsonl` — append-only ledger of every classified Margot research output
  - Fields: `ts`, `interaction_id`, `classification`, `confidence`, `outcome` (informational | drafted | accepted | rejected | expired), `linear_issue_id?`, `draft_id?`
- Existing `.harness/swarm/margot_inflight.jsonl` — unchanged
- Existing `.harness/swarm/margot_complete.jsonl` — unchanged
- Existing `.harness/swarm/telegram_drafts.json` — unchanged (draft_review owns this)
- Existing `.harness/swarm.jsonl` — unchanged (audit_emit owns this)

## Audit events emitted

Add to `swarm/audit_emit.py::_VALID_TYPES` (additive):

```python
# Wave 5 / RA-1856 — Margot bridge
"margot_intent_classified",  # one per completion; fields: interaction_id, classification, confidence
"margot_intent_drafted",     # one per action-shaped + draft posted
"margot_intent_accepted",    # one per 👍 → Linear issue created
"margot_intent_rejected",    # one per ❌
"margot_intent_expired",     # one per 24h timeout
```

## Safety bindings

- **PII redactor** runs automatically on every `draft_review.post_draft` (per Wave 1/2 wiring). Margot research bodies often contain customer names, internal URLs, vendor names — all redacted at strictness=standard before reaching Telegram.
- **Confidence floor** — below 0.75 never routes to action. Logged.
- **Action verb scrubber** — research bodies that contain verbs like "delete", "drop", "destructive" require confidence ≥ 0.90 (stricter). Configurable via `MARGOT_DESTRUCTIVE_VERBS` env var.
- **Repo allowlist** — `target_repo` must be in `.harness/projects.json`. Margot can't propose action against a repo Pi-CEO doesn't know about.
- **Rate limit** — max 5 Margot-originated drafts per 24-hour window. Above that, queue. Prevents accidental flood from a Margot run that returns 50 action-shaped findings.
- **Loop detection** — if the same `interaction_id` was previously rejected, drafts for it are auto-suppressed for 7 days.

## When NOT to use this skill

- For research that's pure intel (e.g. "what's the latest on X library?") — those route to Scribe → Telegram summary, no action.
- For research that's a research follow-up (e.g. "do another deep dive on Y") — those route directly to a new `mcp__margot__deep_research_max` call, no Linear ticket.
- For founder-originated requests (founder asked Margot directly) — those should already have an action context; bridge runs only on autonomous Margot runs (e.g. cron-scheduled Margot research).

## Verification (Wave 5 #4 close-out)

1. **Compile + import smoke** — `python -m py_compile swarm/margot_sandcastle.py` green.
2. **Classification smoke** — paste 10 synthetic Margot research outputs (3 action-shaped, 3 informational, 2 unknown, 2 ambiguous) into `process_completed_research()`. Verify ≥8/10 classified correctly with confidence consistent with expectation.
3. **Action-shaped + 👍 path (TEST_MODE)** — synthetic research → drafts Linear body → `draft_review.mark_reaction("👍")` → mock `linear_create_issue` returns RA-VERIFY-1 → `margot_intent_accepted` audit row → ledger row written.
4. **Action-shaped + ❌ path** — same synthetic, but `mark_reaction("❌")` → `margot_intent_rejected` audit row → no Linear issue created → ledger row written.
5. **Informational path** — synthetic research with no action verbs → confidence-too-low → `margot_intent_classified` row only, no draft posted.
6. **Destructive verb gate** — synthetic research containing "delete the customers table" with confidence 0.80 → suppressed (below the 0.90 destructive threshold).
7. **Repo allowlist** — synthetic research targeting `random/repo-not-in-portfolio` → `margot_intent_rejected` with reason `repo_not_allowed`.
8. **Rate limit** — fire 6 action-shaped drafts in 24h → 6th queues with status `queued_rate_limit`.
9. **Loop detection** — reject draft for `interaction_id=X`; immediately re-classify same → suppressed with reason `recently_rejected`.

## Out of scope for Wave 5 #4

- The `destination_kind="linear_issue"` extension to `draft_review` (Wave 5 #5)
- The new audit event types (added in Wave 5 #1 + this skill, both ship together)
- The actual Sandcastle execution (Wave 5 #1)
- The autonomy.py label pickup (Wave 5 #6 + #7)

## References

- Existing Margot bridge (research-only): `Pi-Dev-Ops/skills/margot-bridge/SKILL.md` + `swarm/margot_tools.py`
- Existing intent router: `Pi-Dev-Ops/skills/intent-parser/SKILL.md` + `swarm/intent_router.py`
- Existing draft review: `swarm/draft_review.py` (Wave 5 #5 extends with `destination_kind`)
- Existing autonomy poller: `app/server/autonomy.py`
- Approved plan: `/Users/phill-mac/.claude/plans/breezy-wiggling-map.md`
- Companion skill: `sandcastle-runner` (the executor)
- Companion skill: `vercel-env-puller` (secrets feed for the executor)
- Parent epic: <issue id="RA-1856">RA-1856</issue>
- Margot bug fix: <issue id="RA-1855">RA-1855</issue> (deep_research_max system_instruction)
