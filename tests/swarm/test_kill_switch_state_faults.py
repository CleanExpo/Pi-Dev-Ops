"""Kill-switch state faults (Codex round on 9b8fc6d2).

P1-CORRUPT-PANIC-STATE-DEFAULT-RESUME: an unreadable panic state refuses every
resume, including the public default with no observations.
P1-PANIC-SEQ-ROLLBACK-CLEARS-NEW-PANIC: a panic recorded after the state was
corrupted never gets a sequence at or below one observed before.
P1-CONCURRENT-PANICS-BYPASS-ESCALATION: the panic counted by the loop guard is
recorded in the same locked step as the count, so concurrent panics engage
the escalation lock at the limit. Every outbound call is mocked or absent.
"""
from __future__ import annotations

import importlib
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def ks(monkeypatch, tmp_path):
    swarm_config = importlib.import_module("swarm.config")
    monkeypatch.setattr(swarm_config, "SWARM_LOG_DIR", tmp_path / "swarmlog")
    monkeypatch.setattr(swarm_config, "TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(swarm_config, "TELEGRAM_BOT_TOKEN", "test-token-not-real")
    for var in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    return importlib.import_module("swarm.kill_switch")


def _corrupt_state():
    state = importlib.import_module("swarm.config").SWARM_LOG_DIR / "kill_switch.panic_seq.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{broken")


def test_corrupt_state_refuses_the_public_default_resume(ks):
    ks.trigger("telegram_panic", reason="engaged")
    _corrupt_state()
    out = ks.resume("telegram_resume")
    assert out.get("error") == "panic_state_unreadable"
    assert ks.is_active()


def test_corrupt_state_refuses_a_confirmed_resume_too(ks):
    ks.trigger("telegram_panic", reason="engaged")
    _corrupt_state()
    out = ks.resume("telegram_resume_confirm", confirmed=True, reason="manual")
    assert out.get("error") == "panic_state_unreadable"
    assert ks.is_active()


def test_panic_after_corruption_never_rolls_the_sequence_back(ks):
    ks.trigger("telegram_panic", reason="one")
    ks.trigger("telegram_panic", reason="two")
    seen_before = ks.panic_seq()
    _corrupt_state()
    ks.trigger("telegram_panic", reason="three, after corruption")
    assert ks.panic_seq() > seen_before
    out = ks.resume("dashboard_2fa", observed_seq=seen_before)
    assert out.get("error") == "newer_panic"
    assert ks.is_active()


def test_dashboard_stale_observation_cannot_clear_a_post_corruption_panic(ks, monkeypatch):
    from app.server.auth import require_auth, require_rate_limit
    from app.server.routes import swarm as swarm_routes
    monkeypatch.setattr(swarm_routes, "_verify_totp", lambda user, code: (True, "ok"))
    ks.trigger("telegram_panic", reason="one")
    ks.trigger("telegram_panic", reason="two")
    seen_before = ks.panic_seq()
    _corrupt_state()
    ks.trigger("telegram_panic", reason="three, after corruption")
    app = FastAPI()
    app.include_router(swarm_routes.router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_rate_limit] = lambda: None
    resp = TestClient(app).post("/api/swarm/resume", json={
        "approver_user": "phill", "approver_totp": "123456", "reason": "ok",
        "observed_panic_seq": seen_before})
    assert resp.status_code == 409
    assert ks.is_active()


def test_concurrent_panics_engage_the_escalation_lock_at_the_limit(ks, monkeypatch):
    """Codex's repro: every thread waits at a barrier inside _append_history.
    If the counted record is appended outside the locked step, all six pass
    the count before any record exists. Inside it, the barrier times out once
    and the six run one after another."""
    n = ks.PANIC_RATE_LIMIT + 1
    barrier, real_append = threading.Barrier(n, timeout=0.5), ks._append_history

    def append_at_barrier(record):
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        real_append(record)
    monkeypatch.setattr(ks, "_append_history", append_at_barrier)
    errors: list[BaseException] = []

    def panic():
        try:
            ks.trigger("telegram_panic", reason="concurrent")
        except BaseException as exc:  # surfaced below
            errors.append(exc)
    threads = [threading.Thread(target=panic) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    assert ks.panic_count_last_hour() == n
    assert ks.is_locked()
    assert ks.resume("telegram_resume").get("error") == "escalation_lock_active"
