"""Shared fixtures for the RA-8174 red-main watcher tests (not a test module)."""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from red_main.common import FAIL, TS  # noqa: E402

T0 = datetime.datetime.strptime("2026-11-04T17:00+1000", TS)
REPO = "CleanExpo/CARSI"


def run(wid, name, conclusion, created, status="completed", event="push", sha="abc12345ff"):
    return {"workflowDatabaseId": wid, "workflowName": name, "conclusion": conclusion, "status": status,
            "createdAt": created, "headSha": sha, "event": event, "url": f"https://x/{wid}/{created}"}


def make_ops(tmp_path, monkeypatch):
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "jobs.json").write_text(json.dumps({"jobs": []}))
    monkeypatch.setenv("RED_MAIN_OPS", str(tmp_path / "ops"))
    monkeypatch.setenv("RED_MAIN_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "ops" / "jobs.json"


def jobs(path):
    return {j["id"]: j for j in json.loads(path.read_text())["jobs"]}


RED = (FAIL, {"failing": [{"id": 1, "name": "CI", "since": "2026-11-04T07:00:00Z"}],
              "since": "2026-11-04T07:00:00Z", "branch": "main"})
