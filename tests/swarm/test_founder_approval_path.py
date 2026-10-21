"""The founder-approval path that every money request uses (21/10/2026).

CFO spend, CMO ad spend and CS refunds post a review ask through
draft_review and wait for a 👍. These tests pin three properties of that path:

1. Only the founder's Telegram user ID can decide a draft. Another chat
   member's 👍 does nothing, and with no founder ID configured nothing can
   approve (fail closed).
2. A reaction decides a draft only in the chat the draft was posted to, and
   the listener hears a review chat that differs from the alert chat.
3. A review ask that was never delivered (post failure, PII abort) is
   reported as "blocked", never "pending".

Every outbound call is mocked: urllib.request.urlopen is replaced for the
whole test, so no Telegram request can leave the process.
"""
from __future__ import annotations

import json
import types

import pytest

from swarm import audit_emit, cfo, cmo, config, cs, draft_review
from swarm import pii_redactor, review_authority
from swarm.bots import chief_of_staff

FOUNDER = "8000001"
OTHER = "999"
ALERT_CHAT = "123"
REVIEW_CHAT = "456"


class _FakeResp:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Isolated draft state, mocked network, distinct review and alert chats."""
    monkeypatch.setattr(draft_review, "TEST_MODE", False)
    monkeypatch.setattr(draft_review, "_state_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-token-not-real")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", ALERT_CHAT)
    monkeypatch.setenv("REVIEW_CHAT_ID", REVIEW_CHAT)
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")
    monkeypatch.setenv(review_authority.FOUNDER_TELEGRAM_USER_ID_ENV, FOUNDER)
    monkeypatch.setattr(audit_emit, "row", lambda *a, **k: None)

    state = types.SimpleNamespace(sends=[], updates=[], other_requests=[])

    def fake_urlopen(req, timeout=None):
        url = getattr(req, "full_url", str(req))
        if url.endswith("/getUpdates"):
            return _FakeResp({"ok": True, "result": state.updates})
        state.other_requests.append(url)
        raise AssertionError(f"unexpected outbound request: {url}")

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(draft_review, "_post_review_message", lambda text: "555")
    monkeypatch.setattr(draft_review, "_do_send",
                        lambda rec: state.sends.append(rec["draft_id"]) or True)
    return state


def _cfo_pending():
    d = cfo.approve_spend(amount_usd=1.0, vendor="V", business_id="b",
                          justification="j", post_draft=draft_review.post_draft)
    assert d.status == "pending", d
    return d


def _status(draft_id):
    return draft_review._load_snapshot()[draft_id]["status"]


def _reaction_update(update_id, *, chat, user, msg="555", emoji="👍"):
    return {"update_id": update_id, "message_reaction": {
        "chat": {"id": int(chat)}, "message_id": int(msg),
        "user": {"id": int(user)}, "new_reaction": [{"type": "emoji", "emoji": emoji}],
    }}


# ── 1. Founder-bound approval ────────────────────────────────────────────────

def test_non_founder_thumbs_up_is_rejected(env):
    d = _cfo_pending()
    out = draft_review.mark_reaction(review_message_id="555", emoji="👍",
                                     actor_user_id=OTHER, chat_id=REVIEW_CHAT)
    assert out is None
    assert _status(d.draft_id) == "pending"
    assert env.sends == []


def test_founder_thumbs_up_is_accepted_and_actor_recorded(env):
    d = _cfo_pending()
    out = draft_review.mark_reaction(review_message_id="555", emoji="👍",
                                     actor_user_id=FOUNDER, chat_id=REVIEW_CHAT)
    assert out["status"] == "sent"
    assert out["decided_by_user_id"] == FOUNDER
    assert out["transitions"][-1]["actor_user_id"] == FOUNDER
    assert env.sends == [d.draft_id]


def test_no_founder_id_configured_means_nothing_approves(env, monkeypatch):
    monkeypatch.delenv(review_authority.FOUNDER_TELEGRAM_USER_ID_ENV, raising=False)
    d = _cfo_pending()
    for actor in (FOUNDER, OTHER, None, ""):
        out = draft_review.mark_reaction(review_message_id="555", emoji="👍",
                                         actor_user_id=actor, chat_id=REVIEW_CHAT)
        assert out is None
    assert _status(d.draft_id) == "pending"
    assert env.sends == []


def test_poller_passes_reactor_identity(env):
    d = _cfo_pending()
    env.updates = [_reaction_update(1, chat=REVIEW_CHAT, user=OTHER)]
    chief_of_staff._poll_telegram(0)
    assert _status(d.draft_id) == "pending"
    env.updates = [_reaction_update(2, chat=REVIEW_CHAT, user=FOUNDER)]
    chief_of_staff._poll_telegram(1)
    assert _status(d.draft_id) == "sent"
    assert env.sends == [d.draft_id]


# ── 2. Review chat binding ───────────────────────────────────────────────────

def test_draft_records_the_chat_it_was_posted_to(env):
    d = _cfo_pending()
    assert draft_review._load_snapshot()[d.draft_id]["review_chat_id"] == REVIEW_CHAT


def test_founder_thumbs_up_in_separate_review_chat_approves(env):
    d = _cfo_pending()
    env.updates = [_reaction_update(1, chat=REVIEW_CHAT, user=FOUNDER)]
    _, offset = chief_of_staff._poll_telegram(0)
    assert offset == 1
    assert _status(d.draft_id) == "sent"


def test_same_message_id_in_another_chat_does_not_approve(env):
    d = _cfo_pending()
    env.updates = [_reaction_update(1, chat=ALERT_CHAT, user=FOUNDER),
                   _reaction_update(2, chat="777", user=FOUNDER)]
    chief_of_staff._poll_telegram(0)
    assert _status(d.draft_id) == "pending"
    assert env.sends == []
    assert draft_review.mark_reaction(review_message_id="555", emoji="👍",
                                      actor_user_id=FOUNDER, chat_id=None) is None


# ── 3. Undelivered review asks are blocked, never pending ────────────────────

def _money_calls():
    return {
        "cfo": lambda: cfo.approve_spend(
            amount_usd=10.0, vendor="V", business_id="b", justification="j",
            post_draft=draft_review.post_draft),
        "cmo": lambda: cmo.approve_adspend(
            amount_usd_per_day=10.0, channel="google", business_id="b",
            justification="j", post_draft=draft_review.post_draft),
        "cs": lambda: cs.approve_refund(
            amount_usd=10.0, customer_id="c1", business_id="b",
            justification="j", post_draft=draft_review.post_draft),
    }


@pytest.mark.parametrize("which", ["cfo", "cmo", "cs"])
def test_review_post_failure_is_blocked(env, monkeypatch, caplog, which):
    monkeypatch.setattr(draft_review, "_post_review_message", lambda text: None)
    d = _money_calls()[which]()
    assert d.status == "blocked"
    assert "founder review undelivered" in caplog.text
    assert _status(d.draft_id) == "queued"
    assert draft_review.list_pending() == []


@pytest.mark.parametrize("which", ["cfo", "cmo", "cs"])
def test_pii_abort_is_blocked(env, monkeypatch, caplog, which):
    aborted = types.SimpleNamespace(passed=False, precision_score=0.1,
                                    redaction_count=3, redacted_payload="")
    monkeypatch.setattr(pii_redactor, "redact", lambda *a, **k: aborted)
    d = _money_calls()[which]()
    assert d.status == "blocked"
    assert "founder review aborted" in caplog.text
    assert d.draft_id is None


@pytest.mark.parametrize("result", [
    {"draft_id": "x", "review_message_id": None, "status": "sent", "policy_level": "auto"},
    {"draft_id": "x", "review_message_id": None, "status": "deferred"},
    {"draft_id": "x"},
])
def test_anything_but_a_delivered_review_ask_is_blocked(result):
    fake = lambda **kw: result  # noqa: E731
    calls = [
        lambda: cfo.approve_spend(amount_usd=1.0, vendor="V", business_id="b",
                                  justification="j", post_draft=fake),
        lambda: cmo.approve_adspend(amount_usd_per_day=1.0, channel="g",
                                    business_id="b", justification="j", post_draft=fake),
        lambda: cs.approve_refund(amount_usd=1.0, customer_id="c", business_id="b",
                                  justification="j", post_draft=fake),
    ]
    for call in calls:
        assert call().status == "blocked"
