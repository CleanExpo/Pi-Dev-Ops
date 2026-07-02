"""Tests for scripts/verify_autonomous_mode.py (RA-6892)."""
from __future__ import annotations

import importlib.util
import json
import sys
from io import StringIO
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load_verify_module():
    spec = importlib.util.spec_from_file_location(
        "verify_autonomous_mode",
        REPO / "scripts" / "verify_autonomous_mode.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_verify_autonomous_mode_exit_ok(monkeypatch, capsys):
    monkeypatch.setenv("TAO_AUTONOMY_ENABLED", "1")
    monkeypatch.setenv("TAO_MACHINE_SHIP_MODE", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GITHUB_REPO", "CleanExpo/Pi-Dev-Ops")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test")

    import app.server.autonomy as autonomy

    monkeypatch.setattr(autonomy, "_gql", lambda _key, _q, _v=None: {"viewer": {"id": "u"}})
    monkeypatch.setattr(autonomy, "fetch_todo_issues", lambda _key: [{"id": "x"}])
    monkeypatch.setattr(
        autonomy,
        "_load_portfolio_projects",
        lambda: [{"project_id": "p", "team_id": "t", "repo_url": "r", "name": "n"}],
    )

    mod = _load_verify_module()
    code = mod.main()
    out = capsys.readouterr().out
    body = json.loads(out)
    assert code == 0
    assert body["ok"] is True
    assert body["queue_depth"] == 1


def test_verify_autonomous_mode_exit_fail_when_autonomy_off(monkeypatch, capsys):
    monkeypatch.setenv("TAO_AUTONOMY_ENABLED", "0")
    monkeypatch.setenv("TAO_MACHINE_SHIP_MODE", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GITHUB_REPO", "CleanExpo/Pi-Dev-Ops")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test")

    import app.server.autonomy as autonomy

    monkeypatch.setattr(autonomy, "_gql", lambda _key, _q, _v=None: {"viewer": {"id": "u"}})
    monkeypatch.setattr(autonomy, "fetch_todo_issues", lambda _key: [])
    monkeypatch.setattr(autonomy, "_load_portfolio_projects", lambda: [])

    # Reload so main() re-imports patched autonomy module.
    mod = _load_verify_module()
    code = mod.main()
    body = json.loads(capsys.readouterr().out)
    assert code == 1
    assert body["ok"] is False
    assert "TAO_AUTONOMY_ENABLED=0" in body["blockers"]
