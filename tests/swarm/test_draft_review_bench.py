"""Security bench findings on ef4819fa (eng-authz), pinned through the real paths.

Same fixture as test_founder_approval_path.py, which uses the REAL
audit_emit.row against a temp SWARM_LOG_DIR:

1. A rejected or failing reaction is audited and contained: the poller still
   advances its offset and reaches /panic later in the same batch.
2. The webhook thread and the orchestrator thread cannot lose each other's
   draft writes, and one draft is never sent twice.
3. Only an emoji the founder just added counts; a 👍 left on a card deferred
   by the kill switch needs a fresh 👍 after resume.
5. The review card escapes the draft text, so the founder sees what is stored.
6. The reversible auto tier honours the kill switch.
"""
from __future__ import annotations

import html
import itertools
import threading

from swarm import draft_review, kill_switch, review_authority
from swarm.bots import chief_of_staff

import test_founder_approval_path as base
from test_founder_approval_path import (
    ALERT_CHAT, FOUNDER, OTHER, REVIEW_CHAT, _audit_types, _cfo_pending, _reaction_update, _status)

env = base.env


def _panic(update_id):
    return {"update_id": update_id, "message": {"text": "/panic bench", "chat": {"id": int(ALERT_CHAT)}}}


# ── 1. audit type is valid; per-update failures are contained ────────────────

def test_rejected_reaction_is_audited_and_poller_reaches_panic(env):
    d = _cfo_pending()
    env.updates = [_reaction_update(1, chat=REVIEW_CHAT, user=OTHER), _panic(2)]
    _, offset = chief_of_staff._poll_telegram(0)
    assert offset == 2
    assert kill_switch.is_active()
    assert "draft_reaction_rejected" in _audit_types()
    assert _status(d.draft_id) == "pending"


def test_reaction_handler_error_is_audited_and_never_propagates(env, monkeypatch):
    _cfo_pending()

    def boom(**_kw):
        raise RuntimeError("disk full")
    monkeypatch.setattr(draft_review, "mark_reaction", boom)
    env.updates = [_reaction_update(1, chat=REVIEW_CHAT, user=FOUNDER), _panic(2)]
    _, offset = chief_of_staff._poll_telegram(0)
    assert offset == 2
    assert kill_switch.is_active()
    assert "draft_reaction_failed" in _audit_types()
    assert env.sends == []


# ── 2. one lock across load-modify-save; "sending" persisted before the send ─

def test_interleaved_writers_lose_no_draft(env, monkeypatch):
    """Writer A loads the snapshot, then pauses; writer B posts a draft in the
    gap. Without the lock A saves its stale copy and B's draft is lost."""
    first = _cfo_pending()
    ids = itertools.count(600)
    monkeypatch.setattr(draft_review, "_post_review_message", lambda text: str(next(ids)))
    real_load, b_done, paused = draft_review._load_snapshot, threading.Event(), []

    def slow_load():
        snap = real_load()
        if threading.current_thread().name == "writer-a" and not paused:
            paused.append(1)
            b_done.wait(timeout=1.0)
        return snap
    monkeypatch.setattr(draft_review, "_load_snapshot", slow_load)
    a = threading.Thread(name="writer-a", target=lambda: draft_review.mark_reaction(
        review_message_id="555", emoji="❌", actor_user_id=FOUNDER, chat_id=REVIEW_CHAT))
    a.start()
    while not paused:
        pass
    second = _cfo_pending()
    b_done.set()
    a.join(timeout=5)
    snap = real_load()
    assert snap[first.draft_id]["status"] == "revise"
    assert second.draft_id in snap and snap[second.draft_id]["status"] == "pending"


def test_second_thumbs_up_during_send_does_not_send_twice(env, monkeypatch):
    """While the first 👍's send is in flight, a second 👍 and a new draft land.
    The draft is sent once, ends "sent", and the new draft survives."""
    first = _cfo_pending()
    ids = itertools.count(600)
    monkeypatch.setattr(draft_review, "_post_review_message", lambda text: str(next(ids)))
    in_send, release, sends = threading.Event(), threading.Event(), []

    def slow_send(rec):
        sends.append(rec["draft_id"])
        if len(sends) == 1:
            in_send.set()
            release.wait(timeout=5)
        return True
    monkeypatch.setattr(draft_review, "_do_send", slow_send)
    approve = dict(review_message_id="555", emoji="👍", actor_user_id=FOUNDER, chat_id=REVIEW_CHAT)
    a = threading.Thread(target=lambda: draft_review.mark_reaction(**approve))
    a.start()
    assert in_send.wait(timeout=5)
    assert _status(first.draft_id) == "sending"
    second = _cfo_pending()
    draft_review.mark_reaction(**approve)
    release.set()
    a.join(timeout=5)
    assert sends == [first.draft_id]
    assert _status(first.draft_id) == "sent"
    assert _status(second.draft_id) == "pending"


