"""Tests for GET /api/zte/score — the cached ZTE v2 score behind the Mission Control badge."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.server.routes import zte


def _write(tmp_path, payload) -> None:
    path = tmp_path / "zte-v2-score.json"
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload))


async def _call(monkeypatch, tmp_path) -> tuple[int, dict]:
    monkeypatch.setattr(zte, "SCORE_FILE", tmp_path / "zte-v2-score.json")
    res = await zte.zte_score()
    return res.status_code, json.loads(res.body)


async def test_serves_fresh_cached_score(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    _write(tmp_path, {"v2_total": 72, "band": "Scaling", "computed_at": now})
    status, body = await _call(monkeypatch, tmp_path)
    assert status == 200
    assert body == {"score": 72, "band": "Scaling", "computed_at": now, "stale": False}


async def test_flags_a_score_older_than_48h_as_stale(monkeypatch, tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
    _write(tmp_path, {"v2_total": 60, "band": "x", "computed_at": old})
    status, body = await _call(monkeypatch, tmp_path)
    assert status == 200
    assert body["stale"] is True


async def test_missing_timestamp_is_stale_not_fresh(monkeypatch, tmp_path):
    _write(tmp_path, {"v2_total": 60})
    _, body = await _call(monkeypatch, tmp_path)
    assert body["stale"] is True


async def test_absent_file_is_404_not_a_fake_score(monkeypatch, tmp_path):
    status, body = await _call(monkeypatch, tmp_path)
    assert status == 404
    assert body == {"error": "no score computed yet"}


async def test_malformed_or_out_of_range_is_404(monkeypatch, tmp_path):
    for payload in ("{not json", {"v2_total": "72"}, {"v2_total": 140}, {"v2_total": True}, [1, 2]):
        _write(tmp_path, payload)
        status, _ = await _call(monkeypatch, tmp_path)
        assert status == 404, payload


def test_route_is_auth_gated_and_wired_into_main():
    route = next(r for r in zte.router.routes if r.path == "/api/zte/score")
    assert route.dependencies, "/api/zte/score must be auth-gated"
    from app.server import main

    assert main.zte.router is zte.router
