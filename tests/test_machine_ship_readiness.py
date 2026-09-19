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


def test_paid_key_presence_does_not_make_machine_ship_ready(monkeypatch):
    monkeypatch.setenv("TAO_MACHINE_SHIP_MODE", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GITHUB_REPO", "CleanExpo/Pi-Dev-Ops")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("TAO_MODEL_SPEC_PIPELINE", "openrouter:paid-model")
    report = machine_ship_readiness()
    assert report["ready"] is False
    assert report["checks"]["llm_execution_verified"] is False


def test_supported_configuration_is_not_observed_runtime_readiness(monkeypatch):
    from unittest.mock import Mock
    from app.server import provider_policy

    monkeypatch.setenv("TAO_MACHINE_SHIP_MODE", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "test")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("TAO_MID_USE_CLAUDE_PRINT", "1")
    for role in ("spec_pipeline", "storm_evidence", "prebuild_judge", "spm_runner",
                 "spm_gap_resolution", "ceo_board_liaison", "boardroom_panellist", "boardroom_synthesis"):
        monkeypatch.delenv(f"TAO_MODEL_{role.upper()}", raising=False)
    auth = Mock(side_effect=AssertionError("health must not launch auth subprocesses"))
    monkeypatch.setattr(provider_policy, "require_transport", auth)
    report = machine_ship_readiness()
    assert report["configured"] is True
    assert report["ready"] is False
    assert report["status"] == "runtime_unverified"
    assert any("not verified" in item for item in report["blockers"])
    auth.assert_not_called()


def test_blockers_list_missing_github(monkeypatch):
    monkeypatch.setenv("TAO_MACHINE_SHIP_MODE", "1")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPO", "CleanExpo/Pi-Dev-Ops")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    report = machine_ship_readiness()
    assert report["ready"] is False
    assert "GITHUB_TOKEN unset" in report["blockers"]


def test_readiness_selection_has_no_routing_observations(monkeypatch):
    from app.server import machine_ship_readiness as readiness
    from app.server import provider_router
    seen = []
    def select(role, **kwargs):
        seen.append(kwargs)
        return provider_router.ProviderModel("claude_print", "claude-sonnet-4-6", "mid", role, "test")
    monkeypatch.setattr(readiness, "select_provider_model", select)
    readiness.machine_ship_readiness()
    assert seen and all(item == {"record_observation": False} for item in seen)
