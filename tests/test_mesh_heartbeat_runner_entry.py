"""tests/test_mesh_heartbeat_runner_entry.py — the heartbeat says which code each node runs (08/11/2026).

On the live fleet every machine showed "nexus-mesh/0.1": node_version only read the
breadcrumb when it was under 120 s old, and the runner writes it once at the start
of a build, so a long build or a dead runner erased the one fact the fleet needed.
These tests drive `collect()`, the payload the heartbeat actually publishes.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from mesh_helpers import load_module as _load  # noqa: E402

SHA = "c" * 40
KEYS = {"runtime", "present", "version", "approved_version", "version_status", "state", "state_age_s",
        "current_task", "hold_reason", "local_edits", "last_update", "last_job", "skills_version",
        "heartbeat_version"}


@pytest.fixture
def hb(monkeypatch, tmp_path):
    mod = _load("mesh_heartbeat_runner_entry", "mesh/heartbeat.py")
    monkeypatch.setattr(mod, "MESH_RUNNER_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(mod, "tailnet_ip", lambda: "")
    monkeypatch.setattr(mod, "cpu_mem_load", lambda: (None, None, None))
    monkeypatch.setattr(mod, "running_agent_sessions", lambda: [])
    monkeypatch.setenv("HOME", str(tmp_path / "home"))   # ~/.claude is not a git checkout here
    return mod


def _crumb(hb, **fields) -> None:
    Path(hb.MESH_RUNNER_STATE).write_text(json.dumps(fields))


def _entry(payload: dict) -> dict:
    found = [r for r in payload["agent_runtimes"] if r.get("runtime") == "mesh-runner"]
    assert len(found) == 1, payload["agent_runtimes"]
    return found[0]


def test_heartbeat_reports_version_for_a_stale_breadcrumb(hb):
    _crumb(hb, version=SHA, state="working", current_task="RA-7487", ts=int(time.time()) - 3600)
    payload = hb.collect()
    assert payload["version"].startswith("nexus-mesh/" + SHA[:12])   # was nexus-mesh/0.1
    assert "old" in payload["version"]                                 # labelled with its age
    entry = _entry(payload)
    assert entry["version"] == SHA and entry["state"] == "working"
    assert 3590 <= entry["state_age_s"] <= 3700


def test_a_fresh_breadcrumb_version_carries_no_age_label(hb):
    _crumb(hb, version=SHA, state="idle", ts=int(time.time()))
    assert hb.collect()["version"] == "nexus-mesh/" + SHA[:12]


def test_mesh_runner_entry_has_nulls_not_guesses(hb):
    _crumb(hb, version="unknown", state="idle")                        # no ts, no version facts
    entry = _entry(hb.collect())
    assert set(entry) == KEYS
    assert entry["present"] is True
    for key in KEYS - {"runtime", "present", "state", "heartbeat_version"}:
        assert entry[key] is None, key
    assert entry["state"] == "idle"


def test_mesh_runner_entry_without_a_breadcrumb_is_absent_and_null(hb):
    entry = _entry(hb.collect())
    assert entry["present"] is False
    assert all(entry[k] is None for k in KEYS - {"runtime", "present", "heartbeat_version"})


def test_mesh_runner_entry_carries_the_runner_facts(hb):
    _crumb(hb, version=SHA, approved_version="d" * 40, version_status="outdated", state="outdated",
           hold_reason="outdated: runtime has local edits; checkpoint them", local_edits=2,
           last_update={"outcome": "update refused", "ts": 5}, last_job={"linear_id": "RA-1", "state": "done", "ts": 6},
           ts=int(time.time()))
    entry = _entry(hb.collect())
    assert entry["approved_version"] == "d" * 40 and entry["local_edits"] == 2
    assert entry["last_job"] == {"linear_id": "RA-1", "state": "done", "ts": 6}


def test_heartbeat_version_is_this_checkouts_commit(hb):
    entry = _entry(hb.collect())
    import subprocess
    head = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert entry["heartbeat_version"] == head


@pytest.mark.parametrize("state", ["outdated", "version-unknown", "hard_stop", "updating"])
def test_node_status_reports_the_new_holds(hb, state):
    assert hb.node_status([], {"state": state}) == state
    assert hb.node_status([], {"state": state}, down=True) == "runner-down"
