Moved from SKILL.md. Read when closing out or re-verifying the bridge, or checking what is out of scope.

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
