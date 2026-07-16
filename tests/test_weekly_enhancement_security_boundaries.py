"""RED regressions for the weekly enhancement loop's security boundaries.

These tests are deliberately network-free.  Provider, git, GitHub and shell
adapters are replaced with fakes before the unsafe path is exercised.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "weekly_enhancement_loop.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "weekly-enhancement-loop.yml"


@pytest.fixture
def loop(monkeypatch):
    """Load a fresh runner module with only fake credentials in its environment."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "FAKE_PROVIDER_CREDENTIAL_FOR_TEST")
    monkeypatch.setenv("GH_ENHANCE_PAT", "FAKE_GITHUB_CREDENTIAL_FOR_TEST")
    name = "weekly_enhancement_loop_security_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_kill_switch_tripped", lambda: None)
    return module


def completed(argv, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def test_model_shell_subprocess_receives_a_scrubbed_environment(loop, monkeypatch, tmp_path):
    captured = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return completed(argv)

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    loop._exec_tool("run_bash", {"cmd": "git status --short"}, tmp_path)

    child_env = captured.get("env")
    assert child_env is not None, "model-controlled subprocess must not inherit the runner environment"
    assert "OPENROUTER_API_KEY" not in child_env
    assert "GH_ENHANCE_PAT" not in child_env


def test_model_cannot_request_arbitrary_shell_execution(loop, monkeypatch, tmp_path):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return completed(argv)

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    result = loop._exec_tool("run_bash", {"cmd": "curl https://attacker.invalid"}, tmp_path)

    assert result.startswith("ERROR: command not allowed")
    assert calls == [], "a rejected model command must never reach the shell adapter"


def test_clone_never_embeds_github_credentials_in_process_arguments(loop, monkeypatch, tmp_path):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return completed(argv)

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    loop._clone("CleanExpo/Pi-Dev-Ops", tmp_path / "clone")

    argv = [str(part) for part in calls[0][0]]
    assert "FAKE_GITHUB_CREDENTIAL_FOR_TEST" not in " ".join(argv)
    assert argv[-2] == "https://github.com/CleanExpo/Pi-Dev-Ops.git"


def test_github_subprocess_does_not_receive_provider_or_unrelated_secrets(loop, monkeypatch):
    captured = {}
    monkeypatch.setenv("UNRELATED_PRIVATE_VALUE", "FAKE_UNRELATED_CREDENTIAL_FOR_TEST")

    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return completed(argv, stdout="https://github.com/CleanExpo/Pi-Dev-Ops/pull/123\n")

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    loop._open_pr("CleanExpo/Pi-Dev-Ops", "enhance-review/weekly-test", "2026-07-17")

    child_env = captured["env"]
    assert child_env.get("GH_TOKEN") == "FAKE_GITHUB_CREDENTIAL_FOR_TEST"
    assert "OPENROUTER_API_KEY" not in child_env
    assert "UNRELATED_PRIVATE_VALUE" not in child_env


def test_cli_rejects_repository_outside_registry_allowlist(loop, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(loop, "_openrouter_key", lambda: "FAKE")
    monkeypatch.setattr(loop, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(loop, "load_repos", lambda: ["CleanExpo/Pi-Dev-Ops"])
    monkeypatch.setattr(
        loop,
        "enhance_repo",
        lambda repo, dry_run, spent: calls.append(repo) or {"repo": repo, "outcome": "no-op"},
    )
    monkeypatch.setattr(sys, "argv", ["weekly_enhancement_loop.py", "--repo", "OtherOrg/Repo"])

    rc = loop.main()

    assert rc == 2
    assert calls == []


@pytest.mark.parametrize(
    "unsafe_repo",
    ["CleanExpo/repo; touch pwned", "CleanExpo/../..", "CleanExpo/repo name", "CleanExpo/repo$(id)"],
)
def test_cli_rejects_unsafe_repository_syntax(loop, monkeypatch, tmp_path, unsafe_repo):
    calls = []
    monkeypatch.setattr(loop, "_openrouter_key", lambda: "FAKE")
    monkeypatch.setattr(loop, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(loop, "load_repos", lambda: ["CleanExpo/Pi-Dev-Ops"])
    monkeypatch.setattr(
        loop,
        "enhance_repo",
        lambda repo, dry_run, spent: calls.append(repo) or {"repo": repo, "outcome": "no-op"},
    )
    monkeypatch.setattr(sys, "argv", ["weekly_enhancement_loop.py", "--repo", unsafe_repo])

    rc = loop.main()

    assert rc == 2
    assert calls == []


def test_workflow_does_not_construct_shell_source_from_dispatch_input():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "format('--repo {0}'" not in workflow
    assert "github.event.inputs.repo" not in workflow.split("run: |", 1)[1]


@pytest.mark.parametrize(
    "protected_path",
    ["app/server/config.py", ".env", "dashboard/middleware.ts", "supabase/seed.sql"],
)
def test_model_write_tool_rejects_protected_paths(loop, tmp_path, protected_path):
    result = loop._exec_tool("write_file", {"path": protected_path, "content": "test-only"}, tmp_path)

    assert result.startswith("ERROR: protected path")
    assert not (tmp_path / protected_path).exists()


def test_provider_request_is_reserved_before_spend_can_overshoot(loop, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(loop, "MAX_COST_USD", 1.0)

    def fake_post(payload, key, timeout):
        calls.append(payload)
        return {"content": [], "stop_reason": "end_turn", "usage": {"cost": 0.02}}

    monkeypatch.setattr(loop, "_post", fake_post)
    with pytest.raises(loop.CostCeilingHit):
        loop.run_phase("monitor", "fake/model", "scan", tmp_path, 1, {"usd": 0.99})

    assert calls == [], "budget rejection must happen before the paid provider adapter is called"


def test_missing_authoritative_usage_cost_fails_closed(loop, monkeypatch, tmp_path):
    monkeypatch.setattr(
        loop,
        "_post",
        lambda payload, key, timeout: {"content": [], "stop_reason": "end_turn", "usage": {}},
    )

    with pytest.raises(loop.CostCeilingHit, match="usage cost"):
        loop.run_phase("monitor", "fake/model", "scan", tmp_path, 1, {"usd": 0.0})


def test_monitor_role_has_a_bounded_token_ceiling(loop, monkeypatch, tmp_path):
    payloads = []

    def fake_post(payload, key, timeout):
        payloads.append(payload)
        return {"content": [], "stop_reason": "end_turn", "usage": {"cost": 0.001}}

    monkeypatch.setattr(loop, "_post", fake_post)
    loop.run_phase("monitor", "fake/model", "scan", tmp_path, 1, {"usd": 0.0})

    assert payloads[0]["max_tokens"] <= 2_000


def test_role_iteration_ceiling_aborts_instead_of_returning_partial_success(loop, monkeypatch, tmp_path):
    monkeypatch.setattr(loop, "MAX_PHASE_ITERS", 2)
    counter = {"calls": 0}

    def fake_post(payload, key, timeout):
        counter["calls"] += 1
        return {
            "content": [{"type": "tool_use", "id": f"tool-{counter['calls']}", "name": "list_dir", "input": {}}],
            "stop_reason": "tool_use",
            "usage": {"cost": 0.001},
        }

    monkeypatch.setattr(loop, "_post", fake_post)
    monkeypatch.setattr(loop, "_exec_tool", lambda name, args, cwd: "fake tool result")

    with pytest.raises(loop.CostCeilingHit, match="iteration"):
        loop.run_phase("monitor", "fake/model", "scan", tmp_path, 1, {"usd": 0.0})
