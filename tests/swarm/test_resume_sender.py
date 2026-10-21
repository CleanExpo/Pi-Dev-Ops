"""A Telegram /resume (or /resume-confirm) counts only when the founder sent it
in person, on the webhook and the CoS poller alike (coordinator finding on
93ee19ff). Refused: another member of the alert chat, an anonymous group
admin (sender_chat set, from = GroupAnonymousBot), a message with no `from`,
a bot, and any sender while TAO_FOUNDER_TELEGRAM_USER_ID is unset. /panic
stays open to any member: it fails safe. Every outbound call is mocked.
"""
from __future__ import annotations

import importlib
import json
import urllib.request

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ALERT_CHAT = "-100123"
FOUNDER = "8000001"
T = 1_700_000_000
FOUNDER_FROM = {"id": int(FOUNDER), "is_bot": False, "first_name": "Phill"}
SENDERS = {
    "another_member": {"from": {"id": 8000002, "is_bot": False, "first_name": "Sam"}},
    "anonymous_admin": {"from": {"id": 1087968824, "is_bot": True, "username": "GroupAnonymousBot"},
                        "sender_chat": {"id": int(ALERT_CHAT), "type": "supergroup"}},
    "founder_via_sender_chat": {"from": FOUNDER_FROM,
                                "sender_chat": {"id": -100999, "type": "channel"}},
    "from_missing": {},
    "founder_id_as_bot": {"from": {"id": int(FOUNDER), "is_bot": True}},
    "is_bot_missing": {"from": {"id": int(FOUNDER)}},
}


@pytest.fixture
def ks(monkeypatch, tmp_path):
    swarm_config = importlib.import_module("swarm.config")
    draft_review = importlib.import_module("swarm.draft_review")
    monkeypatch.setattr(swarm_config, "SWARM_LOG_DIR", tmp_path / "swarmlog")
    monkeypatch.setattr(swarm_config, "TELEGRAM_CHAT_ID", ALERT_CHAT)
    monkeypatch.setattr(swarm_config, "TELEGRAM_BOT_TOKEN", "test-token-not-real")
    monkeypatch.setattr(draft_review, "_state_dir", lambda: tmp_path)
    monkeypatch.setenv("TAO_FOUNDER_TELEGRAM_USER_ID", FOUNDER)
    # Host clock well behind the message dates, so only the sender check can
    # refuse (an earlier revision's host-clock window would otherwise mask it).
    state = importlib.import_module("swarm.kill_switch_state")
    monkeypatch.setattr(state.time, "time", lambda: float(T - 1000))
    for var in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    return importlib.import_module("swarm.kill_switch")


def _msg(text, date, sender):
    return {"text": text, "date": date, "chat": {"id": int(ALERT_CHAT)}, **sender}


def _via_webhook(monkeypatch):
    import app.server.config as cfg
    from app.server.routes.webhooks import router
    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(cfg, "TELEGRAM_WEBHOOK_SECRET", "hook-secret")
    app = FastAPI()
    app.include_router(router)
    client, uid = TestClient(app), iter(range(95_000, 96_000))

    def send(text, date, sender):
        resp = client.post("/webhook/telegram",
                           headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
                           json={"update_id": next(uid), "message": _msg(text, date, sender)})
        assert resp.status_code == 200
    return send


def _via_poller(monkeypatch):
    from swarm.bots import chief_of_staff
    uid = iter(range(1, 1000))

    def send(text, date, sender):
        body = json.dumps({"ok": True, "result": [
            {"update_id": next(uid), "message": _msg(text, date, sender)}]}).encode()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return body
        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp())
        chief_of_staff._poll_telegram(0)
    return send


PATHS = {"webhook": _via_webhook, "poller": _via_poller}


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("command", ["/resume", "/resume-confirm manual"])
@pytest.mark.parametrize("who", SENDERS)
def test_resume_from_anyone_but_the_founder_is_refused(ks, monkeypatch, path, command, who):
    send = PATHS[path](monkeypatch)
    send("/panic", T, {"from": FOUNDER_FROM})
    send(command, T + 5, SENDERS[who])
    assert ks.is_active()


@pytest.mark.parametrize("path", PATHS)
def test_resume_refused_while_the_founder_id_is_unset(ks, monkeypatch, path):
    send = PATHS[path](monkeypatch)
    send("/panic", T, {"from": FOUNDER_FROM})
    monkeypatch.delenv("TAO_FOUNDER_TELEGRAM_USER_ID")
    send("/resume", T + 5, {"from": FOUNDER_FROM})
    assert ks.is_active()


@pytest.mark.parametrize("path", PATHS)
def test_founder_in_person_resumes(ks, monkeypatch, path):
    send = PATHS[path](monkeypatch)
    send("/panic", T, {"from": FOUNDER_FROM})
    send("/resume", T + 5, {"from": FOUNDER_FROM})
    assert not ks.is_active()


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("who", SENDERS)
def test_panic_stays_open_to_any_member(ks, monkeypatch, path, who):
    send = PATHS[path](monkeypatch)
    send("/panic", T, SENDERS[who])
    assert ks.is_active()


def test_handle_command_refuses_resume_by_default(ks):
    ks.handle_command("/panic", sent_at=float(T))
    assert ks.handle_command("/resume", observed_id=ks.panic_id(),
                             sent_at=float(T + 5)) == "refused: not_founder"
    assert ks.is_active()


def test_founder_resume_without_a_message_date_is_refused(ks):
    ks.handle_command("/panic", sent_at=float(T))
    out = ks.handle_command("/resume", observed_id=ks.panic_id(), from_founder=True)
    assert out == "refused: no_message_date"
    assert ks.is_active()


@pytest.mark.parametrize("path", PATHS)
def test_undated_founder_resume_is_refused_on_both_paths(ks, monkeypatch, path):
    send = PATHS[path](monkeypatch)
    send("/panic", T, {"from": FOUNDER_FROM})
    send("/resume", None, {"from": FOUNDER_FROM})
    assert ks.is_active()
