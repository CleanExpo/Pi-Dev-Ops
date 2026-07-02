"""Tests for scripts/run_plan_discovery_backlog.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import run_plan_discovery_backlog as pdb  # noqa: E402


def test_run_plan_discovery_backlog_writes_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(pdb, "OUT_DIR", tmp_path)
    monkeypatch.setattr(
        pdb,
        "fetch_todo_issues",
        lambda _key: [
            {
                "identifier": "RA-1",
                "title": "Test ticket",
                "priority": 2,
                "description": "Do the thing",
                "_project_name": "Pi - Dev -Ops",
                "_repo_url": "https://github.com/CleanExpo/Pi-Dev-Ops",
                "url": "https://linear.app/example/RA-1",
            }
        ],
    )
    monkeypatch.setattr(pdb.config, "LINEAR_API_KEY", "lin_test")

    result = pdb.run(emit_json=False)
    assert result["ok"] is True
    assert result["queue_depth"] == 1
    path = Path(result["path"])
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["issues"][0]["identifier"] == "RA-1"


def test_run_plan_discovery_backlog_no_api_key(monkeypatch):
    monkeypatch.setattr(pdb.config, "LINEAR_API_KEY", None)
    result = pdb.run(emit_json=False)
    assert result["ok"] is False
