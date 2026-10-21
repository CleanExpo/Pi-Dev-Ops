"""Kill-switch state faults (Codex rounds on 9b8fc6d2 and 1922fa7f).

Every panic writes a fresh random id into the flag itself; a resume clears
only the panic whose id it observed. So nothing depends on a second file, on
a counter surviving corruption, or on the host clock moving forward:
- an unreadable flag refuses every resume, the public default included;
- a panic after an observation always changes the id, even when the switch
  is already engaged, even with the clock set back;
- a Telegram /resume sent within RESUME_AFTER_PANIC_S of the panic (by the
  two clocks) is refused, so a few seconds of host skew cannot let a resume
  sent before a panic clear it;
- panic_id() waits for an in-flight panic, so it only observes completed ones;
- the counted history record is appended in the same locked step as the
  count, so concurrent panics engage the escalation lock at the limit.
Every outbound call is mocked or absent.
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


def _flag():
    return importlib.import_module("swarm.config").SWARM_LOG_DIR / "kill_switch.flag"


def test_unreadable_flag_refuses_the_public_default_resume(ks):
    ks.trigger("telegram_panic", reason="engaged")
    _flag().write_text("{broken")
    assert ks.resume("telegram_resume").get("error") == "panic_state_unreadable"
    assert ks.is_active()


def test_unreadable_flag_refuses_a_confirmed_resume_too(ks):
    ks.trigger("telegram_panic", reason="engaged")
    _flag().write_text("{broken")
    out = ks.resume("telegram_resume_confirm", confirmed=True, reason="manual")
    assert out.get("error") == "panic_state_unreadable"
    assert ks.is_active()


def test_unreadable_flag_still_panics_and_then_resumes(ks):
    ks.trigger("telegram_panic", reason="engaged")
    _flag().write_text("{broken")
    seen = ks.panic_id()
    ks.trigger("telegram_panic", reason="rewrites the flag")
    assert ks.resume("telegram_resume", observed_id=seen).get("error") == "newer_panic"
    assert "error" not in ks.resume("telegram_resume", observed_id=ks.panic_id())
    assert not ks.is_active()


def test_panic_while_engaged_changes_the_id(ks):
    ks.trigger("telegram_panic", reason="one")
    seen = ks.panic_id()
    ks.trigger("telegram_panic", reason="two, already engaged")
    assert ks.panic_id() != seen
    assert ks.resume("dashboard", observed_id=seen).get("error") == "newer_panic"
    assert ks.is_active()


def test_clock_set_back_cannot_reuse_an_observation(ks, monkeypatch):
    state = importlib.import_module("swarm.kill_switch_state")
    monkeypatch.setattr(state.time, "time", lambda: 3_000_000_000.0)
    ks.trigger("telegram_panic", reason="one")
    seen = ks.panic_id()
    monkeypatch.setattr(state.time, "time", lambda: 1_000_000_000.0)
    _flag().write_text("{broken")
    ks.trigger("telegram_panic", reason="two, clock set back after corruption")
    assert ks.resume("dashboard", observed_id=seen).get("error") == "newer_panic"
    assert ks.is_active()


def test_resume_sent_just_before_a_panic_is_refused_despite_host_skew(ks, monkeypatch):
    """Host clock 5 s behind Telegram's: the panic is stamped 100, a /resume
    sent before it (by real time) carries Telegram's 103."""
    state = importlib.import_module("swarm.kill_switch_state")
    monkeypatch.setattr(state.time, "time", lambda: 1_700_000_100.0)
    ks.trigger("dashboard_2fa", reason="dashboard panic", approvers=["a", "b"])
    out = ks.resume("telegram_resume", observed_id=ks.panic_id(), sent_at=1_700_000_103.0)
    assert out.get("error") == "too_soon_after_panic"
    assert ks.is_active()


def test_resume_sent_well_after_the_panic_still_works(ks, monkeypatch):
    state = importlib.import_module("swarm.kill_switch_state")
    monkeypatch.setattr(state.time, "time", lambda: 1_700_000_100.0)
    ks.trigger("telegram_panic", reason="engaged")
    sent = 1_700_000_100.0 + ks.RESUME_AFTER_PANIC_S + 1
    assert "error" not in ks.resume("telegram_resume", observed_id=ks.panic_id(), sent_at=sent)
    assert not ks.is_active()


def test_panic_id_waits_for_an_in_flight_panic(ks):
    done = threading.Event()
    with ks.send_gate():  # what a panic holds while it raises the flag
        t = threading.Thread(target=lambda: (ks.panic_id(), done.set()))
        t.start()
        assert not done.wait(0.3)
    assert done.wait(5)
    t.join(5)


def test_legacy_plain_timestamp_flag_still_resumes(ks):
    _flag().parent.mkdir(parents=True, exist_ok=True)
    _flag().write_text("2026-10-20T01:02:03+00:00")
    assert ks.is_active()
    assert "error" not in ks.resume("telegram_resume", observed_id=ks.panic_id())
    assert not ks.is_active()


def test_dashboard_stale_client_observation_is_refused(ks, monkeypatch):
    from app.server.auth import require_auth, require_rate_limit
    from app.server.routes import swarm as swarm_routes
    monkeypatch.setattr(swarm_routes, "_verify_totp", lambda user, code: (True, "ok"))
    ks.trigger("telegram_panic", reason="one")
    seen_before = ks.panic_id()
    ks.trigger("telegram_panic", reason="two")
    app = FastAPI()
    app.include_router(swarm_routes.router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_rate_limit] = lambda: None
    resp = TestClient(app).post("/api/swarm/resume", json={
        "approver_user": "phill", "approver_totp": "123456", "reason": "ok",
        "observed_panic_id": seen_before})
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
