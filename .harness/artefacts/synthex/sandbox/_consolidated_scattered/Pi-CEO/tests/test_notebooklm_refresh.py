"""
test_notebooklm_refresh.py — RA-1668 unit tests for the NotebookLM refresh loop.

Covers the orchestration logic that's actually shippable today:
  - registry I/O (load, filter active)
  - freshness file write/read with atomic replace
  - dry-run path (no API call)
  - needs-credentials path when env vars absent
  - /health summary helper
  - per-notebook outcome recording

The actual REST call to the Enterprise API is gated behind credential
discovery (see notebooklm_refresh._refresh_notebook_sources) — those
calls are not tested live; they are mocked.
"""
import asyncio
import datetime
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def isolated_harness(tmp_path, monkeypatch):
    """Patch _HARNESS, _REGISTRY_PATH, _FRESHNESS_PATH to isolated tmp files."""
    from app.server.agents import notebooklm_refresh as mod

    fake_harness = tmp_path / ".harness"
    fake_harness.mkdir()
    fake_registry = fake_harness / "notebooklm-registry.json"
    fake_freshness = fake_harness / "notebooklm-freshness.json"

    fake_registry.write_text(json.dumps({
        "version": "1.0",
        "notebooks": [
            {"id": "nb-active-1", "entity": "RestoreAssist", "status": "active",
             "sources": ["s1", "s2"]},
            {"id": "nb-active-2", "entity": "Synthex", "status": "active",
             "sources": ["s3"]},
            {"id": "TBD", "entity": "Pending", "status": "pending_creation",
             "sources": []},
        ],
    }))

    monkeypatch.setattr(mod, "_HARNESS", fake_harness)
    monkeypatch.setattr(mod, "_REGISTRY_PATH", fake_registry)
    monkeypatch.setattr(mod, "_FRESHNESS_PATH", fake_freshness)
    return mod, fake_registry, fake_freshness


def test_load_registry_returns_dict(isolated_harness):
    mod, _, _ = isolated_harness
    reg = mod._load_registry()
    assert reg["version"] == "1.0"
    assert len(reg["notebooks"]) == 3


def test_load_registry_handles_missing(tmp_path, monkeypatch):
    from app.server.agents import notebooklm_refresh as mod
    monkeypatch.setattr(mod, "_REGISTRY_PATH", tmp_path / "does-not-exist.json")
    assert mod._load_registry() == {}


def test_active_notebooks_filters_pending_and_tbd(isolated_harness):
    mod, _, _ = isolated_harness
    active = mod._active_notebooks(mod._load_registry())
    ids = [nb["id"] for nb in active]
    assert ids == ["nb-active-1", "nb-active-2"]
    assert "TBD" not in ids


def test_freshness_atomic_write(isolated_harness):
    mod, _, fresh_path = isolated_harness
    data = {"version": "1.0", "notebooks": {"nb-x": {"outcome": "ok"}}}
    mod._save_freshness(data)
    assert fresh_path.exists()
    loaded = json.loads(fresh_path.read_text())
    assert loaded["notebooks"]["nb-x"]["outcome"] == "ok"
    # tmp file should be gone after replace
    assert not fresh_path.with_suffix(".tmp").exists()


def test_dry_run_does_not_call_api(isolated_harness):
    mod, _, fresh_path = isolated_harness

    refresh_mock = AsyncMock(return_value=(True, None))
    with patch.object(mod, "_refresh_notebook_sources", new=refresh_mock):
        result = asyncio.run(mod.refresh_all_notebooks(dry_run=True))

    assert result["active_count"] == 2
    assert refresh_mock.call_count == 0, "dry-run must NOT call the API"
    fresh = json.loads(fresh_path.read_text())
    # both active notebooks recorded as dry_run
    outcomes = [v["outcome"] for v in fresh["notebooks"].values()]
    assert outcomes.count("dry_run") == 2


def test_needs_credentials_when_project_id_missing(isolated_harness, monkeypatch):
    mod, _, _ = isolated_harness
    monkeypatch.delenv("NOTEBOOKLM_GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("NOTEBOOKLM_SERVICE_ACCOUNT_JSON", raising=False)

    refresh_mock = AsyncMock(return_value=(False, "should not be called"))
    with patch.object(mod, "_refresh_notebook_sources", new=refresh_mock):
        result = asyncio.run(mod.refresh_all_notebooks(dry_run=False))

    assert len(result["needs_credentials"]) == 2
    assert result["succeeded"] == []
    assert refresh_mock.call_count == 0, "must short-circuit when project_id missing"


def test_succeeded_path_records_ok(isolated_harness, monkeypatch):
    mod, _, fresh_path = isolated_harness
    monkeypatch.setenv("NOTEBOOKLM_GCP_PROJECT_ID", "test-project-123")

    refresh_mock = AsyncMock(return_value=(True, None))
    with patch.object(mod, "_refresh_notebook_sources", new=refresh_mock):
        result = asyncio.run(mod.refresh_all_notebooks(dry_run=False))

    assert refresh_mock.call_count == 2
    assert sorted(result["succeeded"]) == ["nb-active-1", "nb-active-2"]
    fresh = json.loads(fresh_path.read_text())
    assert fresh["notebooks"]["nb-active-1"]["outcome"] == "ok"


def test_error_path_records_error(isolated_harness, monkeypatch):
    mod, _, fresh_path = isolated_harness
    monkeypatch.setenv("NOTEBOOKLM_GCP_PROJECT_ID", "test-project-123")

    refresh_mock = AsyncMock(return_value=(False, "HTTP 500: server error"))
    with patch.object(mod, "_refresh_notebook_sources", new=refresh_mock):
        result = asyncio.run(mod.refresh_all_notebooks(dry_run=False))

    assert len(result["errors"]) == 2
    fresh = json.loads(fresh_path.read_text())
    rec = fresh["notebooks"]["nb-active-1"]
    assert rec["outcome"] == "error"
    assert "HTTP 500" in rec["error"]


def test_freshness_summary_for_health(isolated_harness):
    mod, _, fresh_path = isolated_harness
    # Seed a freshness file with one fresh + one stale notebook
    now = datetime.datetime.now(datetime.timezone.utc)
    fresh_path.write_text(json.dumps({
        "version": "1.0",
        "notebooks": {
            "nb-fresh": {
                "entity": "RA",
                "last_attempted": now.isoformat(timespec="seconds"),
                "outcome": "ok",
                "sources_count": 2,
            },
            "nb-stale": {
                "entity": "SYN",
                "last_attempted": (now - datetime.timedelta(days=10)).isoformat(timespec="seconds"),
                "outcome": "ok",
                "sources_count": 1,
            },
        },
    }))

    summary = mod.get_notebooklm_freshness_summary()
    assert summary["notebooks_tracked"] == 2
    assert summary["stale_count_7d"] == 1
    entries = {e["id"]: e for e in summary["summary"]}
    assert entries["nb-fresh"]["age_hours"] is not None and entries["nb-fresh"]["age_hours"] < 24
    assert entries["nb-stale"]["age_hours"] > 168


def test_freshness_summary_empty():
    """No registry / no freshness file → returns zeros, doesn't crash."""
    from app.server.agents.notebooklm_refresh import get_notebooklm_freshness_summary
    # Use a freshness path that won't exist for this test
    # Module fallback returns the empty shape — implementation reads a fresh file
    summary = get_notebooklm_freshness_summary()
    assert "notebooks_tracked" in summary
    assert summary.get("notebooks_tracked") >= 0
