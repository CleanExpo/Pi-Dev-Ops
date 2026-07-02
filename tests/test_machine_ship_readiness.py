"""Tests for machine-ship readiness probe (RA-6885)."""
from __future__ import annotations

from app.server.machine_ship_readiness import machine_ship_readiness


def test_not_ready_when_mode_off(monkeypatch):
    monkeypatch.delenv("TAO_MACHINE_SHIP_MODE", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("GITHUB_REPO", "CleanExpo/Pi-Dev-Ops")
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    report = machine_ship_readiness()
    assert report["ready"] is False
    assert "TAO_MACHINE_SHIP_MODE not 1" in report["blockers"]


def test_ready_when_all_set(monkeypatch):
    monkeypatch.setenv("TAO_MACHINE_SHIP_MODE", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GITHUB_REPO", "CleanExpo/Pi-Dev-Ops")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    report = machine_ship_readiness()
    assert report["ready"] is True
    assert report["blockers"] == []


def test_blockers_list_missing_github(monkeypatch):
    monkeypatch.setenv("TAO_MACHINE_SHIP_MODE", "1")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPO", "CleanExpo/Pi-Dev-Ops")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    report = machine_ship_readiness()
    assert report["ready"] is False
    assert "GITHUB_TOKEN unset" in report["blockers"]