# ── 3. only newly added emoji count ──────────────────────────────────────────

def _change(update_id, old, new):
    return {"update_id": update_id, "message_reaction": {
        "chat": {"id": int(REVIEW_CHAT)}, "message_id": 555, "user": {"id": int(FOUNDER)},
        "old_reaction": [{"type": "emoji", "emoji": e} for e in old],
        "new_reaction": [{"type": "emoji", "emoji": e} for e in new]}}


def test_remembered_thumbs_up_needs_a_fresh_one_after_resume(env):
    d = _cfo_pending()
    kill_switch.trigger("telegram_panic", reason="bench")
    env.updates = [_change(1, [], ["👍"])]
    chief_of_staff._poll_telegram(0)
    assert _status(d.draft_id) == "deferred"
    kill_switch.resume("test", reason="bench", confirmed=True)
    env.updates = [_change(2, ["👍"], ["👍", "🔥"]), _change(3, ["👍", "🔥"], ["👍"])]
    chief_of_staff._poll_telegram(1)
    assert _status(d.draft_id) == "deferred"
    assert env.sends == []
    env.updates = [_change(4, ["👍"], []), _change(5, [], ["👍"])]
    chief_of_staff._poll_telegram(3)
    assert _status(d.draft_id) == "sent"
    assert env.sends == [d.draft_id]


def test_forward_reaction_ignores_emoji_already_present(monkeypatch):
    seen = []
    monkeypatch.setattr(draft_review, "mark_reaction", lambda **kw: seen.append(kw["emoji"]))
    review_authority.forward_reaction(_change(1, ["👍", "❌"], ["❌", "👍", "⏳", "⏳"])["message_reaction"])
    assert seen == ["⏳"]


# ── 5. the review card escapes user-supplied text ────────────────────────────

def test_review_card_escapes_draft_markup(env, monkeypatch):
    cards = []
    monkeypatch.setattr(draft_review, "_post_review_message", lambda text: cards.append(text) or "555")
    out = draft_review.post_draft(
        draft_text="Pay <b>5</b> to <a href='x'>Acme</a> & co </code>",
        destination_chat_id="<i>9</i>", drafted_by_role="CFO<u>")
    rec = draft_review._load_snapshot()[out["draft_id"]]
    card = cards[0]
    assert html.escape(rec["draft_text"]) in card
    for raw in ("<a href", "<b>5", "</code> ", "<i>9", "CFO<u>"):
        assert raw not in card


# ── 6. the auto tier honours the kill switch ─────────────────────────────────

def test_auto_tier_defers_when_kill_switch_active(env):
    kill_switch.trigger("telegram_panic", reason="bench")
    out = draft_review.post_draft(draft_text="reversible note", destination_chat_id="42",
                                  drafted_by_role="CoS", reversibility="reversible")
    assert out["status"] == "deferred"
    assert env.sends == []


# ── Codex round on 7da9f064: a /panic after "sending" is saved still stops it ─

def _panic_once_sending_is_saved(monkeypatch):
    real_save = draft_review._save_snapshot

    def save(snap):
        real_save(snap)
        if any(r.get("status") == "sending" for r in snap.values()) and not kill_switch.is_active():
            kill_switch.trigger("telegram_panic", reason="panic during approval")
    monkeypatch.setattr(draft_review, "_save_snapshot", save)


def test_panic_after_sending_saved_defers_direct_approval(env, monkeypatch):
    d = _cfo_pending()
    _panic_once_sending_is_saved(monkeypatch)
    out = draft_review.mark_reaction(review_message_id="555", emoji="👍",
                                     actor_user_id=FOUNDER, chat_id=REVIEW_CHAT)
    assert kill_switch.is_active()
    assert env.sends == []
    assert out["status"] == "deferred"
    assert _status(d.draft_id) == "deferred"
