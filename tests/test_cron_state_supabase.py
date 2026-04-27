"""
test_cron_state_supabase.py — RA-1439 unit tests.

Covers:
  - save_cron_last_fired upserts the right shape
  - save_cron_last_fired returns False on bad input / outage (never raises)
  - load_cron_state parses ISO timestamps to epoch floats
  - load_cron_state empty on Supabase error
  - cron_store._load_triggers overlays Supabase state onto JSON
  - cron_store._load_triggers falls back to JSON last_fired_at on outage
  - cron_store._save_triggers writes JSON AND fires Supabase upserts
"""
import json
import os
from unittest.mock import patch, MagicMock

import pytest


# ── save_cron_last_fired ────────────────────────────────────────────────────


def test_save_cron_last_fired_upserts_iso_timestamp():
    from app.server import supabase_log

    captured = {}

    def fake_upsert(table, row):
        captured["table"] = table
        captured["row"] = row
        return True

    with patch.object(supabase_log, "_upsert", side_effect=fake_upsert):
        ok = supabase_log.save_cron_last_fired("intel-refresh-daily-0200", 1776578110.0)

    assert ok is True
    assert captured["table"] == "cron_state"
    assert captured["row"]["trigger_id"] == "intel-refresh-daily-0200"
    # ISO timestamp string with offset
    assert "T" in captured["row"]["last_fired_at"]
    assert captured["row"]["last_fired_at"].startswith("2026-")


def test_save_cron_last_fired_rejects_bad_input():
    from app.server import supabase_log
    assert supabase_log.save_cron_last_fired("", 100.0) is False
    assert supabase_log.save_cron_last_fired("x", 0) is False
    assert supabase_log.save_cron_last_fired("x", None) is False


def test_save_cron_last_fired_returns_false_on_exception():
    from app.server import supabase_log

    with patch.object(supabase_log, "_upsert", side_effect=RuntimeError("supabase down")):
        ok = supabase_log.save_cron_last_fired("test-trigger", 1700000000.0)

    assert ok is False  # never raises


# ── load_cron_state ─────────────────────────────────────────────────────────


def test_load_cron_state_parses_rows():
    from app.server import supabase_log

    fake_rows = [
        {"trigger_id": "intel-refresh-daily-0200", "last_fired_at": "2026-04-19T07:09:29+00:00"},
        {"trigger_id": "scan-high-0000", "last_fired_at": "2026-04-25T00:00:00Z"},
    ]
    with patch.object(supabase_log, "_select", return_value=fake_rows):
        state = supabase_log.load_cron_state()

    assert "intel-refresh-daily-0200" in state
    assert "scan-high-0000" in state
    assert isinstance(state["intel-refresh-daily-0200"], float)
    assert state["intel-refresh-daily-0200"] > 1700000000  # > 2023


def test_load_cron_state_skips_malformed_rows():
    from app.server import supabase_log

    fake_rows = [
        {"trigger_id": "ok", "last_fired_at": "2026-04-25T00:00:00Z"},
        {"trigger_id": "no-ts"},
        {"trigger_id": "", "last_fired_at": "2026-04-25T00:00:00Z"},
        {"trigger_id": "bad-ts", "last_fired_at": "not-a-timestamp"},
    ]
    with patch.object(supabase_log, "_select", return_value=fake_rows):
        state = supabase_log.load_cron_state()

    assert "ok" in state
    assert "no-ts" not in state
    assert "bad-ts" not in state


def test_load_cron_state_empty_on_exception():
    from app.server import supabase_log

    with patch.object(supabase_log, "_select", side_effect=RuntimeError("supabase down")):
        state = supabase_log.load_cron_state()

    assert state == {}


# ── cron_store integration ─────────────────────────────────────────────────


def test_load_triggers_overlays_supabase_state(tmp_path, monkeypatch):
    from app.server import cron_store, supabase_log

    triggers_file = tmp_path / "cron-triggers.json"
    triggers_file.write_text(json.dumps([
        {"id": "intel-refresh-daily-0200", "hour": 2, "enabled": True, "last_fired_at": 1700000000.0},
        {"id": "scan-high-0000", "hour": 0, "enabled": True, "last_fired_at": 1700000000.0},
    ]))
    monkeypatch.setattr(cron_store, "_TRIGGERS_FILE", str(triggers_file))

    # Supabase has fresher timestamps for both
    fresh_state = {
        "intel-refresh-daily-0200": 1776700000.0,
        "scan-high-0000": 1776700100.0,
    }
    with patch.object(supabase_log, "load_cron_state", return_value=fresh_state):
        triggers = cron_store._load_triggers()

    by_id = {t["id"]: t for t in triggers}
    # Supabase should win
    assert by_id["intel-refresh-daily-0200"]["last_fired_at"] == 1776700000.0
    assert by_id["scan-high-0000"]["last_fired_at"] == 1776700100.0


def test_load_triggers_falls_back_to_json_on_supabase_outage(tmp_path, monkeypatch):
    from app.server import cron_store, supabase_log

    triggers_file = tmp_path / "cron-triggers.json"
    triggers_file.write_text(json.dumps([
        {"id": "x", "last_fired_at": 1700000000.0, "enabled": True},
    ]))
    monkeypatch.setattr(cron_store, "_TRIGGERS_FILE", str(triggers_file))

    with patch.object(supabase_log, "load_cron_state", side_effect=RuntimeError("down")):
        triggers = cron_store._load_triggers()

    # System keeps running, JSON value preserved
    assert len(triggers) == 1
    assert triggers[0]["last_fired_at"] == 1700000000.0


def test_load_triggers_returns_empty_when_no_file(tmp_path, monkeypatch):
    from app.server import cron_store
    monkeypatch.setattr(cron_store, "_TRIGGERS_FILE", str(tmp_path / "does-not-exist.json"))
    assert cron_store._load_triggers() == []


def test_save_triggers_writes_json_and_calls_supabase(tmp_path, monkeypatch):
    from app.server import cron_store, supabase_log

    triggers_file = tmp_path / "cron-triggers.json"
    monkeypatch.setattr(cron_store, "_TRIGGERS_FILE", str(triggers_file))

    triggers = [
        {"id": "t1", "last_fired_at": 1776700000.0, "hour": 2, "enabled": True},
        {"id": "t2", "last_fired_at": 1776700100.0, "hour": 6, "enabled": True},
        {"id": "t3", "last_fired_at": None, "hour": 12, "enabled": True},  # never fired
    ]

    with patch.object(supabase_log, "save_cron_last_fired", return_value=True) as mock_save:
        cron_store._save_triggers(triggers)

    # JSON written
    assert triggers_file.exists()
    loaded = json.loads(triggers_file.read_text())
    assert len(loaded) == 3

    # Supabase called for the two with last_fired_at, NOT for t3 (None)
    assert mock_save.call_count == 2
    call_ids = sorted([call.args[0] for call in mock_save.call_args_list])
    assert call_ids == ["t1", "t2"]


def test_save_triggers_supabase_failure_does_not_crash(tmp_path, monkeypatch):
    from app.server import cron_store, supabase_log

    triggers_file = tmp_path / "cron-triggers.json"
    monkeypatch.setattr(cron_store, "_TRIGGERS_FILE", str(triggers_file))

    with patch.object(supabase_log, "save_cron_last_fired", side_effect=RuntimeError("down")):
        # Must not raise
        cron_store._save_triggers([{"id": "x", "last_fired_at": 1700000000.0}])

    # JSON should still be written
    assert triggers_file.exists()
