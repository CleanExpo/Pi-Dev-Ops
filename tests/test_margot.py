"""tests/test_margot.py — Margot Telegram personal-assistant smoke."""
from __future__ import annotations

import asyncio
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import intent_router  # noqa: E402
from swarm import margot_bot  # noqa: E402
from swarm.bots import margot as margot_bot_wrapper  # noqa: E402


# ── Intent router: margot intent ────────────────────────────────────────────


def test_intent_margot_prefix_match():
    out = intent_router.classify("Margot, what's our CCW state?")
    assert out["intent"] == "margot"
    assert out["confidence"] == 0.95
    # Prefix stripped
    assert out["fields"]["prompt"] == "what's our CCW state?"


def test_intent_margot_at_mention():
    out = intent_router.classify("@margot summarise yesterday")
    assert out["intent"] == "margot"
    assert out["fields"]["prompt"] == "summarise yesterday"


def test_intent_margot_slash_command():
    out = intent_router.classify("/margot research competitor X")
    assert out["intent"] == "margot"
    assert "competitor X" in out["fields"]["prompt"]


def test_intent_margot_hey_pattern():
    out = intent_router.classify("hey Margot, are you there?")
    assert out["intent"] == "margot"


def test_intent_dm_chat_id_routes_to_margot(monkeypatch):
    monkeypatch.setenv("MARGOT_DM_CHAT_ID", "12345")
    out = intent_router.classify(
        "What's the runway looking like?", chat_id="12345",
    )
    assert out["intent"] == "margot"
    assert out["fields"]["addressed_by"] == "dm_chat"
    # Whole message preserved (no prefix stripped in DM mode)
    assert out["fields"]["prompt"] == "What's the runway looking like?"


def test_intent_dm_chat_id_does_not_match_other_chats(monkeypatch):
    monkeypatch.setenv("MARGOT_DM_CHAT_ID", "12345")
    out = intent_router.classify(
        "What's the runway looking like?", chat_id="67890",
    )
    # Different chat → falls through to default classifier
    assert out["intent"] != "margot"


def test_intent_margot_does_not_match_plain_research():
    """Plain research without addressing Margot should still be 'research' intent."""
    out = intent_router.classify("research the latest competitor activity")
    assert out["intent"] == "research"


def test_intent_pii_blocks_margot_route():
    """SSN in 'Margot, ...' message → forced unknown via PII guard."""
    out = intent_router.classify("Margot, my SSN is 123-45-6789")
    assert out["intent"] == "unknown"


# ── Margot persistence ──────────────────────────────────────────────────────


def test_append_and_load_history(tmp_path):
    t1 = margot_bot.MargotTurn(
        chat_id="789", user_text="hi", margot_text="hello",
        started_at="t", ended_at="t",
    )
    t2 = margot_bot.MargotTurn(
        chat_id="789", user_text="how is CCW",
        margot_text="great", started_at="t", ended_at="t",
    )
    margot_bot.append_turn(t1, repo_root=tmp_path)
    margot_bot.append_turn(t2, repo_root=tmp_path)
    history = margot_bot.load_history("789", repo_root=tmp_path)
    assert len(history) == 2
    assert history[0].user_text == "hi"
    assert history[1].user_text == "how is CCW"


def test_load_history_respects_limit(tmp_path):
    for i in range(15):
        t = margot_bot.MargotTurn(
            chat_id="x", user_text=f"q{i}", margot_text=f"a{i}",
            started_at="t", ended_at="t",
        )
        margot_bot.append_turn(t, repo_root=tmp_path)
    out = margot_bot.load_history("x", limit=5, repo_root=tmp_path)
    assert len(out) == 5
    assert out[0].user_text == "q10"
    assert out[-1].user_text == "q14"


def test_load_history_chat_isolation(tmp_path):
    margot_bot.append_turn(margot_bot.MargotTurn(
        chat_id="A", user_text="for A", margot_text="ans",
        started_at="t", ended_at="t",
    ), repo_root=tmp_path)
    margot_bot.append_turn(margot_bot.MargotTurn(
        chat_id="B", user_text="for B", margot_text="ans",
        started_at="t", ended_at="t",
    ), repo_root=tmp_path)
    a = margot_bot.load_history("A", repo_root=tmp_path)
    b = margot_bot.load_history("B", repo_root=tmp_path)
    assert len(a) == 1 and a[0].user_text == "for A"
    assert len(b) == 1 and b[0].user_text == "for B"


# ── Context assembly ────────────────────────────────────────────────────────


