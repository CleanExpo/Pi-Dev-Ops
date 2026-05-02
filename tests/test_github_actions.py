"""tests/test_github_actions.py — GitHub Actions CTO provider smoke."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm.providers import github_actions as GHA  # noqa: E402
from swarm.providers import select_platform_provider  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("TAO_CTO_PROVIDER", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


# ── Registry routing ────────────────────────────────────────────────────────


def test_registry_github_actions_selectable(monkeypatch):
    monkeypatch.setenv("TAO_CTO_PROVIDER", "github_actions")
    fn = select_platform_provider()
    assert fn.__name__ == "github_actions_provider"


# ── No-creds fallback ───────────────────────────────────────────────────────


def test_provider_no_token_emits_all_synthetic():
    out = GHA.github_actions_provider()
    from swarm.providers.synthetic_platform import synthetic_platform_provider
    expected = {m.business_id: m.deploys_last_week
                for m in synthetic_platform_provider()}
    actual = {m.business_id: m.deploys_last_week for m in out}
    assert actual == expected


# ── _parse_iso ──────────────────────────────────────────────────────────────


def test_parse_iso_handles_z_suffix():
    out = GHA._parse_iso("2026-05-03T06:00:00Z")
    assert out is not None
    assert out.tzinfo is not None


def test_parse_iso_returns_none_on_garbage():
    assert GHA._parse_iso("not-a-date") is None


# ── _compute_dora ───────────────────────────────────────────────────────────


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_compute_dora_empty_returns_none():
    assert GHA._compute_dora([]) is None


def test_compute_dora_counts_recent_successes():
    """Successes in the last 7 days count as deploys."""
    now = _now()
    runs = [
        {
            "status": "completed", "conclusion": "success",
            "created_at": _iso(now - timedelta(days=1)),
            "updated_at": _iso(now - timedelta(days=1, minutes=-5)),
        },
        {
            "status": "completed", "conclusion": "success",
            "created_at": _iso(now - timedelta(days=2)),
            "updated_at": _iso(now - timedelta(days=2, minutes=-3)),
        },
        {
            # Too old to count as a deploy
            "status": "completed", "conclusion": "success",
            "created_at": _iso(now - timedelta(days=20)),
            "updated_at": _iso(now - timedelta(days=20, minutes=-10)),
        },
    ]
    out = GHA._compute_dora(runs)
    assert out is not None
    assert out["deploys_last_week"] == 2
    assert out["change_total_count"] == 3
    assert out["change_failure_count"] == 0
    # Lead time p50 — non-negative; the third run also contributes
    assert out["lead_time_hours_p50"] >= 0.0


def test_compute_dora_failure_followed_by_success_yields_mttr():
    now = _now()
    runs = [
        {  # T-3h failure
            "status": "completed", "conclusion": "failure",
            "created_at": _iso(now - timedelta(hours=3)),
            "updated_at": _iso(now - timedelta(hours=3, minutes=-15)),
        },
        {  # T-1h success → MTTR ~2h
            "status": "completed", "conclusion": "success",
            "created_at": _iso(now - timedelta(hours=1)),
            "updated_at": _iso(now - timedelta(hours=1, minutes=-5)),
        },
    ]
    out = GHA._compute_dora(runs)
    assert out is not None
    # MTTR ≈ 2 hours (failure created_at → next success updated_at)
    assert 1.5 < out["mttr_hours"] < 2.5
    assert out["change_failure_count"] == 1
    assert out["change_total_count"] == 2


def test_compute_dora_handles_in_progress_runs():
    """Non-completed runs are excluded from CFR + MTTR computation."""
    now = _now()
    runs = [
        {
            "status": "in_progress", "conclusion": None,
            "created_at": _iso(now - timedelta(hours=1)),
            "updated_at": _iso(now),
        },
        {
            "status": "completed", "conclusion": "success",
            "created_at": _iso(now - timedelta(days=1)),
            "updated_at": _iso(now - timedelta(days=1, minutes=-5)),
        },
    ]
    out = GHA._compute_dora(runs)
    assert out is not None
    assert out["change_total_count"] == 1  # in_progress excluded


# ── _real_for_business ──────────────────────────────────────────────────────


def test_real_for_business_uses_repo_from_projects_json(monkeypatch):
    seen = {}

    def fake_runs(repo, *, token):
        seen["repo"] = repo
        seen["token"] = token
        now = _now()
        return [{
            "status": "completed", "conclusion": "success",
            "created_at": _iso(now - timedelta(days=1)),
            "updated_at": _iso(now - timedelta(days=1, minutes=-5)),
        }]

    monkeypatch.setattr(GHA, "_runs_for_repo", fake_runs)
    out = GHA._real_for_business("pi-dev-ops", token="ghs_xxx")
    assert out is not None
    assert seen["repo"] == "CleanExpo/Pi-Dev-Ops"
    assert seen["token"] == "ghs_xxx"
    assert out.deploys_last_week == 1


def test_real_for_business_unknown_bid_returns_none(monkeypatch):
    out = GHA._real_for_business("not-a-business", token="ghs_xxx")
    assert out is None


def test_real_for_business_runs_fetch_failure_returns_none(monkeypatch):
    def boom(repo, *, token):
        raise RuntimeError("api down")
    monkeypatch.setattr(GHA, "_runs_for_repo", boom)
    out = GHA._real_for_business("pi-dev-ops", token="ghs_xxx")
    assert out is None


def test_real_for_business_no_runs_returns_none(monkeypatch):
    monkeypatch.setattr(GHA, "_runs_for_repo", lambda repo, *, token: [])
    out = GHA._real_for_business("pi-dev-ops", token="ghs_xxx")
    assert out is None


# ── github_actions_provider end-to-end ──────────────────────────────────────


def test_provider_with_token_calls_real_path(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_test")

    now = _now()

    def fake_runs(repo, *, token):
        # Only return real data for one repo; others get [] → fallback
        if repo == "CleanExpo/Pi-Dev-Ops":
            return [{
                "status": "completed", "conclusion": "success",
                "created_at": _iso(now - timedelta(days=1)),
                "updated_at": _iso(now - timedelta(days=1, minutes=-5)),
            }]
        return []

    monkeypatch.setattr(GHA, "_runs_for_repo", fake_runs)
    out = GHA.github_actions_provider()
    by_bid = {m.business_id: m for m in out}

    # pi-dev-ops should be the real one
    pdo = by_bid.get("pi-dev-ops")
    assert pdo is not None
    assert pdo.deploys_last_week == 1

    # Some other business should have synthetic deploys (could be any number,
    # just confirm it's matching the synthetic value, not 1)
    from swarm.providers.synthetic_platform import synthetic_platform_one
    other_bid = next(b for b in by_bid if b != "pi-dev-ops")
    expected = synthetic_platform_one(other_bid).deploys_last_week
    assert by_bid[other_bid].deploys_last_week == expected
