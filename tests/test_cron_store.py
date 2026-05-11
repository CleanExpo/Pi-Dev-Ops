"""tests/test_cron_store.py — cron_store update_trigger() unit tests.

Pins the behaviour required by the Hermes audit follow-up
(`Wiki/hermes-agent-sprinkle-audit-2026-05-11.md` § plan-discovery investigation):
``cron_store.update_trigger("<id>", enabled=False)`` must idempotently flip
fields on a known trigger and raise on an unknown id.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def test_update_trigger_modifies_existing_fields(tmp_path, monkeypatch):
    from app.server import cron_store, supabase_log

    triggers_file = tmp_path / "cron-triggers.json"
    triggers_file.write_text(json.dumps([
        {"id": "plan-discovery-daily-0300", "hour": 3, "minute": 0,
         "enabled": True, "last_fired_at": None, "type": "plan_discovery"},
        {"id": "scan-high-0000", "hour": 0, "minute": 0,
         "enabled": True, "last_fired_at": 1700000000.0, "type": "scan"},
    ]))
    monkeypatch.setattr(cron_store, "_TRIGGERS_FILE", str(triggers_file))

    with patch.object(supabase_log, "load_cron_state", return_value={}), \
         patch.object(supabase_log, "save_cron_last_fired", return_value=True):
        updated = cron_store.update_trigger("plan-discovery-daily-0300", enabled=False)

    assert updated["enabled"] is False
    assert updated["id"] == "plan-discovery-daily-0300"
    # other fields preserved
    assert updated["hour"] == 3
    assert updated["type"] == "plan_discovery"

    # persisted on disk
    on_disk = json.loads(triggers_file.read_text())
    by_id = {t["id"]: t for t in on_disk}
    assert by_id["plan-discovery-daily-0300"]["enabled"] is False
    # untouched sibling stays untouched
    assert by_id["scan-high-0000"]["enabled"] is True


def test_update_trigger_raises_if_missing(tmp_path, monkeypatch):
    from app.server import cron_store, supabase_log

    triggers_file = tmp_path / "cron-triggers.json"
    triggers_file.write_text(json.dumps([
        {"id": "scan-high-0000", "hour": 0, "minute": 0, "enabled": True,
         "last_fired_at": None, "type": "scan"},
    ]))
    monkeypatch.setattr(cron_store, "_TRIGGERS_FILE", str(triggers_file))

    with patch.object(supabase_log, "load_cron_state", return_value={}):
        try:
            cron_store.update_trigger("does-not-exist", enabled=False)
        except KeyError as exc:
            assert "does-not-exist" in str(exc)
        else:
            raise AssertionError("update_trigger should raise KeyError on unknown id")
