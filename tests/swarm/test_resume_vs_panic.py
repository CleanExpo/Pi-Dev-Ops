"""A /resume never clears a panic that completed after the resume was decided
(Codex round on 590a54b6: P1-STALE-RESUME-CLEARS-NEWER-PANIC).

Each path is driven to the same interleaving, deterministically and without
threads: the resume passes its own check, a panic completes, then the resume
tries to clear the flag. The panic must win on the webhook, the CoS poller
and the dashboard. Every outbound call is mocked.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ALERT_CHAT = "123"


@pytest.fixture
def ks(monkeypatch, tmp_path):
    swarm_config = importlib.import_module("swarm.config")
    draft_review = importlib.import_module("swarm.draft_review")
    monkeypatch.setattr(swarm_config, "SWARM_LOG_DIR", tmp_path / "swarmlog")
    monkeypatch.setattr(swarm_config, "TELEGRAM_CHAT_ID", ALERT_CHAT)
    monkeypatch.setattr(swarm_config, "TELEGRAM_BOT_TOKEN", "test-token-not-real")
    monkeypatch.setattr(draft_review, "_state_dir", lambda: tmp_path)
    for var in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    return importlib.import_module("swarm.kill_switch")


def _client(router):
    from app.server.auth import require_auth, require_rate_limit
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_rate_limit] = lambda: None
    return TestClient(app, raise_server_exceptions=True)


# ── the rule itself ──────────────────────────────────────────────────────────

def test_resume_refused_when_a_newer_panic_was_recorded(ks):
    ks.trigger("telegram_panic", reason="one")
    seen = ks.panic_id()
    ks.trigger("telegram_panic", reason="two")
    out = ks.resume("telegram_resume", observed_id=seen)
    assert out.get("error") == "newer_panic"
    assert ks.is_active()
    assert "error" not in ks.resume("telegram_resume", observed_id=ks.panic_id())
    assert not ks.is_active()


def test_resume_sent_before_the_latest_panic_is_refused(ks):
    ks.trigger("telegram_panic", reason="one")
    out = ks.resume("telegram_resume", sent_at=0.0)
    assert out.get("error") == "too_soon_after_panic"
    assert ks.is_active()


def test_panic_id_changes_on_every_trigger_even_when_engaged(ks):
    ids = {ks.panic_id()}
    ks.trigger("telegram_panic", reason="a")
    ids.add(ks.panic_id())
    ks.trigger("telegram_panic", reason="b")
    ids.add(ks.panic_id())
    assert len(ids) == 3


# ── webhook ──────────────────────────────────────────────────────────────────

def test_webhook_resume_cannot_clear_a_panic_that_completes_after_its_check(ks, monkeypatch):
    import app.server.config as cfg
    from app.server.routes.webhooks import router
    ra = importlib.import_module("swarm.review_authority")
    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(cfg, "TELEGRAM_WEBHOOK_SECRET", "hook-secret")
    ks.trigger("telegram_panic", reason="first")
    real_claim = ra._claim_update_id

    def claim_then_panic(uid):
        ok = real_claim(uid)
        if uid == 70_001:
            ks.trigger("telegram_panic", reason="lands after the resume's check")
        return ok
    monkeypatch.setattr(ra, "_claim_update_id", claim_then_panic)
    resp = _client(router).post(
        "/webhook/telegram", headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        json={"update_id": 70_001, "message": {"text": "/resume", "chat": {"id": int(ALERT_CHAT)}}})
    assert resp.status_code == 200
    assert ks.is_active()


# ── CoS poller ───────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_poller_resume_cannot_clear_a_panic_that_completes_after_its_fetch(ks, monkeypatch):
    import json
    import urllib.request
    from swarm.bots import chief_of_staff
    ks.trigger("telegram_panic", reason="first")
    body = json.dumps({"ok": True, "result": [
        {"update_id": 1, "message": {"text": "/resume", "chat": {"id": int(ALERT_CHAT)}}}]}).encode()

    def fetch_then_panic(req, timeout=None):
        resp = _Resp(body)
        ks.trigger("telegram_panic", reason="dashboard panic after the fetch")
        return resp
    monkeypatch.setattr(urllib.request, "urlopen", fetch_then_panic)
    chief_of_staff._poll_telegram(0)
    assert ks.is_active()


# ── dashboard ────────────────────────────────────────────────────────────────

def test_dashboard_resume_cannot_clear_a_panic_that_completes_during_its_check(ks, monkeypatch):
    from app.server.routes import swarm as swarm_routes

    def totp_then_panic(user, code):
        ks.trigger("telegram_panic", reason="lands while the resume is being verified")
        return True, "ok"
    monkeypatch.setattr(swarm_routes, "_verify_totp", totp_then_panic)
    ks.trigger("telegram_panic", reason="first")
    resp = _client(swarm_routes.router).post(
        "/api/swarm/resume",
        json={"approver_user": "phill", "approver_totp": "123456", "reason": "ok",
              "observed_panic_id": ks.panic_id()})
    assert resp.status_code == 409
    assert ks.is_active()


def test_dashboard_resume_still_works_with_no_newer_panic(ks, monkeypatch):
    from app.server.routes import swarm as swarm_routes
    monkeypatch.setattr(swarm_routes, "_verify_totp", lambda user, code: (True, "ok"))
    ks.trigger("telegram_panic", reason="first")
    resp = _client(swarm_routes.router).post(
        "/api/swarm/resume",
        json={"approver_user": "phill", "approver_totp": "123456", "reason": "ok",
              "observed_panic_id": ks.panic_id()})
    assert resp.status_code == 200
    assert not ks.is_active()


def test_unreadable_flag_still_panics_and_refuses_resume(ks):
    flag = importlib.import_module("swarm.config").SWARM_LOG_DIR / "kill_switch.flag"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("{not json")
    out = ks.resume("telegram_resume", observed_id=ks.panic_id())
    assert out.get("error") == "panic_state_unreadable"
    ks.trigger("telegram_panic", reason="flag was corrupt")
    assert ks.is_active()
    assert ks.panic_id() not in ("", ks.UNREADABLE)


def test_panic_cannot_slip_between_the_resume_check_and_the_clear(ks, monkeypatch):
    """The check and the clear are one step under send_gate(): a panic that
    starts while a resume is past its check waits, then re-engages."""
    import threading
    ks.trigger("telegram_panic", reason="first")
    seen, checked = ks.panic_id(), threading.Event()
    real_state = ks.flag_state

    def state_then_pause():
        out = real_state()
        if threading.current_thread().name == "resumer":
            checked.set()
            threading.Event().wait(0.3)  # the panic thread runs in this gap
        return out
    monkeypatch.setattr(ks, "flag_state", state_then_pause)
    resumer = threading.Thread(name="resumer", target=lambda: ks.resume(
        "telegram_resume", observed_id=seen))
    resumer.start()
    assert checked.wait(timeout=5)
    panic = threading.Thread(target=lambda: ks.trigger("telegram_panic", reason="in the gap"))
    panic.start()
    resumer.join(timeout=5)
    panic.join(timeout=5)
    assert ks.is_active()
