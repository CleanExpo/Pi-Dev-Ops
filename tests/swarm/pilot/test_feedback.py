"""Tests for feedback.py — 5 callback handlers per ADR 003.

Each handler: state-machine update + editMessageReplyMarkup + (for discuss) voice prompt.
Pause-state transitions honour the two-verb contract: paused-until-{ts} vs paused-hard.
STOP halts interactive stream only — L4 digest scope separation tested separately.
"""
from unittest.mock import MagicMock, patch
from swarm.pilot import feedback


def _mem(msg=None):
    m = MagicMock()
    m.get_suggestion.return_value = {"id": 1, "fingerprint": "fp", "body_json": {}}
    m.get_message_for_suggestion.return_value = msg
    return m


def test_agree_marks_accepted_and_greys_buttons():
    m = _mem(msg={"chat_id": 999, "message_id": 7})
    with patch("swarm.pilot.feedback._edit_reply_markup") as e:
        feedback.handle_callback("agree|fp", suggestion_id=1, memory=m)
    m.mark_response.assert_called_once_with(1, "agree", "accepted")
    e.assert_called_once()


def test_dismiss_marks_rejected():
    m = _mem(msg={"chat_id": 999, "message_id": 7})
    with patch("swarm.pilot.feedback._edit_reply_markup"):
        feedback.handle_callback("dismiss|fp", suggestion_id=1, memory=m)
    m.mark_response.assert_called_once_with(1, "dismiss", "rejected")


def test_discuss_marks_in_discussion_and_prompts_voice():
    m = _mem(msg={"chat_id": 999, "message_id": 7})
    with patch("swarm.pilot.feedback._edit_reply_markup"), \
         patch("swarm.pilot.feedback._prompt_voice_reply") as v:
        feedback.handle_callback("discuss|fp", suggestion_id=1, memory=m)
    v.assert_called_once_with(chat_id=999, suggestion_id=1)
    m.mark_response.assert_called_once_with(1, "discuss", "in_discussion")


def test_pause_24h_sets_paused_until_iso_timestamp(monkeypatch):
    m = _mem(msg={"chat_id": 999, "message_id": 7})
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    with patch("swarm.pilot.feedback._edit_reply_markup"):
        feedback.handle_callback("pause_24h|fp", suggestion_id=1, memory=m)
    call = m.set_pause_state.call_args
    assert call.args[0] == "phill"
    assert call.args[1].startswith("paused-until-")


def test_stop_sets_paused_hard(monkeypatch):
    m = _mem(msg={"chat_id": 999, "message_id": 7})
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    with patch("swarm.pilot.feedback._edit_reply_markup"):
        feedback.handle_callback("stop|fp", suggestion_id=1, memory=m)
    m.set_pause_state.assert_called_once_with("phill", "paused-hard")


def test_unknown_action_is_noop():
    m = _mem()
    feedback.handle_callback("garbage|fp", suggestion_id=1, memory=m)
    m.mark_response.assert_not_called()
    m.set_pause_state.assert_not_called()


def test_stop_does_not_call_mark_response(monkeypatch):
    """STOP is a global state transition, not a per-suggestion response."""
    m = _mem(msg={"chat_id": 999, "message_id": 7})
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    with patch("swarm.pilot.feedback._edit_reply_markup"):
        feedback.handle_callback("stop|fp", suggestion_id=1, memory=m)
    m.mark_response.assert_not_called()


def test_pause_24h_does_not_call_mark_response(monkeypatch):
    """PAUSE 24h is a global state transition, not a per-suggestion response."""
    m = _mem(msg={"chat_id": 999, "message_id": 7})
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    with patch("swarm.pilot.feedback._edit_reply_markup"):
        feedback.handle_callback("pause_24h|fp", suggestion_id=1, memory=m)
    m.mark_response.assert_not_called()
