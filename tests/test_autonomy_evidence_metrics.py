"""Autonomy telemetry must describe observations, not invented delivery success."""

import pytest

from app.server.autonomy import _calc_effective_autonomy


@pytest.mark.parametrize("events", [[], [{"action": "poll", "found": 0}], [{"action": "session_started"}]])
def test_partial_or_missing_observations_have_no_composite_score(events):
    report = _calc_effective_autonomy(events)
    assert report["effective_autonomy_pct"] is None
    assert report["metric_scope"] == "poll_and_launch_only"


def test_launch_metric_does_not_claim_verified_delivery():
    report = _calc_effective_autonomy([
        {"action": "poll", "found": 2},
        {"action": "session_started"},
        {"action": "session_error"},
    ])
    assert report["effective_autonomy_pct"] == 50.0
    assert report["metric_scope"] == "poll_and_launch_only"
    assert report["sessions_started"] == 1
    assert report["session_errors"] == 1


def test_observed_failures_remain_zero():
    report = _calc_effective_autonomy([
        {"action": "poll_error"}, {"action": "session_error"},
    ])
    assert report["effective_autonomy_pct"] == 0.0


def test_blocked_admission_is_not_a_successful_launch():
    report = _calc_effective_autonomy([
        {"action": "poll", "found": 2}, {"action": "session_started"},
        {"action": "session_blocked"},
    ])
    assert report["effective_autonomy_pct"] == 50.0
    assert report["sessions_blocked"] == 1
