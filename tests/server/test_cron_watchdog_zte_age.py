"""tests/server/test_cron_watchdog_zte_age.py — ZTE age-aware watchdog.

Regression coverage for the bug where 10 freshly filed ATIA tickets were counted
toward the stall alarm, producing a misleading "Pipeline Stalled 51h" alert
30 minutes after Phill filed them. The watchdog now:

  * only counts tickets older than ``_MIN_TICKET_AGE_H`` toward the stall;
  * reports the *oldest waiting ticket's* age, not the time since the watchdog
    first noticed the stall;
  * sleeps on an escalating cadence the older the stall gets (per
    ~/.claude/projects/-Users-phill-mac-2nd-Brain/memory/feedback_no_repeating_alerts.md).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.server.cron_watchdog_zte import (
    _alert_cooldown_for_age,
    _filter_aged,
    _oldest_age_hours,
)


def _ticket(hours_ago: float, identifier: str = "UNI-1") -> dict:
    """Build a Linear-shaped ticket dict whose createdAt is ``hours_ago`` hours old."""
    created = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {
        "identifier": identifier,
        "createdAt": created.isoformat().replace("+00:00", "Z"),
        "priority": 1,
        "state": {"type": "unstarted", "name": "Todo"},
    }


# ── _filter_aged ──────────────────────────────────────────────────────────────


def test_filter_aged_all_fresh_returns_empty():
    """10 tickets all filed within the last hour — none should pass a 24h filter."""
    fresh = [_ticket(hours_ago=0.5, identifier=f"UNI-{2000 + i}") for i in range(10)]
    assert _filter_aged(fresh, min_age_hours=24.0) == []


def test_filter_aged_mix_returns_only_aged_ones():
    """Mixed batch: 3 fresh (<24h), 2 aged (>24h). Only the aged pair survives."""
    tickets = [
        _ticket(hours_ago=0.5, identifier="UNI-fresh-1"),
        _ticket(hours_ago=25.0, identifier="UNI-aged-1"),
        _ticket(hours_ago=2.0, identifier="UNI-fresh-2"),
        _ticket(hours_ago=72.0, identifier="UNI-aged-2"),
        _ticket(hours_ago=10.0, identifier="UNI-fresh-3"),
    ]
    aged = _filter_aged(tickets, min_age_hours=24.0)
    ids = sorted(t["identifier"] for t in aged)
    assert ids == ["UNI-aged-1", "UNI-aged-2"]


def test_filter_aged_missing_createdat_is_kept_defensively():
    """Defensive: an unknown-age ticket (no createdAt) is kept so an API shape
    change cannot silently suppress a real stall."""
    tickets = [
        {"identifier": "UNI-no-ts", "priority": 1, "state": {"type": "unstarted", "name": "Todo"}},
        _ticket(hours_ago=0.1, identifier="UNI-fresh"),
    ]
    aged = _filter_aged(tickets, min_age_hours=24.0)
    assert [t["identifier"] for t in aged] == ["UNI-no-ts"]


# ── _oldest_age_hours ─────────────────────────────────────────────────────────


def test_oldest_age_hours_empty_list_returns_zero():
    assert _oldest_age_hours([]) == 0.0


def test_oldest_age_hours_returns_max_age():
    """With ages 5h, 50h, 100h — answer must be ~100h (within tolerance for clock drift)."""
    tickets = [
        _ticket(hours_ago=5.0),
        _ticket(hours_ago=50.0),
        _ticket(hours_ago=100.0),
    ]
    oldest = _oldest_age_hours(tickets)
    assert 99.9 < oldest < 100.1


# ── _alert_cooldown_for_age ───────────────────────────────────────────────────


def test_alert_cooldown_for_age_escalates():
    """30h → 6h cadence; 72h → 24h cadence; 200h → 72h cadence."""
    assert _alert_cooldown_for_age(30.0) == 6.0
    assert _alert_cooldown_for_age(72.0) == 24.0
    assert _alert_cooldown_for_age(200.0) == 72.0
