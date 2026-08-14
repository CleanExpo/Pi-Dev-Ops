"""
test_ra7216_acceptance_events.py — RA-7216 slice 2 unit tests.

Covers the acceptance-event path that makes first-pass acceptance,
trigger-to-accepted-outcome and review latency measurable:

  - parse_linear_event emits issue_completed on terminal transitions
  - "completed" and "canceled" are BOTH captured, distinguished by state_type
  - occurred_at falls back to updatedAt when completedAt is absent
  - no regression on the pre-existing issue_started / issue_created triggers
  - record_acceptance patches only rows whose accepted_at is still null
  - log_gate_check carries linear_issue_id (the join key)
  - score_c1 never reports a fabricated 24h survival rate
  - score_c2 reads terminal outcomes, not the hardcoded "In Review" literal

All Supabase HTTP is mocked. No live network in CI.

MUTATION CONTROLS — each of these should fail if the corresponding fix is
reverted, and they are noted per-test rather than in a block so a reviewer can
check them one at a time.
"""
import importlib.util
from unittest.mock import patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _linear_payload(state_type, state_name="Done", action="update",
                    completed_at="2026-08-14T05:00:00Z",
                    updated_at="2026-08-14T05:00:01Z",
                    with_state_id=True, priority=0):
    data = {
        "id": "issue-abc",
        "title": "Ship the thing",
        "description": "repo: https://github.com/CleanExpo/Pi-Dev-Ops",
        "state": {"type": state_type, "name": state_name},
        "updatedAt": updated_at,
        "priority": priority,
    }
    if completed_at is not None:
        data["completedAt"] = completed_at
    payload = {"type": "Issue", "action": action, "data": data}
    if with_state_id:
        payload["updatedFrom"] = {"stateId": "prev-state"}
    return payload


