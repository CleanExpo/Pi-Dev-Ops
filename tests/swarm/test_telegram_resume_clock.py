"""A Telegram /resume is ordered against the panic by Telegram's clock only
(Codex helper findings on 93ee19ff).

The host clock and Telegram's can disagree by any amount, so no check
compares them. A /panic sent in Telegram stores its own message date in the
flag; a Telegram /resume clears the flag only when its message date is later.
A panic raised anywhere else carries no Telegram date, so a Telegram /resume
cannot clear it: resume from the dashboard, or send /panic then /resume.
Command words match exactly. A webhook secret equal to the bot's id (the
token prefix) is refused. Every outbound call is mocked or absent.
"""
from __future__ import annotations

import importlib
import json
import urllib.request

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ALERT_CHAT = "123"
T = 1_700_000_000
FOUNDER = "8000001"
FROM = {"id": int(FOUNDER), "is_bot": False}  # the founder in person (test_resume_sender.py)


@pytest.fixture
def ks(monkeypatch, tmp_path):
    swarm_config = importlib.import_module("swarm.config")
    monkeypatch.setattr(swarm_config, "SWARM_LOG_DIR", tmp_path / "swarmlog")
    monkeypatch.setattr(swarm_config, "TELEGRAM_CHAT_ID", ALERT_CHAT)
    monkeypatch.setattr(swarm_config, "TELEGRAM_BOT_TOKEN", "test-token-not-real")
    monkeypatch.setattr(importlib.import_module("swarm.draft_review"), "_state_dir",
                        lambda: tmp_path)
    monkeypatch.setenv("TAO_FOUNDER_TELEGRAM_USER_ID", FOUNDER)
    for var in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    return importlib.import_module("swarm.kill_switch")


def _webhook(monkeypatch, secret="hook-secret", token="bot-token"):
    import app.server.config as cfg
    from app.server.routes.webhooks import router
    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setattr(cfg, "TELEGRAM_WEBHOOK_SECRET", secret)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    def post(text, date, uid, header=secret):
        return client.post(
            "/webhook/telegram", headers={"X-Telegram-Bot-Api-Secret-Token": header},
            json={"update_id": uid, "message": {"text": text, "date": date, "from": FROM,
                                                 "chat": {"id": int(ALERT_CHAT)}}})
    return post


def _poll(monkeypatch, text, date, uid=1):
    from swarm.bots import chief_of_staff
    body = json.dumps({"ok": True, "result": [{"update_id": uid, "message": {
        "text": text, "date": date, "from": FROM, "chat": {"id": int(ALERT_CHAT)}}}]}).encode()

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return body
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp())
    chief_of_staff._poll_telegram(0)


def _host_clock(monkeypatch, t):
    state = importlib.import_module("swarm.kill_switch_state")
    monkeypatch.setattr(state.time, "time", lambda: float(t))


# ── the rule ────────────────────────────────────────────────────────────────

def test_telegram_resume_cannot_clear_a_dashboard_panic_at_any_skew(ks):
    ks.trigger("dashboard_2fa", reason="dashboard", approvers=["a", "b"])
    for sent in (T - 10**6, T, T + 10**6):  # host clock anywhere relative to Telegram
        out = ks.resume("telegram_resume", observed_id=ks.panic_id(), sent_at=float(sent))
        assert out.get("error") == "telegram_time_unknown"
    assert ks.is_active()


def test_telegram_resume_sent_before_the_telegram_panic_is_refused(ks):
    ks.handle_command("/panic stop", sent_at=float(T))
    for sent in (T - 150, T):  # earlier, and the same second (ambiguous)
        out = ks.resume("telegram_resume", observed_id=ks.panic_id(), sent_at=float(sent))
        assert out.get("error") == "sent_before_panic"
    assert ks.is_active()
    assert "error" not in ks.resume("telegram_resume", observed_id=ks.panic_id(),
                                    sent_at=float(T + 1))
    assert not ks.is_active()


def test_dashboard_resume_still_clears_a_dashboard_panic(ks):
    ks.trigger("dashboard_2fa", reason="dashboard", approvers=["a", "b"])
    assert "error" not in ks.resume("dashboard", observed_id=ks.panic_id())
    assert not ks.is_active()


# ── both Telegram ingress paths, Codex's >120 s skew repro ──────────────────

def test_webhook_stale_resume_cannot_clear_a_dashboard_panic(ks, monkeypatch):
    _host_clock(monkeypatch, T)  # host 150 s behind Telegram: Codex's repro
    post = _webhook(monkeypatch)
    ks.trigger("dashboard_2fa", reason="dashboard", approvers=["a", "b"])
    assert post("/resume", T + 150, 90_001).status_code == 200
    assert ks.is_active()


def test_poller_stale_resume_cannot_clear_a_dashboard_panic(ks, monkeypatch):
    _host_clock(monkeypatch, T)  # host 150 s behind Telegram: Codex's repro
    ks.trigger("dashboard_2fa", reason="dashboard", approvers=["a", "b"])
    _poll(monkeypatch, "/resume", T + 150)
    assert ks.is_active()


def test_webhook_panic_then_resume_by_telegram_dates(ks, monkeypatch):
    post = _webhook(monkeypatch)
    assert post("/panic", T, 90_010).status_code == 200
    assert ks.is_active()
    assert post("/resume", T - 5, 90_011).status_code == 200  # sent before the panic
    assert ks.is_active()
    assert post("/resume", T + 5, 90_012).status_code == 200
    assert not ks.is_active()


def test_poller_panic_then_resume_by_telegram_dates(ks, monkeypatch):
    _poll(monkeypatch, "/panic", T, uid=1)
    assert ks.is_active()
    _poll(monkeypatch, "/resume", T + 5, uid=2)
    assert not ks.is_active()


# ── command words ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["/resume-not-now", "/resumeplease", "/resume_later x"])
def test_lookalike_commands_do_not_resume(ks, text):
    ks.handle_command("/panic", sent_at=float(T))
    assert ks.handle_command(text, observed_id=ks.panic_id(), sent_at=float(T + 60),
                             from_founder=True) is None
    assert ks.is_active()


def test_lookalike_panic_does_not_panic(ks):
    assert ks.handle_command("/panicky", sent_at=float(T)) is None
    assert not ks.is_active()


def test_bot_addressed_commands_still_work(ks, monkeypatch):
    monkeypatch.setenv("TAO_TELEGRAM_BOT_USERNAME", "PiCeoBot")
    assert ks.handle_command("/panic@PiCeoBot now", sent_at=float(T)) == "panic"
    out = ks.handle_command("/resume@PiCeoBot ok", observed_id=ks.panic_id(),
                            sent_at=float(T + 1), from_founder=True)
    assert out == "resume"
    assert not ks.is_active()


# ── webhook secret ──────────────────────────────────────────────────────────

def test_webhook_secret_equal_to_the_bot_id_is_refused(ks, monkeypatch):
    post = _webhook(monkeypatch, secret="12345", token="12345:synthetic")
    ks.trigger("dashboard_2fa", reason="dashboard", approvers=["a", "b"])
    resp = post("/panic", T, 90_020, header="12345")
    assert resp.status_code >= 400
    resp = post("/resume", T + 5, 90_021, header="12345")
    assert resp.status_code >= 400
    assert ks.is_active()
