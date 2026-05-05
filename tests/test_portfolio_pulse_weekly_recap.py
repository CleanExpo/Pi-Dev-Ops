"""tests/test_portfolio_pulse_weekly_recap.py — RA-2006 regression coverage.

Friday 8am AEST week-in-review briefing:

  * `lookback_window()` context manager scopes the window for one pulse run
    and restores the previous value on exit (idempotent, nesting-safe).
  * Section providers (github, linear) honour the active lookback when
    rendering the body — labels switch from "last 24h" to "last 7 days"
    at the 168h boundary.
  * Cron trigger config plumbs `lookback_hours: 168` and
    `deliver_telegram: true` into `_fire_portfolio_pulse_trigger`, which
    composes a weekly digest and calls `deliver_to_telegram`.
  * Friday 8am AEST is encoded as `weekday=3, hour=22, minute=0` UTC
    (Thursday 22:00 UTC). Verified end-to-end against the cron matcher.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import portfolio_pulse  # noqa: E402


# ── lookback_window() context manager ────────────────────────────────────────


def test_default_lookback_is_24h():
    assert portfolio_pulse.get_lookback_hours() == 24


def test_lookback_window_scopes_the_value():
    assert portfolio_pulse.get_lookback_hours() == 24
    with portfolio_pulse.lookback_window(168):
        assert portfolio_pulse.get_lookback_hours() == 168
    # Restored
    assert portfolio_pulse.get_lookback_hours() == 24


def test_lookback_window_restores_on_exception():
    """Exception inside the block must NOT leak the wider window."""
    assert portfolio_pulse.get_lookback_hours() == 24
    with pytest.raises(RuntimeError):
        with portfolio_pulse.lookback_window(168):
            assert portfolio_pulse.get_lookback_hours() == 168
            raise RuntimeError("boom")
    assert portfolio_pulse.get_lookback_hours() == 24


def test_lookback_window_nesting():
    """Nested context managers compose correctly."""
    with portfolio_pulse.lookback_window(72):
        assert portfolio_pulse.get_lookback_hours() == 72
        with portfolio_pulse.lookback_window(168):
            assert portfolio_pulse.get_lookback_hours() == 168
        assert portfolio_pulse.get_lookback_hours() == 72
    assert portfolio_pulse.get_lookback_hours() == 24


def test_lookback_window_clamps_negative_to_one():
    with portfolio_pulse.lookback_window(-5):
        assert portfolio_pulse.get_lookback_hours() == 1


# ── Section rendering: window labels ─────────────────────────────────────────


def test_github_render_deploys_daily_label():
    from swarm import portfolio_pulse_github as gh

    body = gh._render_deploys([], lookback_hours=24)
    assert "last 24h" in body
    assert "last 7 days" not in body


def test_github_render_deploys_weekly_label():
    from swarm import portfolio_pulse_github as gh

    body = gh._render_deploys([], lookback_hours=168)
    assert "last 7 days" in body


def test_github_render_deploys_weekly_caps_at_12():
    from swarm import portfolio_pulse_github as gh

    deploys = [
        {"sha": f"abc{i:03d}", "author": "phill",
         "deploy_status": "success", "message": f"commit {i}"}
        for i in range(20)
    ]
    body_daily = gh._render_deploys(deploys, lookback_hours=24)
    body_weekly = gh._render_deploys(deploys, lookback_hours=168)
    # Daily caps at 5
    assert body_daily.count("- `") <= 6  # 1 header + up to 5 entries
    # Weekly caps at 12
    assert body_weekly.count("- `") <= 13  # 1 header + up to 12 entries
    assert "and 8 more" in body_weekly  # 20 - 12 = 8


def test_github_render_ci_weekly_label():
    from swarm import portfolio_pulse_github as gh

    body = gh._render_ci(
        {"pass_count": 3, "fail_count": 1, "recent_failures": []},
        lookback_hours=168,
    )
    assert "last 7 days" in body


def test_linear_render_section_weekly_includes_closed_list():
    from swarm import portfolio_pulse_linear as lin

    movement = {
        "opened": [],
        "closed": [
            {"identifier": "RA-100", "title": "Ship feature X",
             "priority": 2, "state": {"type": "completed"}},
            {"identifier": "RA-101", "title": "Fix bug Y",
             "priority": 3, "state": {"type": "completed"}},
        ],
        "blocked": [],
        "stale": [],
    }
    body_daily = lin._render_section(movement, lookback_hours=24)
    body_weekly = lin._render_section(movement, lookback_hours=168)
    # Daily mode just shows the count
    assert "Ship feature X" not in body_daily
    # Weekly mode lists each closed ticket — that's the "wins this week" surface
    assert "Ship feature X" in body_weekly
    assert "Fix bug Y" in body_weekly
    # Both render the window label correctly
    assert "last 24h" in body_daily
    assert "last 7 days" in body_weekly


# ── cron-triggers.json: Friday entry shape ───────────────────────────────────


def test_friday_weekly_recap_entry_present():
    """The cron-triggers.json must contain a Friday weekly recap entry
    with the correct UTC weekday/hour mapping for Fri 08:00 AEST."""
    triggers_path = REPO_ROOT / ".harness" / "cron-triggers.json"
    triggers = json.loads(triggers_path.read_text())
    friday = next(
        (t for t in triggers if t.get("id") == "weekly-recap-friday"),
        None,
    )
    assert friday is not None, "weekly-recap-friday entry missing"
    assert friday["type"] == "portfolio_pulse"
    # Critical: weekday=3 (Thursday UTC) + hour=22 = Friday 08:00 AEST.
    # Off-by-one here would silently fire on the wrong day.
    assert friday["weekday"] == 3, (
        "weekday must be 3 (Thursday UTC); cron uses datetime.utcnow().weekday()"
    )
    assert friday["hour"] == 22
    assert friday["minute"] == 0
    assert friday["lookback_hours"] == 168
    assert friday["deliver_telegram"] is True
    assert friday["enabled"] is True


def test_cron_matcher_fires_friday_entry_at_thursday_2200_utc():
    """End-to-end: simulate the cron loop's _matches() at the Thursday 22:00
    UTC instant and confirm the Friday entry fires."""
    from app.server.cron_triggers import _matches

    # Pick any actual Thursday 2026-05-07 22:00 UTC
    thursday_22_utc = datetime(2026, 5, 7, 22, 0, 0, tzinfo=timezone.utc)
    assert thursday_22_utc.weekday() == 3  # Thursday

    triggers_path = REPO_ROOT / ".harness" / "cron-triggers.json"
    triggers = json.loads(triggers_path.read_text())
    friday = next(t for t in triggers if t["id"] == "weekly-recap-friday")

    fires = _matches(
        friday,
        now_hour=thursday_22_utc.hour,
        now_minute=thursday_22_utc.minute,
        now_weekday=thursday_22_utc.weekday(),
    )
    assert fires is True, "weekly-recap-friday must fire at Thursday 22:00 UTC"


def test_cron_matcher_does_not_fire_other_times():
    from app.server.cron_triggers import _matches

    triggers_path = REPO_ROOT / ".harness" / "cron-triggers.json"
    triggers = json.loads(triggers_path.read_text())
    friday = next(t for t in triggers if t["id"] == "weekly-recap-friday")

    # Wrong weekday (Wednesday)
    assert _matches(friday, now_hour=22, now_minute=0, now_weekday=2) is False
    # Wrong hour (21:00)
    assert _matches(friday, now_hour=21, now_minute=0, now_weekday=3) is False
    # Wrong minute (22:30)
    assert _matches(friday, now_hour=22, now_minute=30, now_weekday=3) is False