def test_build_context_empty_repo(tmp_path):
    ctx = margot_bot.build_context(repo_root=tmp_path)
    assert ctx["cfo"] == [] and ctx["cmo"] == [] and ctx["cto"] == []
    assert ctx["cs"] == [] and ctx["board_recent"] == []
    assert ctx["ccw"] is None


def test_build_context_with_data(tmp_path):
    cfo_dir = tmp_path / ".harness/swarm"
    cfo_dir.mkdir(parents=True, exist_ok=True)
    (cfo_dir / "cfo_state.jsonl").write_text(
        json.dumps({"business_id": "ccw-crm", "mrr": 4500}) + "\n"
        + json.dumps({"business_id": "restoreassist", "mrr": 12000}) + "\n"
    )
    (cfo_dir / "cs_state.jsonl").write_text(
        json.dumps({"business_id": "ccw-crm", "nps": 75}) + "\n"
    )

    ctx = margot_bot.build_context(repo_root=tmp_path)
    assert len(ctx["cfo"]) == 2
    assert ctx["ccw"] is not None
    assert ctx["ccw"]["cfo"]["mrr"] == 4500
    assert ctx["ccw"]["cs"]["nps"] == 75


# ── Prompt construction ─────────────────────────────────────────────────────


def test_build_prompt_includes_user_message():
    out = margot_bot.build_prompt(
        user_text="What's CCW NPS?",
        history=[],
        context={"cfo": [], "cmo": [], "cto": [], "cs": [],
                  "board_recent": [], "ccw": None},
    )
    assert "What's CCW NPS?" in out
    assert "Margot" in out
    assert "(this is the first turn)" in out


def test_build_prompt_includes_history():
    history = [
        margot_bot.MargotTurn(chat_id="x", user_text="prev q",
                                margot_text="prev a"),
    ]
    out = margot_bot.build_prompt(
        user_text="follow up",
        history=history,
        context={"cfo": [], "cmo": [], "cto": [], "cs": [],
                  "board_recent": [], "ccw": None},
    )
    assert "prev q" in out
    assert "prev a" in out
    assert "follow up" in out


# ── Board trigger parsing ──────────────────────────────────────────────────


def test_parse_board_triggers_extracts_and_strips():
    response = '''Here's my analysis.

[BOARD-TRIGGER score=8 topic="Competitor X raised $50M"]
Series B for the largest ANZ competitor implies aggressive expansion
into the restoration vertical. Recommend tracking their hiring + pricing.
[/BOARD-TRIGGER]

Otherwise, the picture looks stable.'''
    triggers, cleaned = margot_bot.parse_board_triggers(response)
    assert len(triggers) == 1
    assert triggers[0].score == 8
    assert "Competitor X" in triggers[0].topic
    assert "$50M" in triggers[0].topic
    assert "Series B" in triggers[0].insight
    # Cleaned response has no sentinel
    assert "[BOARD-TRIGGER" not in cleaned
    assert "Here's my analysis." in cleaned
    assert "Otherwise, the picture looks stable." in cleaned


def test_parse_board_triggers_multiple():
    response = '''Two findings.

[BOARD-TRIGGER score=7 topic="Reg change A"]
A details
[/BOARD-TRIGGER]

[BOARD-TRIGGER score=9 topic="Reg change B"]
B details
[/BOARD-TRIGGER]

That's it.'''
    triggers, cleaned = margot_bot.parse_board_triggers(response)
    assert len(triggers) == 2
    assert triggers[0].score == 7
    assert triggers[1].score == 9
    assert "[BOARD-TRIGGER" not in cleaned


def test_parse_board_triggers_score_clamped():
    response = '[BOARD-TRIGGER score=15 topic="x"]y[/BOARD-TRIGGER]'
    triggers, _ = margot_bot.parse_board_triggers(response)
    assert triggers[0].score == 10  # clamped to max


def test_parse_board_triggers_no_sentinel():
    response = "Just a plain response with no triggers."
    triggers, cleaned = margot_bot.parse_board_triggers(response)
    assert triggers == []
    assert cleaned == response


# ── handle_turn end-to-end ──────────────────────────────────────────────────


def _stub_llm(monkeypatch, *, response_text: str, rc: int = 0,
                cost: float = 0.05):
    async def fake(*, prompt, timeout_s=120, workspace=None, turn_id="", **kw):
        return rc, response_text, cost, None
    monkeypatch.setattr(margot_bot, "_call_llm", fake)


