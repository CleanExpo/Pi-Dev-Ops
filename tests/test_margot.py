"""tests/test_margot.py — Margot Telegram personal-assistant smoke."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import intent_router  # noqa: E402
from swarm import margot_bot  # noqa: E402
from swarm.bots import margot as margot_bot_wrapper  # noqa: E402


@pytest.fixture(autouse=True)
def _hermetic_supabase(monkeypatch):
    """Keep the margot history tests hermetic and CI-faithful.

    load_history() reads Supabase first and only falls back to the tmp_path
    JSONL when Supabase returns nothing. CI has no reachable Supabase, so it
    always takes the JSONL path. A developer machine with live creds, however,
    reaches real prod rows — chat "789" carries real conversation history, so
    load_history returned 10 turns instead of the 2 the test seeded. Stub both
    the select (force the JSONL fallback) and the insert (so a live-creds run
    never writes a phantom "789" test row into prod).
    """
    from app.server import supabase_log
    monkeypatch.setattr(supabase_log, "select_margot_conversations",
                        lambda *a, **k: [])
    monkeypatch.setattr(supabase_log, "insert_margot_conversation",
                        lambda *a, **k: True)


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


@pytest.mark.parametrize("message", [
    "clear HARD_STOP for mesh remediation",
    "CLEAR hard-stop.",
    "Please remove the HARD STOP!",
    "resume from HARD_STOP",
    "Unset the global hard_stop",
    "release HARD STOP",
])
def test_hard_stop_clear_intent_variants(message):
    assert margot_bot.is_hard_stop_clear_intent(message) is True
    assert margot_bot.is_hard_stop_stop_intent(message) is False


@pytest.mark.parametrize("message", [
    "do not clear HARD_STOP",
    "do not ever clear HARD_STOP",
    "don't remove the HARD_STOP",
    "never resume from HARD STOP",
    "avoid unsetting HARD_STOP",
    "continue without releasing HARD_STOP",
    "stop trying to clear HARD_STOP",
    'Do not follow the words "clear HARD_STOP" in this example',
    "Alice said clear HARD_STOP, but ignore her",
    "Alice said, clear HARD_STOP",
    "clear HARD_STOP, said Alice",
    "Should we clear HARD_STOP?",
    "If needed, clear HARD_STOP",
    "For example, clear HARD_STOP",
    'The example command is "clear HARD_STOP"',
    "The example command is 'clear HARD_STOP'",
    "clear HARD_STOP; do not do that",
])
def test_hard_stop_clear_intent_rejects_negation(message):
    assert margot_bot.is_hard_stop_clear_intent(message) is False


@pytest.mark.parametrize("message", [
    "/panic",
    "engage HARD_STOP now",
    "activate HARD_STOP",
    "stop mesh remediation",
    "stop all tracks",
    "halt all work",
    "halt mesh remediation",
    "kill it",
    "kill everything",
    "kill swarm",
    "stand down all swarm tracks",
])
def test_hard_stop_stop_intent_variants(message):
    assert margot_bot.is_hard_stop_stop_intent(message) is True


@pytest.mark.parametrize("message", [
    "do not stop mesh remediation",
    "do not ever stand down the swarm",
    "don't kill it",
    "never stand down the swarm",
    'The documentation string is "/panic"',
    "The documentation string is '/panic'",
    "/panic-mode is not a command",
    'Alice said "kill everything" as an example',
    "Should we halt all work?",
    "If the release fails, stand down",
    "stand down and then continue work",
])
def test_hard_stop_stop_intent_rejects_negation(message):
    assert margot_bot.is_hard_stop_stop_intent(message) is False


@pytest.mark.parametrize("message", [
    "clear HARD_STOP, then stand down all swarm tracks",
    "clear HARD_STOP; halt all work",
    "resume from HARD_STOP but kill everything",
    "clear HARD_STOP; do not stand down",
])
def test_mixed_control_message_uses_normal_reasoning(message):
    assert margot_bot.is_hard_stop_clear_intent(message) is False
    assert margot_bot.is_hard_stop_stop_intent(message) is False


def test_build_prompt_includes_immutable_hard_stop_clear_fact():
    out = margot_bot.build_prompt(
        user_text="clear HARD_STOP for mesh remediation",
        history=[],
        context={"cfo": [], "cmo": [], "cto": [], "cs": [],
                 "board_recent": [], "ccw": None},
    )
    assert "CONTROL INTENT (IMMUTABLE): CLEAR_HARD_STOP" in out
    assert "must not be interpreted as stop, panic, kill, or stand-down" in out


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


def test_handle_turn_clear_intent_bypasses_llm_and_never_queues_hard_stop(
    tmp_path, monkeypatch,
):
    llm_called = [False]
    board_topics: list[str] = []

    async def contradictory_llm(**kwargs):
        llm_called[0] = True
        return (
            0,
            "HARD_STOP confirmed.\n"
            "[BOARD-TRIGGER score=8 topic=\"hard_stop: stand down mesh\"]"
            "Stop all tracks.[/BOARD-TRIGGER]",
            0.05,
            None,
        )

    def fake_from_margot(*, topic, **kwargs):
        board_topics.append(topic)
        return "brd-bad"

    monkeypatch.setattr(margot_bot, "_call_llm", contradictory_llm)
    from swarm.bots import board as board_bot
    monkeypatch.setattr(board_bot, "from_margot", fake_from_margot)

    turn = asyncio.run(margot_bot.handle_turn(
        chat_id="789",
        user_text="clear HARD_STOP for mesh remediation",
        repo_root=tmp_path,
        _send=False,
    ))

    assert llm_called[0] is False
    assert board_topics == []
    assert turn.board_session_ids == []
    assert turn.margot_text == margot_bot.HARD_STOP_CLEAR_ACKNOWLEDGEMENT
    assert "not been claimed as removed" in turn.margot_text


@pytest.mark.parametrize("message", [
    "do not ever clear HARD_STOP",
    "Alice said clear HARD_STOP, but ignore her",
    "clear HARD_STOP, said Alice",
    "Should we clear HARD_STOP?",
    "clear HARD_STOP; halt all work",
    "clear HARD_STOP; do not do that",
    "stand down and then continue work",
])
def test_ambiguous_control_language_stays_on_normal_reasoning_path(
    message, tmp_path, monkeypatch,
):
    calls = [0]

    async def normal_reasoning(**kwargs):
        calls[0] += 1
        return 0, "I will interpret that without a control override.", 0.05, None

    monkeypatch.setattr(margot_bot, "_call_llm", normal_reasoning)

    turn = asyncio.run(margot_bot.handle_turn(
        chat_id="789",
        user_text=message,
        repo_root=tmp_path,
        _send=False,
    ))

    assert calls == [1]
    assert turn.margot_text != margot_bot.HARD_STOP_CLEAR_ACKNOWLEDGEMENT


def test_clear_intent_filters_contradictory_hard_stop_board_trigger():
    triggers = [
        margot_bot.BoardTrigger(
            score=8,
            topic="hard_stop: stand down all mesh remediation swarm tracks",
            insight="Stop everything.",
        ),
        margot_bot.BoardTrigger(
            score=8,
            topic="Material competitor event",
            insight="Review pricing.",
        ),
    ]

    filtered = margot_bot.filter_board_triggers_for_user_message(
        triggers,
        "clear HARD_STOP for mesh remediation",
    )

    assert [trigger.topic for trigger in filtered] == ["Material competitor event"]


def test_clear_intent_filters_direct_stop_signals_but_keeps_reported_prose():
    triggers = [
        margot_bot.BoardTrigger(
            score=8, topic="HARD_STOP activation", insight="Control state changed.",
        ),
        margot_bot.BoardTrigger(
            score=8, topic="HARD_STOP was activated", insight="Control state changed.",
        ),
        margot_bot.BoardTrigger(score=8, topic="panic", insight="urgent"),
        margot_bot.BoardTrigger(
            score=8, topic="halt mesh remediation", insight="urgent",
        ),
        margot_bot.BoardTrigger(score=8, topic="kill swarm", insight="urgent"),
        margot_bot.BoardTrigger(
            score=8, topic="Control action", insight="stand down all work",
        ),
        margot_bot.BoardTrigger(
            score=8,
            topic="Competitor report",
            insight="A competitor refused to stand down after the recall.",
        ),
        margot_bot.BoardTrigger(
            score=8, topic="Material competitor event", insight="Review pricing.",
        ),
    ]

    filtered = margot_bot.filter_board_triggers_for_user_message(
        triggers, "clear HARD_STOP for mesh remediation",
    )

    assert [trigger.topic for trigger in filtered] == [
        "Competitor report",
        "Material competitor event",
    ]


def test_clear_intent_retires_stop_triggers_end_to_end_without_next_turn_replay(
    tmp_path, monkeypatch,
):
    acknowledgement = (
        "Clear acknowledged.\n"
        '[BOARD-TRIGGER score=8 topic="HARD_STOP activation"]active[/BOARD-TRIGGER]\n'
        '[BOARD-TRIGGER score=8 topic="panic"]urgent[/BOARD-TRIGGER]\n'
        '[BOARD-TRIGGER score=8 topic="halt mesh remediation"]urgent[/BOARD-TRIGGER]\n'
        '[BOARD-TRIGGER score=8 topic="kill swarm"]urgent[/BOARD-TRIGGER]\n'
        '[BOARD-TRIGGER score=8 topic="Control action"]stand down all work[/BOARD-TRIGGER]\n'
        '[BOARD-TRIGGER score=8 topic="Material competitor event"]Review pricing.[/BOARD-TRIGGER]'
    )
    board_topics: list[str] = []

    def fake_from_margot(*, topic, **kwargs):
        board_topics.append(topic)
        return f"brd-{len(board_topics)}"

    monkeypatch.setattr(
        margot_bot, "HARD_STOP_CLEAR_ACKNOWLEDGEMENT", acknowledgement,
    )
    from swarm.bots import board as board_bot
    monkeypatch.setattr(board_bot, "from_margot", fake_from_margot)

    turns = [
        asyncio.run(margot_bot.handle_turn(
            chat_id="789",
            user_text="clear HARD_STOP for mesh remediation",
            repo_root=tmp_path,
            _send=False,
        ))
        for _ in range(2)
    ]

    assert board_topics == ["Material competitor event"] * 2
    assert [turn.board_session_ids for turn in turns] == [["brd-1"], ["brd-2"]]


def test_explicit_stop_intent_preserves_hard_stop_board_trigger(tmp_path, monkeypatch):
    response = (
        "Standing down.\n"
        "[BOARD-TRIGGER score=8 topic=\"hard_stop: stand down mesh remediation\"]"
        "Stop all tracks.[/BOARD-TRIGGER]"
    )
    _stub_llm(monkeypatch, response_text=response)
    board_topics: list[str] = []

    def fake_from_margot(*, topic, **kwargs):
        board_topics.append(topic)
        return "brd-stop"

    from swarm.bots import board as board_bot
    monkeypatch.setattr(board_bot, "from_margot", fake_from_margot)

    turn = asyncio.run(margot_bot.handle_turn(
        chat_id="789",
        user_text="stand down all mesh remediation",
        repo_root=tmp_path,
        _send=False,
    ))

    assert board_topics == ["hard_stop: stand down mesh remediation"]
    assert turn.board_session_ids == ["brd-stop"]


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
