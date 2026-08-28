"""Regression coverage for the persistent Nexus Mesh worker service."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_runner():
    """Load mesh/runner.py without requiring mesh to be a package."""
    spec = importlib.util.spec_from_file_location("mesh_runner_service", REPO_ROOT / "mesh" / "runner.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_runner_reads_same_hermes_env_as_heartbeat(monkeypatch, tmp_path):
    """The work daemon can recover mesh authority from ~/.hermes/.env."""
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    (hermes / ".env").write_text("PI_CEO_API_KEY=shared-secret\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = _load_runner()
    assert runner._from_env_file("PI_CEO_API_KEY") == "shared-secret"


def test_runner_defaults_to_repository_root(monkeypatch):
    """A daemon claim cannot inherit an arbitrary launchd working directory."""
    # bootstrap.sh exports MESH_REPO_DIR into the runner service, so every
    # mesh-dispatched agent inherits it, and DEFAULT_REPO_DIR reads it at import
    # time. Left set, this asserts against the ambient session instead of the
    # fallback it claims to cover — and fails in exactly the environment the
    # guard exists to protect.
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    runner = _load_runner()
    assert runner._repo_dir_for({}) == REPO_ROOT.resolve()


def test_runner_honours_operator_repo_dir_override(monkeypatch, tmp_path):
    """MESH_REPO_DIR is the operator's deliberate override, not ambient drift."""
    monkeypatch.setenv("MESH_REPO_DIR", str(tmp_path))
    runner = _load_runner()
    assert runner._repo_dir_for({}) == tmp_path.resolve()


def test_macos_bootstrap_installs_worker_peer_to_heartbeat():
    """Fleet enlistment must install both visibility and work execution daemons."""
    bootstrap = (REPO_ROOT / "mesh" / "bootstrap.sh").read_text(encoding="utf-8")
    assert "com.unite-group.mesh-heartbeat" in bootstrap
    assert "com.unite-group.mesh-runner" in bootstrap
    assert "$MESH_DIR/runner.py" in bootstrap
    assert "MESH_REPO_DIR" in bootstrap
    assert "SuccessfulExit" in bootstrap


def test_runner_plist_never_embeds_mesh_secret():
    """The runner service must load authority at runtime, not write it into plist."""
    bootstrap = (REPO_ROOT / "mesh" / "bootstrap.sh").read_text(encoding="utf-8")
    runner_section = bootstrap.split('RUNNER_PLIST=', 1)[1]
    assert "<key>PI_CEO_API_KEY</key>" not in runner_section
    assert "reads PI_CEO_API_KEY from ~/.hermes/.env" in runner_section
