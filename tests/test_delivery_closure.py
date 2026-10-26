"""RA-8099: finish line must be able to fail on false Done."""
from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest

from app.server.delivery_closure import (
    Snapshot, Stage, assess, can_finish, closure_queue, project_can_close,
)


NOW = datetime(2026, 10, 27, 0, 30, tzinfo=timezone.utc)


def snapshot(**changes):
    base = Snapshot(
        issue_id="RA-8099", project_id="unite-mission",
        stage=Stage.REVIEW_WAIT, stage_since=NOW - timedelta(hours=3),
        owner="PC Worker", acceptance_passed=True, tests_passed=True,
        pr_head_sha="a" * 40, reviewed_head_sha="a" * 40,
        authorised_head_sha="a" * 40,
        merge_sha="b" * 40, deployed_sha="b" * 40,
        verified_sha="b" * 40,
    )
    return replace(base, **changes)


def codes(item):
    return [f.code for f in assess(item, NOW)]


def test_real_verified_release_may_close_only_at_verified_stage():
    item = snapshot(stage=Stage.VERIFIED_LIVE)
    assert can_finish(item)
    assert codes(item) == ["CLOSE_ELIGIBLE"]


@pytest.mark.parametrize("changed", [
    {"tests_passed": False},
    {"acceptance_passed": False},
    {"reviewed_head_sha": "z" * 40},
    {"authorised_head_sha": None},
    {"merge_sha": None},
    {"deployed_sha": "a" * 40},  # PR head is not the deployed merge commit
    {"verified_sha": None},
])
def test_false_done_caught_by_planted_missing_or_stale_receipt(changed):
    item = snapshot(stage=Stage.DONE, **changed)
    assert not can_finish(item)
    assert codes(item) == ["FALSE_DONE"]


def test_merge_not_done_without_live_receipt_after_six_hours():
    item = snapshot(stage=Stage.MERGED, stage_since=NOW - timedelta(hours=6),
                    deployed_sha=None, verified_sha=None)
    assert codes(item) == ["DEPLOY_UNVERIFIED"]


def test_three_day_unverified_deploy_also_escalates_to_founder():
    item = snapshot(stage=Stage.MERGED,
                    stage_since=NOW - timedelta(days=3),
                    deployed_sha=None, verified_sha=None)
    finding = assess(item, NOW)[0]
    assert finding.code == "DEPLOY_UNVERIFIED_24H"
    assert finding.severity == "founder"


def test_one_hour_review_reminder_and_four_hour_escalation():
    new = snapshot(stage_since=NOW - timedelta(minutes=20))
    assert codes(new) == []
    remind = snapshot(stage_since=NOW - timedelta(hours=2))
    assert codes(remind) == ["REVIEW_REMINDER"]
    escalate = snapshot(stage_since=NOW - timedelta(hours=5))
    assert codes(escalate) == ["STALE_4H"]


def test_three_day_review_must_reach_founder():
    item = snapshot(stage_since=NOW - timedelta(days=3))
    findings = assess(item, NOW)
    assert findings[0].code == "STALE_24H"
    assert findings[0].severity == "founder"


def test_missing_owner_escalated_immediately():
    item = snapshot(owner=None, stage_since=NOW)
    assert codes(item) == ["UNOWNED"]


def test_waiting_for_founder_approval_never_becomes_auto_approval():
    item = snapshot(stage=Stage.APPROVAL_WAIT,
                    stage_since=NOW - timedelta(days=3),
                    authorised_head_sha=None)
    assert codes(item) == ["HUMAN_APPROVAL_AGED"]
    assert not can_finish(item)


def test_repeat_scan_is_idempotent_and_revision_change_invalidates_alert_key():
    item = snapshot(stage_since=NOW - timedelta(hours=5))
    first = assess(item, NOW)[0]
    assert first.key == assess(item, NOW)[0].key
    changed = replace(item, pr_head_sha="c" * 40)
    assert first.key != assess(changed, NOW)[0].key


