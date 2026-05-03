"""tests/test_margot_supabase_memory.py — RA-1905 Supabase persistent memory.

Verifies that Margot conversation history survives a Railway redeploy by
treating Supabase as the durable source of truth and JSONL as a hot cache.

Covers:
  * append_turn writes JSONL AND attempts Supabase insert
  * append_turn never raises when Supabase is unconfigured
  * load_history reads Supabase first, falls back to JSONL
  * cross-deploy simulation: 3 turns persist after JSONL is wiped
  * tenant_id defaults to 'pi-ceo' in the insert payload (RA-1838)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import margot_bot  # noqa: E402


# ── append_turn ─────────────────────────────────────────────────────────────


def test_append_turn_writes_jsonl_and_attempts_supabase(tmp_path):
    """Both JSONL and Supabase are touched. Capture the Supabase payload."""
    from app.server import supabase_log

    captured: dict = {}

    def fake_insert(row):
        captured["row"] = row
        return True

    turn = margot_bot.MargotTurn(
        chat_id="42", user_text="hi", margot_text="hello",
        started_at="2026-05-03T10:00:00+00:00",
        ended_at="2026-05-03T10:00:01+00:00",
    )
    with patch.object(
        supabase_log, "insert_margot_conversation", side_effect=fake_insert,
    ):
        margot_bot.append_turn(turn, repo_root=tmp_path)

    # JSONL written
    jsonl_path = tmp_path / margot_bot.CONVERSATIONS_DIR_REL / "42.jsonl"
    assert jsonl_path.exists()
    assert "hi" in jsonl_path.read_text(encoding="utf-8")

    # Supabase insert called with expected fields
    assert "row" in captured
    row = captured["row"]
    assert row["chat_id"] == "42"
    assert row["user_text"] == "hi"
    assert row["margot_text"] == "hello"
    assert row["tenant_id"] == "pi-ceo"  # RA-1838 forward-compat
    assert row["turn_id"] == turn.turn_id


def test_append_turn_no_supabase_no_exception(tmp_path):
    """When Supabase is unconfigured (test env default), no exception is
    raised and only the JSONL is written.

    The real _insert helper short-circuits when SUPABASE_URL/KEY are empty.
    """
    turn = margot_bot.MargotTurn(
        chat_id="X", user_text="q", margot_text="a",
        started_at="t", ended_at="t",
    )
    # No mock — real helper, real config (empty in test env)
    margot_bot.append_turn(turn, repo_root=tmp_path)
    jsonl_path = tmp_path / margot_bot.CONVERSATIONS_DIR_REL / "X.jsonl"
    assert jsonl_path.exists()


def test_append_turn_supabase_failure_is_fire_and_forget(tmp_path):
    """If Supabase raises, append_turn must still write JSONL and return."""
    from app.server import supabase_log

    def boom(_row):
        raise RuntimeError("supabase down")

    turn = margot_bot.MargotTurn(
        chat_id="Y", user_text="q", margot_text="a",
        started_at="t", ended_at="t",
    )
    with patch.object(
        supabase_log, "insert_margot_conversation", side_effect=boom,
    ):
        margot_bot.append_turn(turn, repo_root=tmp_path)  # must not raise

    jsonl_path = tmp_path / margot_bot.CONVERSATIONS_DIR_REL / "Y.jsonl"
    assert jsonl_path.exists()


# ── tenant_id default ───────────────────────────────────────────────────────


def test_tenant_id_defaults_to_pi_ceo(tmp_path):
    """RA-1838 forward-compat — every insert must default tenant_id='pi-ceo'."""
    from app.server import supabase_log

    captured: dict = {}

    def fake_insert(row):
        captured["row"] = row
        return True

    turn = margot_bot.MargotTurn(
        chat_id="Z", user_text="hello", margot_text="hi",
        started_at="t", ended_at="t",
    )
    with patch.object(
        supabase_log, "insert_margot_conversation", side_effect=fake_insert,
    ):
        margot_bot.append_turn(turn, repo_root=tmp_path)

    assert captured["row"]["tenant_id"] == "pi-ceo"


# ── load_history ────────────────────────────────────────────────────────────


def test_load_history_reads_supabase_when_jsonl_empty(tmp_path):
    """Supabase rows convert to MargotTurn objects in chronological order."""
    from app.server import supabase_log

    # Supabase returns desc by started_at (newest first)
    fake_rows = [
        {
            "turn_id": "mt-2", "chat_id": "C",
            "user_text": "second q", "margot_text": "second a",
            "started_at": "2026-05-03T10:01:00+00:00",
            "ended_at": "2026-05-03T10:01:01+00:00",
            "research_called": False, "cost_usd": 0.0,
            "board_session_ids": [],
        },
        {
            "turn_id": "mt-1", "chat_id": "C",
            "user_text": "first q", "margot_text": "first a",
            "started_at": "2026-05-03T10:00:00+00:00",
            "ended_at": "2026-05-03T10:00:01+00:00",
            "research_called": False, "cost_usd": 0.0,
            "board_session_ids": [],
        },
    ]
    with patch.object(
        supabase_log, "select_margot_conversations", return_value=fake_rows,
    ):
        history = margot_bot.load_history("C", repo_root=tmp_path)

    assert len(history) == 2
    # Reversed to chronological (oldest first)
    assert history[0].user_text == "first q"
    assert history[1].user_text == "second q"
    assert isinstance(history[0], margot_bot.MargotTurn)


def test_load_history_jsonl_fallback_when_supabase_empty(tmp_path):
    """When Supabase returns no rows, JSONL fallback preserves old behavior."""
    from app.server import supabase_log

    # Write directly to JSONL bypassing Supabase
    turn = margot_bot.MargotTurn(
        chat_id="J", user_text="local q", margot_text="local a",
        started_at="t", ended_at="t",
    )
    # Mock Supabase as empty so JSONL fallback triggers
    with patch.object(
        supabase_log, "insert_margot_conversation", return_value=False,
    ):
        margot_bot.append_turn(turn, repo_root=tmp_path)

    with patch.object(
        supabase_log, "select_margot_conversations", return_value=[],
    ):
        history = margot_bot.load_history("J", repo_root=tmp_path)

    assert len(history) == 1
    assert history[0].user_text == "local q"


def test_cross_deploy_simulation(tmp_path):
    """Write 3 turns, blow away the JSONL file, history still rehydrates from
    Supabase. This is the RA-1905 acceptance criterion.
    """
    from app.server import supabase_log

    stored: list[dict] = []

    def fake_insert(row):
        stored.append(row)
        return True

    def fake_select(*, chat_id, limit=10, tenant_id="pi-ceo"):
        # Mimic real Supabase: filter by chat_id, order by started_at desc
        rows = [r for r in stored if r["chat_id"] == chat_id]
        rows = sorted(rows, key=lambda r: r["started_at"] or "", reverse=True)
        return rows[:limit]

    with patch.object(
        supabase_log, "insert_margot_conversation", side_effect=fake_insert,
    ):
        for i in range(3):
            margot_bot.append_turn(
                margot_bot.MargotTurn(
                    turn_id=f"mt-{i}", chat_id="D",
                    user_text=f"q{i}", margot_text=f"a{i}",
                    started_at=f"2026-05-03T10:0{i}:00+00:00",
                    ended_at=f"2026-05-03T10:0{i}:01+00:00",
                ),
                repo_root=tmp_path,
            )

    # JSONL exists at this point
    jsonl_path = tmp_path / margot_bot.CONVERSATIONS_DIR_REL / "D.jsonl"
    assert jsonl_path.exists()

    # SIMULATE RAILWAY REDEPLOY: nuke the JSONL
    jsonl_path.unlink()
    assert not jsonl_path.exists()

    # load_history rehydrates from Supabase
    with patch.object(
        supabase_log, "select_margot_conversations", side_effect=fake_select,
    ):
        history = margot_bot.load_history("D", repo_root=tmp_path)

    assert len(history) == 3
    # Chronological order preserved
    assert [t.user_text for t in history] == ["q0", "q1", "q2"]