def _load_scorer():
    """Load zte_v2_score.py by path — it is a script, not an importable module."""
    spec = importlib.util.spec_from_file_location(
        "zte_v2_score", "scripts/zte_v2_score.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── parse_linear_event: the terminal branch ───────────────────────────────────

def test_completed_transition_emits_issue_completed():
    """MUTATION CONTROL: delete the _TERMINAL_STATE_TYPES branch → this fails."""
    from app.server.webhook import parse_linear_event

    event = parse_linear_event(_linear_payload("completed"))
    assert event is not None
    assert event["event"] == "issue_completed"
    assert event["state_type"] == "completed"
    assert event["state_name"] == "Done"
    assert event["occurred_at"] == "2026-08-14T05:00:00Z"
    assert event["issue_id"] == "issue-abc"


def test_canceled_transition_is_captured_as_a_rejection():
    """A cancelled issue is a terminal OUTCOME, not a non-event.

    Recording only acceptances would give C2 a numerator with no denominator —
    the shape of the original defect. state_type is what separates the two.
    """
    from app.server.webhook import parse_linear_event

    event = parse_linear_event(_linear_payload("canceled", "Cancelled"))
    assert event["event"] == "issue_completed"
    assert event["state_type"] == "canceled"


def test_occurred_at_falls_back_to_updated_at():
    """Cancelled issues may carry no completedAt; without a fallback the row is
    silently unmeasurable because latency arithmetic has no end point."""
    from app.server.webhook import parse_linear_event

    event = parse_linear_event(
        _linear_payload("canceled", "Cancelled", completed_at=None)
    )
    assert event["occurred_at"] == "2026-08-14T05:00:01Z"


# ── no regression on the existing triggers ────────────────────────────────────

def test_started_transition_still_emits_issue_started():
    """NEGATIVE CONTROL. Without this, 'always return issue_completed' passes
    the terminal tests above."""
    from app.server.webhook import parse_linear_event

    event = parse_linear_event(_linear_payload("started", "In Progress"))
    assert event["event"] == "issue_started"


def test_non_terminal_non_started_transition_is_still_skipped():
    from app.server.webhook import parse_linear_event

    assert parse_linear_event(_linear_payload("unstarted", "Todo")) is None


def test_update_without_state_change_is_still_skipped():
    from app.server.webhook import parse_linear_event

    assert parse_linear_event(
        _linear_payload("completed", with_state_id=False)
    ) is None


def test_high_priority_create_still_triggers():
    """RA-888's create trigger must survive the restructure."""
    from app.server.webhook import parse_linear_event

    event = parse_linear_event(
        _linear_payload("unstarted", "Todo", action="create",
                        with_state_id=False, priority=1)
    )
    assert event is not None
    assert event["event"] == "issue_created"


# ── record_acceptance ─────────────────────────────────────────────────────────

def test_record_acceptance_patches_only_unaccepted_rows():
    """MUTATION CONTROL: drop `&accepted_at=is.null` → this fails.

    First terminal transition wins. A reopened-then-reclosed issue is rework and
    must not be able to overwrite the original outcome and pass itself off as a
    clean first pass. It also makes a retried webhook idempotent.
    """
    from app.server import supabase_log

    captured = {}

    def fake_patch(table, filter_param, patch_body):
        captured.update(table=table, filter=filter_param, body=patch_body)
        return True

    with patch.object(supabase_log, "_patch", side_effect=fake_patch):
        ok = supabase_log.record_acceptance(
            linear_issue_id="issue-abc",
            state_name="Done",
            state_type="completed",
            occurred_at="2026-08-14T05:00:00Z",
        )

    assert ok is True
    assert captured["table"] == "gate_checks"
    assert "linear_issue_id=eq.issue-abc" in captured["filter"]
    assert "accepted_at=is.null" in captured["filter"]
    assert captured["body"]["accepted_at"] == "2026-08-14T05:00:00Z"
    assert captured["body"]["accepted_state_type"] == "completed"
    assert captured["body"]["accepted_state"] == "Done"


def test_record_acceptance_stamps_now_when_no_timestamp_supplied():
    from app.server import supabase_log

    captured = {}
    with patch.object(supabase_log, "_patch",
                      side_effect=lambda t, f, b: captured.update(body=b) or True):
        supabase_log.record_acceptance(
            linear_issue_id="issue-abc", state_name="Done",
            state_type="completed", occurred_at=None,
        )
    assert captured["body"]["accepted_at"]  # non-empty ISO string


def test_record_acceptance_rejects_missing_identifiers():
    """Never issue a PATCH with an empty filter — that would stamp every row."""
    from app.server import supabase_log

    with patch.object(supabase_log, "_patch") as mock_patch:
        assert supabase_log.record_acceptance(
            linear_issue_id="", state_name="Done", state_type="completed") is False
        assert supabase_log.record_acceptance(
            linear_issue_id="issue-abc", state_name="Done", state_type="") is False
    mock_patch.assert_not_called()


def test_record_acceptance_is_non_fatal_on_supabase_failure():
    """Observability must never raise into the webhook handler."""
    from app.server import supabase_log

    with patch.object(supabase_log, "_patch", return_value=False):
        assert supabase_log.record_acceptance(
            linear_issue_id="issue-abc", state_name="Done",
            state_type="completed") is False


# ── the join key ──────────────────────────────────────────────────────────────

def test_log_gate_check_carries_linear_issue_id():
    """MUTATION CONTROL: drop the linear_issue_id passthrough → this fails.

    Without the join key an acceptance event has no gate_checks row to attach to
    and every downstream metric stays unmeasurable.
    """
    from app.server import supabase_log

    captured = {}
    with patch.object(supabase_log, "_insert",
                      side_effect=lambda t, r: captured.update(row=r) or True):
        supabase_log.log_gate_check(
            pipeline_id="p1", session_id="s1",
            gate_checks={"spec_exists": True}, review_score=8.0, shipped=True,
            linear_issue_id="issue-abc",
        )
    assert captured["row"]["linear_issue_id"] == "issue-abc"


def test_log_gate_check_omits_the_key_when_absent():
    """A session with no Linear issue must not write an empty join key —
    `linear_issue_id=eq.` would otherwise match it from an unrelated event."""
    from app.server import supabase_log

    captured = {}
    with patch.object(supabase_log, "_insert",
                      side_effect=lambda t, r: captured.update(row=r) or True):
        supabase_log.log_gate_check(
            pipeline_id="p1", session_id="s1",
            gate_checks={"spec_exists": True}, review_score=8.0, shipped=True,
            linear_issue_id=None,
        )
    assert "linear_issue_id" not in captured["row"]


# ── scorer honesty ────────────────────────────────────────────────────────────

def test_c1_never_reports_a_survival_score():
    """MUTATION CONTROL: restore the shipped/total proxy → this fails.

    RA-7216's first guardrail forbids presenting shipped/total as a 24h rollback
    measure. Until rollback telemetry exists C1 must be needs_data at any ship
    rate, including a perfect one.
    """
    z = _load_scorer()
    for rows in ([{"shipped": True}] * 20,
                 [{"shipped": True}] * 19 + [{"shipped": False}],
                 []):
        score, note = z.score_c1_deployment_success(rows)
        assert score == 1, f"C1 scored {score} without rollback data"
        assert "needs_data" in note
    # the ship rate survives as an explicitly-labelled diagnostic
    _, note = z.score_c1_deployment_success([{"shipped": True}] * 20)
    assert "DIAGNOSTIC ONLY" in note


def test_c2_treats_the_old_in_review_literal_as_unknown():
    """MUTATION CONTROL: restore "in review" to the accepted-states set → fails.

    These are exactly the rows the old scorer returned 5/5 on: linear_state_after
    is the hardcoded "In Review" literal, written at push time and never updated.
    They carry no terminal outcome, so acceptance is unknown — not 100%.
    """
    z = _load_scorer()
    z._supabase_query = lambda *a, **k: [
        {"shipped": True, "linear_state_after": "In Review"}] * 12
    score, note = z.score_c2_output_acceptance(30)
    assert score == 1
    assert "needs_data" in note


def test_c2_scores_real_terminal_outcomes():
    z = _load_scorer()
    done = {"shipped": True, "accepted_at": "t", "accepted_state_type": "completed"}
    killed = {"shipped": True, "accepted_at": "t", "accepted_state_type": "canceled"}
    z._supabase_query = lambda *a, **k: [done] * 9 + [killed]
    score, note = z.score_c2_output_acceptance(30)
    assert score == 5
    assert "9/10" in note


def test_c2_can_detect_total_rejection():
    """The old implementation structurally could not score below 5/5 on the
    Supabase path — every surviving row said 'In Review' and counted as
    accepted. This is the case that proves the new one can register failure."""
    z = _load_scorer()
    killed = {"shipped": True, "accepted_at": "t", "accepted_state_type": "canceled"}
    z._supabase_query = lambda *a, **k: [killed] * 8
    score, note = z.score_c2_output_acceptance(30)
    assert score == 1
    assert "0/8" in note


def test_c2_excludes_still_open_issues_from_both_sides():
    """Open issues must not dilute the denominator; their outcome is unknown."""
    z = _load_scorer()
    done = {"shipped": True, "accepted_at": "t", "accepted_state_type": "completed"}
    z._supabase_query = lambda *a, **k: [done] * 6 + [{"shipped": True}] * 50
    score, note = z.score_c2_output_acceptance(30)
    assert "6/6" in note
    assert score == 5


def test_c2_enforces_a_sample_floor():
    """MUTATION CONTROL: delete the _C2_MIN_SAMPLE guard → this fails.

    One accepted issue is 1/1 = 100%, which lands the whole card in the top band
    off a single data point. A metric that changes a routing decision wrongly is
    worse than one that abstains.
    """
    z = _load_scorer()
    done = {"shipped": True, "accepted_at": "t", "accepted_state_type": "completed"}
    for n in range(1, z._C2_MIN_SAMPLE):
        z._supabase_query = lambda *a, _n=n, **k: [done] * _n
        score, note = z.score_c2_output_acceptance(30)
        assert score == 1, f"n={n} scored {score} below the floor"
        assert "needs_data" in note and "DIAGNOSTIC ONLY" in note
    # at the floor it becomes a real score
    z._supabase_query = lambda *a, **k: [done] * z._C2_MIN_SAMPLE
    assert z.score_c2_output_acceptance(30)[0] == 5
