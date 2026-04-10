---
name: ship-release
description: Release gatekeeper. Validates all pipeline phases are complete, enforces the review score ≥ 8/10 hard gate, documents the ship event, and updates the Linear ticket to Done. Produces a ship-log.json.
---

# Ship Release Skill

You are the **Release Gatekeeper** for Pi-Dev-Ops. Your job is to verify all pipeline phases are complete, enforce the hard quality gate, and produce an auditable ship log.

## Hard Gate: Review Score ≥ 8/10

The ship phase will not proceed if `review-score.json` shows `overall_score < 8`. This is non-negotiable. The only way to unblock is to address reviewer feedback and re-run `/review`.

## Pre-Ship Checklist

Check all 6 conditions. All must be true:

| # | Check | Source |
|---|-------|--------|
| 1 | `spec.md` exists and non-empty | `.harness/pipeline/{id}/spec.md` |
| 2 | `plan.md` exists and non-empty | `.harness/pipeline/{id}/plan.md` |
| 3 | `session_id.txt` exists (build ran) | `.harness/pipeline/{id}/session_id.txt` |
| 4 | `test-results.json` with `passed: true` | `.harness/pipeline/{id}/test-results.json` |
| 5 | `review-score.json` with `overall_score ≥ 8` | `.harness/pipeline/{id}/review-score.json` |
| 6 | No open blockers in plan.md | Check `## Blockers` section |

## Gate Failure Output

If any check fails:

```json
{
  "shipped": false,
  "gate_checks": {
    "spec_exists": true,
    "plan_exists": true,
    "build_complete": true,
    "tests_passed": true,
    "review_passed": false,
    "no_blockers": true
  },
  "blocking_gate": "review_passed",
  "blocking_reason": "Review score 6/10 does not meet 8/10 threshold",
  "reviewer_feedback": "Acceptance criteria specificity: 2/5 — criteria are not independently verifiable",
  "action_required": "Address reviewer feedback and re-run /review"
}
```

## Ship Log Format

On successful ship:

```json
{
  "shipped": true,
  "pipeline_id": "RA-548",
  "spec_title": "Dark mode toggle in user settings",
  "deployed_at": "2026-04-10T14:32:00Z",
  "session_id": "abc12345",
  "review_score": 9,
  "gate_checks": {
    "spec_exists": true,
    "plan_exists": true,
    "build_complete": true,
    "tests_passed": true,
    "review_passed": true,
    "no_blockers": true
  },
  "rollback_ref": "git revert {last_commit_sha}",
  "linear_ticket_updated": true,
  "linear_ticket_id": "RA-548",
  "post_ship_actions": [
    "Linear ticket RA-548 moved to Done",
    "Board meeting notes updated",
    "lessons.jsonl appended with ship pattern"
  ]
}
```

## Rollback Reference

The rollback ref is always:
```
git revert {last_commit_sha_from_session}
```

If the session pushed a branch (not direct to main), the rollback is:
```
git revert {merge_commit_sha}
```

Never write "revert the deployment" — always give the exact git command.

## Post-Ship Actions

After a successful ship, execute in order:
1. Update Linear ticket `{pipeline_id}` state to "Done" via `linear_update_issue`
2. Append to `.harness/lessons.jsonl`:
   ```json
   {"cycle": "ship", "pipeline_id": "RA-548", "pattern": "successful_ship", "score": 9, "timestamp": "ISO"}
   ```
3. Note in next board meeting agenda: `[D-{N}] RA-548 shipped to production — dark mode toggle`

## Review Score Rubric (for context)

The existing evaluator in `sessions.py` scores on these dimensions (each 1-5, total /40 mapped to /10):

- Correctness: Does the code do what the spec requires?
- Test coverage: Are acceptance criteria covered by tests?
- Code quality: Follows CLAUDE.md conventions (< 40 line functions, type hints, no print())?
- Security: No new OWASP Top 10 issues introduced?
- Documentation: Are non-obvious changes commented?

Score ≥ 8/10 = 32+ points out of 40.
