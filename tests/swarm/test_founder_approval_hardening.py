"""Hardening of the founder-approval path (review round on 9e534212).

Same fixture and helpers as test_founder_approval_path.py. These pin:
a draft with no recorded posting chat never approves; a malformed founder ID
or a null / non-integer reactor authorises nothing; and a kill switch engaged
before the send (including /panic earlier in the same update batch) stops it.
"""
from __future__ import annotations

import pytest

from swarm import config, draft_review, review_authority
from swarm.bots import chief_of_staff

import test_founder_approval_path as base
from test_founder_approval_path import (
    ALERT_CHAT, FOUNDER, REVIEW_CHAT, _audit_types, _cfo_pending, _reaction_update, _status)

env = base.env  # the shared fixture, registered in this module too


def _legacy_pending(env):
    """A pending draft saved before review_chat_id existed (posted in ALERT_CHAT)."""
    d = _cfo_pending()
    snap = draft_review._load_snapshot()
    snap[d.draft_id].pop("review_chat_id", None)
    draft_review._save_snapshot(snap)
    return d


def test_draft_without_recorded_chat_never_approves(env):
    d = _legacy_pending(env)
    for chat in (REVIEW_CHAT, ALERT_CHAT):
        env.updates = [_reaction_update(1, chat=chat, user=FOUNDER)]
        chief_of_staff._poll_telegram(0)
    assert _status(d.draft_id) == "pending"
    assert env.sends == []
    assert "draft_reaction_rejected" in _audit_types()


@pytest.mark.parametrize("bad", ["None", "null", "0", "-5", "12a", "+8000001", "8000001.0", "1" * 21, "abc"])
def test_malformed_founder_id_authorises_nothing(env, monkeypatch, bad):
    monkeypatch.setenv(review_authority.FOUNDER_TELEGRAM_USER_ID_ENV, bad)
    d = _cfo_pending()
    upd = _reaction_update(1, chat=REVIEW_CHAT, user=FOUNDER)
    upd["message_reaction"]["user"] = {"id": None}
    env.updates = [upd, _reaction_update(2, chat=REVIEW_CHAT, user=FOUNDER),
                   {"update_id": 3, "message_reaction": {
                       "chat": {"id": int(REVIEW_CHAT)}, "message_id": 555,
                       "new_reaction": [{"type": "emoji", "emoji": "👍"}]}}]
    chief_of_staff._poll_telegram(0)
    assert _status(d.draft_id) == "pending"
    assert env.sends == []


@pytest.mark.parametrize("actor", [None, "None", "", "abc", True, 1.5, {"id": 1}])
def test_null_or_non_integer_actor_never_matches(env, monkeypatch, actor):
    d = _cfo_pending()
    upd = _reaction_update(1, chat=REVIEW_CHAT, user=FOUNDER)
    upd["message_reaction"]["user"] = {"id": actor}
    env.updates = [upd]
    chief_of_staff._poll_telegram(0)
    assert _status(d.draft_id) == "pending"
    assert env.sends == []


def test_panic_then_founder_thumbs_up_in_one_batch_sends_nothing(env, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SWARM_LOG_DIR", tmp_path / "swarmlog")
    d = _cfo_pending()
    env.updates = [
        {"update_id": 1, "message": {"text": "/panic stop", "chat": {"id": int(ALERT_CHAT)}}},
        _reaction_update(2, chat=REVIEW_CHAT, user=FOUNDER),
    ]
    chief_of_staff._poll_telegram(0)
    assert env.sends == []
    assert _status(d.draft_id) != "sent"


def test_active_kill_switch_blocks_direct_founder_approval(env, monkeypatch, tmp_path):
    from swarm import kill_switch
    monkeypatch.setattr(config, "SWARM_LOG_DIR", tmp_path / "swarmlog")
    d = _cfo_pending()
    kill_switch.trigger("telegram_panic", reason="test")
    out = draft_review.mark_reaction(review_message_id="555", emoji="👍",
                                     actor_user_id=FOUNDER, chat_id=REVIEW_CHAT)
    assert out["status"] == "deferred"
    assert _status(d.draft_id) == "deferred"
    assert env.sends == []


@pytest.mark.parametrize("bad", ["None", "null", "0", "-5", "12a", "+8000001", "1" * 21])
def test_malformed_founder_id_reads_as_unset(monkeypatch, bad):
    monkeypatch.setenv(review_authority.FOUNDER_TELEGRAM_USER_ID_ENV, bad)
    assert review_authority.founder_telegram_user_id() == ""


@pytest.mark.parametrize("raw", [None, "None", "", True, 1.5, "abc", 0])
def test_forwarded_actor_is_none_unless_a_valid_user_id(monkeypatch, raw):
    seen = []
    monkeypatch.setattr(draft_review, "mark_reaction", lambda **kw: seen.append(kw))
    review_authority.forward_reaction({
        "chat": {"id": 456}, "message_id": 555, "user": {"id": raw},
        "new_reaction": [{"type": "emoji", "emoji": "👍"}]})
    assert [kw["actor_user_id"] for kw in seen] == [None]


def test_swarm_disabled_defers_founder_approval(env, monkeypatch):
    monkeypatch.setenv("TAO_SWARM_ENABLED", "0")
    d = _cfo_pending()
    out = draft_review.mark_reaction(review_message_id="555", emoji="👍",
                                     actor_user_id=FOUNDER, chat_id=REVIEW_CHAT)
    assert out["status"] == "deferred"
    assert _status(d.draft_id) == "deferred"
    assert env.sends == []


# Review round on ef4819fa: a padded ID normalised to the founder's must not
# approve. These configure values that strip() would turn into FOUNDER, so the
# parser itself is what has to reject them.
PADDED = [" 8000001", "8000001 ", " 8000001 ", "8000001\n", "\t8000001", "8000001\r\n"]


@pytest.mark.parametrize("padded", PADDED)
def test_padded_founder_id_authorises_nothing_through_poller(env, monkeypatch, padded):
    monkeypatch.setenv(review_authority.FOUNDER_TELEGRAM_USER_ID_ENV, padded)
    d = _cfo_pending()
    env.updates = [_reaction_update(1, chat=REVIEW_CHAT, user=FOUNDER)]
    chief_of_staff._poll_telegram(0)
    assert _status(d.draft_id) == "pending"
    assert env.sends == []


@pytest.mark.parametrize("padded", PADDED)
def test_padded_reactor_id_authorises_nothing_through_poller(env, monkeypatch, padded):
    d = _cfo_pending()
    upd = _reaction_update(1, chat=REVIEW_CHAT, user=FOUNDER)
    upd["message_reaction"]["user"] = {"id": padded}
    env.updates = [upd]
    chief_of_staff._poll_telegram(0)
    assert _status(d.draft_id) == "pending"
    assert env.sends == []


@pytest.mark.parametrize("padded", PADDED)
def test_padded_ids_parse_as_invalid(monkeypatch, padded):
    assert review_authority.telegram_user_id(padded) is None
    monkeypatch.setenv(review_authority.FOUNDER_TELEGRAM_USER_ID_ENV, padded)
    assert review_authority.founder_telegram_user_id() == ""