def test_handle_turn_happy_path(tmp_path, monkeypatch):
    _stub_llm(monkeypatch, response_text="CCW NPS is 72; healthy.")

    turn = asyncio.run(margot_bot.handle_turn(
        chat_id="789", user_text="What's CCW NPS?",
        repo_root=tmp_path, _send=False,
    ))
    assert not turn.error
    assert turn.margot_text == "CCW NPS is 72; healthy."
    assert turn.cost_usd == 0.05

    # Persisted to conversation
    p = tmp_path / margot_bot.CONVERSATIONS_DIR_REL / "789.jsonl"
    assert p.exists()
    history = margot_bot.load_history("789", repo_root=tmp_path)
    assert len(history) == 1
    assert history[0].user_text == "What's CCW NPS?"


def test_handle_turn_llm_failure(tmp_path, monkeypatch):
    async def fake(*, prompt, timeout_s=120, workspace=None, turn_id="", **kw):
        return 1, "", 0.0, "sdk_call_raised: boom"
    monkeypatch.setattr(margot_bot, "_call_llm", fake)

    turn = asyncio.run(margot_bot.handle_turn(
        chat_id="789", user_text="hi",
        repo_root=tmp_path, _send=False,
    ))
    assert turn.error and "boom" in turn.error
    assert "unavailable" in turn.margot_text.lower()
    # Still persisted (so we can audit failures)
    history = margot_bot.load_history("789", repo_root=tmp_path)
    assert len(history) == 1


def test_handle_turn_with_board_trigger_above_threshold(tmp_path, monkeypatch):
    response = '''Yes, that's significant.

[BOARD-TRIGGER score=8 topic="Material event"]
Insight body.
[/BOARD-TRIGGER]

Recommend reviewing.'''
    _stub_llm(monkeypatch, response_text=response)

    fake_sids: list[str] = []

    def fake_from_margot(*, topic, insight, citations, repo_root=None):
        sid = f"brd-{len(fake_sids):03d}"
        fake_sids.append(sid)
        return sid

    from swarm.bots import board as board_bot
    monkeypatch.setattr(board_bot, "from_margot", fake_from_margot)

    turn = asyncio.run(margot_bot.handle_turn(
        chat_id="789", user_text="any updates?",
        repo_root=tmp_path, _send=False,
    ))
    assert turn.board_session_ids == ["brd-000"]
    # Sentinel stripped from user-facing text
    assert "[BOARD-TRIGGER" not in turn.margot_text
    assert "Yes, that's significant." in turn.margot_text


def test_handle_turn_with_board_trigger_below_threshold(tmp_path, monkeypatch):
    """Score below threshold → not queued; sentinel still stripped."""
    response = '''Minor finding.

[BOARD-TRIGGER score=4 topic="Minor"]
Not worth escalating.
[/BOARD-TRIGGER]'''
    _stub_llm(monkeypatch, response_text=response)
    monkeypatch.setenv("MARGOT_BOARD_TRIGGER_THRESHOLD", "7")

    called = [False]

    def fake_from_margot(**kw):
        called[0] = True
        return "brd-x"

    from swarm.bots import board as board_bot
    monkeypatch.setattr(board_bot, "from_margot", fake_from_margot)

    turn = asyncio.run(margot_bot.handle_turn(
        chat_id="789", user_text="hi", repo_root=tmp_path, _send=False,
    ))
    assert called[0] is False
    assert turn.board_session_ids == []
    assert "[BOARD-TRIGGER" not in turn.margot_text


# ── Bot wrapper ─────────────────────────────────────────────────────────────


def test_wrapper_routes_intent_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(margot_bot_wrapper, "REPO_ROOT", tmp_path)
    _stub_llm(monkeypatch, response_text="hi back")

    payload = {
        "intent": "margot",
        "fields": {"prompt": "hello", "addressed_by": "prefix"},
        "originating_chat_id": "789",
        "originating_message_id": "msg-1",
    }
    out = margot_bot_wrapper.handle_telegram_intent(payload, _send=False)
    assert out["status"] == "ok"
    assert "turn_id" in out


def test_wrapper_missing_chat_id_returns_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(margot_bot_wrapper, "REPO_ROOT", tmp_path)
    out = margot_bot_wrapper.handle_telegram_intent(
        {"intent": "margot", "fields": {"prompt": "hi"}},
        _send=False,
    )
    assert out["status"] == "failed"


def test_wrapper_missing_prompt_returns_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(margot_bot_wrapper, "REPO_ROOT", tmp_path)
    out = margot_bot_wrapper.handle_telegram_intent(
        {"intent": "margot", "fields": {},
         "originating_chat_id": "789"},
        _send=False,
    )
    assert out["status"] == "failed"
