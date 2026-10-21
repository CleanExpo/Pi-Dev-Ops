"""Founder draft approvals arrive by webhook in production (review 9e534212).

In webhook mode getUpdates receives nothing, so the authenticated
/webhook/telegram route must hand message_reaction updates to
review_authority with the same founder, chat and kill-switch checks the
poller uses. All network calls are mocked.

Modules are resolved per test: other tests reload or drop swarm.* from
sys.modules, and the route imports whatever is current at call time.
"""
from __future__ import annotations

import importlib
import itertools
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

FOUNDER = "8000001"
OTHER = "999"
REVIEW_CHAT = "456"


def _client() -> TestClient:
    from app.server.auth import require_rate_limit
    from app.server.routes.webhooks import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_rate_limit] = lambda: None
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def env(monkeypatch, tmp_path):
    import app.server.config as cfg
    cfo, draft_review, review_authority, swarm_config = (
        importlib.import_module(f"swarm.{m}")
        for m in ("cfo", "draft_review", "review_authority", "config"))

    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(cfg, "TELEGRAM_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr(draft_review, "TEST_MODE", False)
    monkeypatch.setattr(draft_review, "_state_dir", lambda: tmp_path)
    monkeypatch.setattr(swarm_config, "TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(swarm_config, "SWARM_LOG_DIR", tmp_path / "swarmlog")
    monkeypatch.setenv("REVIEW_CHAT_ID", REVIEW_CHAT)
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")
    monkeypatch.setenv(review_authority.FOUNDER_TELEGRAM_USER_ID_ENV, FOUNDER)
    for var in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(draft_review, "_post_review_message", lambda text: "555")
    sends: list[str] = []
    monkeypatch.setattr(draft_review, "_do_send", lambda rec: sends.append(rec["draft_id"]) or True)
    d = cfo.approve_spend(amount_usd=1.0, vendor="V", business_id="b",
                          justification="j", post_draft=draft_review.post_draft)
    assert d.status == "pending"
    return d.draft_id, sends


_UPDATE_IDS = itertools.count(1)  # each call is a new Telegram update unless replayed


def _post(*, user, chat=REVIEW_CHAT, secret="hook-secret", update_id=None):
    return _client().post(
        "/webhook/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": secret},
        json={"update_id": update_id or next(_UPDATE_IDS), "message_reaction": {
            "chat": {"id": int(chat)}, "message_id": 555, "user": {"id": int(user)},
            "new_reaction": [{"type": "emoji", "emoji": "👍"}]}},
    )


def _status(draft_id):
    return importlib.import_module("swarm.draft_review")._load_snapshot()[draft_id]["status"]


def test_founder_reaction_by_webhook_approves(env):
    draft_id, sends = env
    assert _post(user=FOUNDER).status_code == 200
    assert _status(draft_id) == "sent"
    assert sends == [draft_id]


def test_non_founder_reaction_by_webhook_does_nothing(env):
    draft_id, sends = env
    assert _post(user=OTHER).status_code == 200
    assert _post(user=FOUNDER, chat="777").status_code == 200
    assert _status(draft_id) == "pending"
    assert sends == []


def test_bad_secret_reaction_is_refused(env):
    draft_id, sends = env
    assert _post(user=FOUNDER, secret="wrong").status_code == 401
    assert _status(draft_id) == "pending"
    assert sends == []


def test_webhook_reaction_after_kill_switch_does_not_send(env):
    draft_id, sends = env
    importlib.import_module("swarm.kill_switch").trigger("telegram_panic", reason="test")
    assert _post(user=FOUNDER).status_code == 200
    assert sends == []
    assert _status(draft_id) != "sent"


PADDED = [" 8000001", "8000001 ", "8000001\n", "\t8000001"]


def _post_raw_user(user_id):
    return _client().post(
        "/webhook/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        json={"update_id": next(_UPDATE_IDS), "message_reaction": {
            "chat": {"id": int(REVIEW_CHAT)}, "message_id": 555, "user": {"id": user_id},
            "new_reaction": [{"type": "emoji", "emoji": "👍"}]}},
    )


@pytest.mark.parametrize("padded", PADDED)
def test_padded_founder_env_by_webhook_does_nothing(env, monkeypatch, padded):
    draft_id, sends = env
    ra = importlib.import_module("swarm.review_authority")
    monkeypatch.setenv(ra.FOUNDER_TELEGRAM_USER_ID_ENV, padded)
    assert _post(user=FOUNDER).status_code == 200
    assert _status(draft_id) == "pending"
    assert sends == []


@pytest.mark.parametrize("padded", PADDED)
def test_padded_reactor_id_by_webhook_does_nothing(env, padded):
    draft_id, sends = env
    assert _post_raw_user(padded).status_code == 200
    assert _status(draft_id) == "pending"
    assert sends == []


# Security bench on ef4819fa ─────────────────────────────────────────────────

def _audit_types():
    p = importlib.import_module("swarm.config").SWARM_LOG_DIR / "swarm.jsonl"
    return [json.loads(line)["type"] for line in p.read_text().splitlines()] if p.exists() else []


def test_rejected_reaction_by_webhook_is_audited_not_a_500(env):
    """The real audit_emit.row once raised on draft_reaction_rejected, so a
    non-founder 👍 by webhook returned 500."""
    draft_id, sends = env
    assert _post(user=OTHER).status_code == 200
    assert "draft_reaction_rejected" in _audit_types()
    assert _status(draft_id) == "pending"
    assert sends == []


def test_replayed_webhook_update_cannot_re_approve(env):
    """A 👍 deferred by the kill switch, replayed after /resume with the same
    or an older update_id, must not send. A new update still can."""
    draft_id, sends = env
    ks = importlib.import_module("swarm.kill_switch")
    ks.trigger("telegram_panic", reason="test")
    assert _post(user=FOUNDER, update_id=10_000).status_code == 200
    assert _status(draft_id) == "deferred"
    ks.resume("test", reason="test", confirmed=True)
    for replay in (10_000, 9_999):
        assert _post(user=FOUNDER, update_id=replay).status_code == 200
    assert _status(draft_id) == "deferred"
    assert sends == []
    assert _post(user=FOUNDER, update_id=10_001).status_code == 200
    assert _status(draft_id) == "sent"
    assert sends == [draft_id]


@pytest.mark.parametrize("update_id", [None, "10", True, 1.5])
def test_webhook_reaction_without_an_integer_update_id_is_dropped(env, update_id):
    draft_id, sends = env
    resp = _client().post(
        "/webhook/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        json={"update_id": update_id, "message_reaction": {
            "chat": {"id": int(REVIEW_CHAT)}, "message_id": 555, "user": {"id": int(FOUNDER)},
            "new_reaction": [{"type": "emoji", "emoji": "👍"}]}})
    assert resp.status_code == 200
    assert _status(draft_id) == "pending"
    assert sends == []


def test_panic_after_sending_saved_defers_webhook_approval(env, monkeypatch):
    """Codex round on 7da9f064: the halt is re-checked right before the send."""
    draft_id, sends = env
    dr = importlib.import_module("swarm.draft_review")
    ks = importlib.import_module("swarm.kill_switch")
    real_save = dr._save_snapshot

    def save(snap):
        real_save(snap)
        if any(r.get("status") == "sending" for r in snap.values()) and not ks.is_active():
            ks.trigger("telegram_panic", reason="panic during approval")
    monkeypatch.setattr(dr, "_save_snapshot", save)
    assert _post(user=FOUNDER).status_code == 200
    assert ks.is_active()
    assert sends == []
    assert _status(draft_id) == "deferred"