def test_project_cannot_close_with_missing_review_or_cancellation():
    a = snapshot(issue_id="RA-1", stage=Stage.DONE)
    b = snapshot(issue_id="RA-2", stage=Stage.REVIEW_WAIT)
    assert not project_can_close([a, b], expected_issue_ids={"RA-1", "RA-2"})
    assert not project_can_close([a], expected_issue_ids={"RA-1", "RA-2"})
    assert not project_can_close([a], expected_issue_ids=set())
    assert project_can_close([a], expected_issue_ids={"RA-1"})


def test_non_production_artifact_uses_receipt_not_fake_deployment():
    item = snapshot(delivery_kind="artifact", stage=Stage.VERIFIED_LIVE,
                    merge_sha=None, deployed_sha=None, verified_sha=None)
    assert not can_finish(item)
    item = replace(item, delivered_artifact_receipt="signed-acceptance-123")
    assert can_finish(item)


def test_closure_queue_prioritises_broken_done_and_old_reviews():
    new = snapshot(issue_id="RA-3", stage_since=NOW - timedelta(minutes=5))
    old = snapshot(issue_id="RA-4", stage_since=NOW - timedelta(days=3))
    bad = snapshot(issue_id="RA-5", stage=Stage.DONE, verified_sha=None)
    ordered = closure_queue([new, old, bad], NOW)
    assert [x.issue_id for x in ordered] == ["RA-5", "RA-4"]


def test_datetime_must_be_timezone_aware():
    with pytest.raises(ValueError, match="timezone"):
        assess(snapshot(), datetime(2026, 10, 27))


def test_blocked_is_not_done_and_has_explicit_owner():
    item = snapshot(stage=Stage.BLOCKED, blocked_reason="Waiting for human security approval")
    assert codes(item) == ["BLOCKED"]
    assert item.owner == "PC Worker"


def test_project_rejects_cancelled_failed_and_duplicate_required_issues():
    complete = snapshot(issue_id="RA-1", stage=Stage.DONE)
    cancelled = snapshot(issue_id="RA-2", stage=Stage.CANCELLED)
    failed = snapshot(issue_id="RA-2", stage=Stage.FAILED)
    assert not project_can_close([complete, cancelled], expected_issue_ids={"RA-1", "RA-2"})
    assert not project_can_close([complete, failed], expected_issue_ids={"RA-1", "RA-2"})
    assert not project_can_close([complete, replace(complete)], expected_issue_ids={"RA-1"})


def test_future_stage_timestamp_fails_closed():
    item = snapshot(stage_since=NOW + timedelta(minutes=6))
    assert codes(item) == ["INVALID_CLOCK"]


def test_unverified_live_stage_refuses_missing_production_receipt():
    item = snapshot(stage=Stage.VERIFIED_LIVE, verified_sha=None)
    assert codes(item) == ["UNVERIFIED_RELEASE"]


def test_merging_and_deploying_stages_need_correct_evidence():
    deploying = snapshot(stage=Stage.DEPLOYING, stage_since=NOW - timedelta(hours=6),
                         verified_sha=None)
    assert codes(deploying) == ["DEPLOY_UNVERIFIED"]
    merged = snapshot(stage=Stage.MERGED)
    assert codes(merged) == ["CHECK_ACCEPTANCE"]


def test_new_pending_approval_yields_no_automatic_transition():
    pending = snapshot(stage=Stage.APPROVAL_WAIT, stage_since=NOW,
                       authorised_head_sha=None)
    assert assess(pending, NOW) == ()


def test_artifact_done_requires_delivery_receipt():
    item = snapshot(stage=Stage.DONE, delivery_kind="artifact",
                    delivered_artifact_receipt=None)
    assert codes(item) == ["FALSE_DONE"]


def test_new_stage_invalidates_existing_alert_fingerprint():
    item = snapshot(stage_since=NOW - timedelta(hours=7))
    first = assess(item, NOW)[0]
    next_stage = replace(item, stage=Stage.TESTED)
    assert first.key != assess(next_stage, NOW)[0].key
