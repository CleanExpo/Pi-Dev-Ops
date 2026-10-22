"""Mission Control must show what is happening: a failed read is never a zero.

Two defects pinned here, both observed on /control:

1. Session `repo` was `repo_url.split("/")[-1]` ("Pi-Dev-Ops") while every
   portfolio card compares against projects.json `repo` ("CleanExpo/Pi-Dev-Ops"),
   so no card could ever show WORKING.
2. The queue, pulse and session panels turned every failed read into
   `urgent: 0`, `comments_today: 0`, `[0]*24` or `[]` — byte-identical to a
   quiet, healthy system. A failure must say `available: False` with an
   `error`, or `None`, so the panel can render UNAVAILABLE.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.server.routes import mission_control, mission_control_sessions as mcs

REPO = Path(__file__).resolve().parents[1]


def _registered_repos() -> list[str]:
    projects = json.loads((REPO / "config" / "harness" / "projects.json").read_text())["projects"]
    return sorted({p["repo"] for p in projects if isinstance(p.get("repo"), str) and "/" in p["repo"]})


def _store(monkeypatch: pytest.MonkeyPatch, sessions: dict) -> None:
    monkeypatch.setattr(mcs, "_store", lambda: sessions)


def _broken_store(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise RuntimeError("session store unreadable")
    monkeypatch.setattr(mcs, "_store", boom)


# ── 1. repo identity ─────────────────────────────────────────────────────────

def test_registry_has_repos_to_check() -> None:
    """Positive control: an empty registry would make the round-trip vacuous."""
    assert "CleanExpo/Pi-Dev-Ops" in _registered_repos()


@pytest.mark.parametrize("shape", ["https://github.com/{}", "https://github.com/{}.git",
                                   "https://github.com/{}/", "git@github.com:{}.git"])
def test_every_registered_repo_round_trips_through_a_session_url(shape: str) -> None:
    for repo in _registered_repos():
        assert mcs.repo_slug(shape.format(repo)) == repo


def test_active_session_repo_is_owner_slash_name(monkeypatch: pytest.MonkeyPatch) -> None:
    _store(monkeypatch, {"sid-active-0001": {"status": "building", "repo_url": "https://github.com/CleanExpo/Pi-Dev-Ops.git"}})
    [row] = mcs.active_sessions()
    assert row["repo"] == "CleanExpo/Pi-Dev-Ops"


def test_completion_repo_is_owner_slash_name(monkeypatch: pytest.MonkeyPatch) -> None:
    _store(monkeypatch, {"sid-done-00001": {"status": "complete", "repo_url": "https://github.com/CleanExpo/CARSI"}})
    [row] = mcs.recent_completions()
    assert row["repo"] == "CleanExpo/CARSI"


def test_unparseable_repo_url_is_unknown_not_a_guess() -> None:
    assert mcs.repo_slug("") == "?"
    assert mcs.repo_slug("not-a-url") == "?"


# ── 2a. session panels ───────────────────────────────────────────────────────

def test_session_store_failure_is_null_not_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _broken_store(monkeypatch)
    assert mcs.hourly_throughput_24h() is None
    assert mcs.active_sessions() is None
    assert mcs.recent_completions() is None


def test_empty_session_store_is_a_real_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: an empty, readable store is a measurement of nothing."""
    _store(monkeypatch, {})
    assert mcs.hourly_throughput_24h() == [0] * 24
    assert mcs.active_sessions() == []
    assert mcs.recent_completions() == []


# ── 2b. Linear queue ─────────────────────────────────────────────────────────

@pytest.fixture
def linear(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    monkeypatch.setattr(mission_control, "_queue_cache", None)
    monkeypatch.setattr(mission_control, "_pulse_cache", None)
    monkeypatch.setattr(mission_control.autonomy, "linear_rate_limited", lambda: False)
    return monkeypatch


def _assert_queue_unavailable(snap: dict) -> None:
    assert snap["available"] is False
    assert isinstance(snap["error"], str) and snap["error"]
    assert snap["urgent"] is None and snap["high"] is None


def test_queue_read_failure_is_unavailable(linear: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise RuntimeError("Linear HTTP 500")
    linear.setattr(mission_control, "_queue_snapshot", boom)
    _assert_queue_unavailable(mission_control._cached_queue_snapshot())


def test_queue_rate_limited_is_unavailable(linear: pytest.MonkeyPatch) -> None:
    linear.setattr(mission_control.autonomy, "linear_rate_limited", lambda: True)
    _assert_queue_unavailable(mission_control._cached_queue_snapshot())


def test_queue_without_linear_key_is_unavailable(linear: pytest.MonkeyPatch) -> None:
    linear.delenv("LINEAR_API_KEY")
    _assert_queue_unavailable(mission_control._cached_queue_snapshot())


def test_queue_success_is_available_with_counts(linear: pytest.MonkeyPatch) -> None:
    linear.setattr(mission_control.autonomy, "_load_portfolio_projects", lambda: [{"project_id": "p1"}])
    linear.setattr(mission_control.autonomy, "fetch_todo_issues", lambda *a, **k: [{"priority": 1}])
    linear.setattr(mission_control, "filter_claimable_issues", lambda issues, **_: issues)
    snap = mission_control._cached_queue_snapshot()
    assert snap["available"] is True and snap["error"] is None
    assert snap["urgent"] == 1 and snap["high"] == 0


# ── 2c. Pulse heartbeat ──────────────────────────────────────────────────────

def _assert_pulse_unavailable(snap: dict) -> None:
    assert snap["available"] is False
    assert isinstance(snap["error"], str) and snap["error"]
    assert snap["comments_today"] is None


def test_pulse_read_failure_is_unavailable(linear: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise RuntimeError("Linear GQL errors")
    linear.setattr(mission_control, "_pulse_status", boom)
    _assert_pulse_unavailable(mission_control._cached_pulse_status())


def test_pulse_rate_limited_is_unavailable(linear: pytest.MonkeyPatch) -> None:
    linear.setattr(mission_control.autonomy, "linear_rate_limited", lambda: True)
    _assert_pulse_unavailable(mission_control._cached_pulse_status())


def test_pulse_without_state_file_is_unavailable(linear: pytest.MonkeyPatch, tmp_path: Path) -> None:
    linear.setattr(mission_control, "_repo_root", lambda: tmp_path)
    _assert_pulse_unavailable(mission_control._pulse_status())


def _pulse_state(tmp_path: Path) -> None:
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "linear-pulse-state.json").write_text(json.dumps({"pulse_issue_id": "abc"}))


def test_pulse_issue_missing_from_linear_is_unavailable(linear: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _pulse_state(tmp_path)
    linear.setattr(mission_control, "_repo_root", lambda: tmp_path)
    linear.setattr(mission_control, "_linear_graphql", lambda *a, **k: {})
    _assert_pulse_unavailable(mission_control._pulse_status())


def test_pulse_success_counts_today(linear: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    _pulse_state(tmp_path)
    linear.setattr(mission_control, "_repo_root", lambda: tmp_path)
    issue = {"identifier": "RA-1", "comments": {"nodes": [{"createdAt": f"{today}T01:00:00Z"}]}}
    linear.setattr(mission_control, "_linear_graphql", lambda *a, **k: {"issue": issue})
    snap = mission_control._pulse_status()
    assert snap["available"] is True and snap["error"] is None
    assert snap["comments_today"] == 1 and snap["pulse_issue_id"] == "RA-1"
