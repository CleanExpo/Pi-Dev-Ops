"""Tests for the env-gated client -> Board fan-out in intake_router."""
from __future__ import annotations

import pytest

from swarm.inbox import intake_router as ir


def _bot(kind="client", context_id="dimitri-itr", username="UniteGroupDimitriItrBot"):
    return ir.Bot(
        id="b1", bot_username=username, bot_token="t", kind=kind, brand="unite-group",
        context_id=context_id, context_label="Duncan — ITR", linear_team_key="UNI",
        linear_project_id=None, wiki_section=None, greeting_template=None,
        auto_reply_enabled=False, long_poll_offset=0, authorized_chat_ids=[],
    )


_MSG = {"chat": {"id": 4242}, "from": {"id": 1}, "text": "Need an ITR status update"}


def test_fanout_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INTAKE_BOARD_FANOUT", raising=False)
    called = {"n": 0}
    import swarm.bots.board as board
    monkeypatch.setattr(board, "from_margot", lambda **k: called.__setitem__("n", called["n"] + 1) or "x")
    assert ir._maybe_fanout_to_board(_bot(), _MSG, "hello") is None
    assert called["n"] == 0


@pytest.mark.parametrize("flag", ["1", "true", "YES", "on"])
def test_fanout_fires_for_client_when_enabled(monkeypatch, flag):
    monkeypatch.setenv("INTAKE_BOARD_FANOUT", flag)
    calls = []
    import swarm.bots.board as board
    monkeypatch.setattr(board, "from_margot",
                        lambda **k: calls.append(k) or "board-sess-7")
    sid = ir._maybe_fanout_to_board(_bot(), _MSG, "Need a status update")
    assert sid == "board-sess-7"
    assert len(calls) == 1
    assert "Need a status update" in calls[0]["insight"]
    assert "dimitri-itr" in calls[0]["insight"]


def test_non_client_bot_never_fans_out(monkeypatch):
    monkeypatch.setenv("INTAKE_BOARD_FANOUT", "1")
    import swarm.bots.board as board
    monkeypatch.setattr(board, "from_margot", lambda **k: pytest.fail("should not call"))
    assert ir._maybe_fanout_to_board(_bot(kind="function"), _MSG, "x") is None


def test_board_failure_is_swallowed(monkeypatch):
    monkeypatch.setenv("INTAKE_BOARD_FANOUT", "1")
    import swarm.bots.board as board

    def _boom(**k):
        raise RuntimeError("board down")

    monkeypatch.setattr(board, "from_margot", _boom)
    # Must not raise — fan-out is fire-and-forget.
    assert ir._maybe_fanout_to_board(_bot(), _MSG, "x") is None


def test_enabled_flag_parsing(monkeypatch):
    monkeypatch.setenv("INTAKE_BOARD_FANOUT", "off")
    assert ir._board_fanout_enabled() is False
    monkeypatch.setenv("INTAKE_BOARD_FANOUT", "1")
    assert ir._board_fanout_enabled() is True
