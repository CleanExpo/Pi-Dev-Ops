"""tests/test_sprinkle_feedback_loop.py — RA-3017 sprinkle coverage.

Covers `app.server.agents.feedback_loop._classify_with_claude`:
  * Routes through provider_router with role `sprinkle.feedback`
  * Returns dict {category, label, confidence} on valid JSON response
  * Returns None on rc != 0
  * Returns None on router-unavailable exception
  * Returns None on unparseable JSON
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tests._sprinkle_helpers import FakeProviderRouter, install_fake_router  # noqa: E402


@pytest.fixture
def autonomy_log(monkeypatch, tmp_path: Path):
    from app.server.agents import feedback_loop as fl
    log = tmp_path / "autonomy.jsonl"
    monkeypatch.setattr(fl, "_AUTONOMY_LOG", log)
    return log


def _read_log(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def test_feedback_loop_routes_through_provider_router(monkeypatch, autonomy_log):
    fake = FakeProviderRouter(
        response='{"category": "positive", "label": "client used it immediately", "confidence": 0.91}',
    )
    install_fake_router(monkeypatch, fake)

    from app.server.agents import feedback_loop as fl
    out = fl._classify_with_claude(
        pipeline_id="PL-1",
        comments=["client thanked us"],
        days_since=2,
        state="Done",
    )

    assert out is not None
    assert out["category"] == "positive"
    assert out["label"] == "client used it immediately"
    assert pytest.approx(0.91, rel=1e-3) == out["confidence"]
    assert len(fake.calls) == 1
    assert fake.calls[0]["role"] == fl._PATTERN_ROLE == "sprinkle.feedback"


def test_feedback_loop_returns_none_on_llm_failure(monkeypatch, autonomy_log):
    fake = FakeProviderRouter(rc=1, response="", error="timeout")
    install_fake_router(monkeypatch, fake)

    from app.server.agents import feedback_loop as fl
    out = fl._classify_with_claude(
        pipeline_id="PL-2",
        comments=["meh"],
        days_since=5,
        state="In Review",
    )

    assert out is None
    events = _read_log(autonomy_log)
    assert any(e.get("sprinkle") == "feedback_loop" and e.get("outcome") == "call_failed" for e in events)


def test_feedback_loop_returns_none_on_router_exception(monkeypatch, autonomy_log):
    fake = FakeProviderRouter(raise_exc=ConnectionError("no socket"))
    install_fake_router(monkeypatch, fake)

    from app.server.agents import feedback_loop as fl
    out = fl._classify_with_claude(
        pipeline_id="PL-3",
        comments=[],
        days_since=10,
        state="Done",
    )

    assert out is None
    events = _read_log(autonomy_log)
    assert any(e.get("sprinkle") == "feedback_loop" and e.get("outcome") == "router_unavailable" for e in events)


def test_feedback_loop_returns_none_on_unparseable_json(monkeypatch, autonomy_log):
    fake = FakeProviderRouter(response="this is not json")
    install_fake_router(monkeypatch, fake)

    from app.server.agents import feedback_loop as fl
    out = fl._classify_with_claude(
        pipeline_id="PL-4",
        comments=["yikes"],
        days_since=1,
        state="Backlog",
    )

    assert out is None
    events = _read_log(autonomy_log)
    assert any(e.get("sprinkle") == "feedback_loop" for e in events)
