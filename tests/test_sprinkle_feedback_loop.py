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


# ── RA-6872: Pydantic-validated bounded-retry on malformed output ──────────────

def test_feedback_loop_retries_malformed_then_succeeds(monkeypatch, autonomy_log):
    """First call returns malformed JSON (missing category); the loop re-asks
    and the second, valid response is parsed into the outcome object."""
    fake = FakeProviderRouter(responses=[
        '{"label": "no category here", "confidence": 0.8}',
        '{"category": "negative", "label": "regressed two releases later", "confidence": 0.77}',
    ])
    install_fake_router(monkeypatch, fake)

    from app.server.agents import feedback_loop as fl
    out = fl._classify_with_claude(
        pipeline_id="PL-5",
        comments=["it broke again"],
        days_since=40,
        state="Done",
    )

    assert out is not None
    assert out["category"] == "negative"
    assert out["label"] == "regressed two releases later"
    assert pytest.approx(0.77, rel=1e-3) == out["confidence"]
    # Exactly one re-ask: the malformed first call plus the valid retry.
    assert len(fake.calls) == 2
    # The retry prompt must carry the validation error back to the model.
    assert fake.calls[1]["prompt"] != fake.calls[0]["prompt"]
    assert "invalid" in fake.calls[1]["prompt"].lower()


def test_feedback_loop_returns_none_after_retries_exhausted(monkeypatch, autonomy_log):
    """Persistently malformed output is retried a bounded number of times
    (initial + 2), then gives up with None so the keyword fallback wins."""
    fake = FakeProviderRouter(response='{"not": "the schema"}')
    install_fake_router(monkeypatch, fake)

    from app.server.agents import feedback_loop as fl
    out = fl._classify_with_claude(
        pipeline_id="PL-6",
        comments=["ambiguous"],
        days_since=12,
        state="In Review",
    )

    assert out is None
    # Bounded at 3 total cheap-tier calls (1 initial + 2 retries) — never unbounded.
    assert len(fake.calls) == 3


def test_feedback_loop_clamps_out_of_range_confidence(monkeypatch, autonomy_log):
    """A model returning confidence > 1 is clamped, not rejected — preserving
    the prior clamp semantics while still validating the rest of the schema."""
    fake = FakeProviderRouter(
        response='{"category": "positive", "label": "client used it immediately", "confidence": 1.5}',
    )
    install_fake_router(monkeypatch, fake)

    from app.server.agents import feedback_loop as fl
    out = fl._classify_with_claude(
        pipeline_id="PL-7",
        comments=["great"],
        days_since=3,
        state="Done",
    )

    assert out is not None
    assert out["confidence"] == 1.0
    assert len(fake.calls) == 1  # clamped on the first try, no wasteful re-ask
