"""The plan-lane agent starts with the allowlisted environment, never the runner's own.

The build lane has passed ``agent_sandbox.agent_env()`` since the 30/09 estate audit; the
plan lane started ``claude -p`` with the runner's whole environment, so a metered API key,
a bearer token, the lane secret or the SSH agent socket in the runner reached the agent.

A real child process is spawned here (not a fake ``Popen``): it prints the environment it
actually received, and that output is the packet the runner reports. A bounded
``AGENT_TIMEOUT_SECONDS`` keeps a child that never exits from hanging the suite.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mesh_helpers import SHIPPED  # noqa: E402
from mesh_helpers import load_module as _load  # noqa: E402

CLAIM = {"linear_id": "UNI-78", "lane": "plan", "title": "Env check", "description": "x"}
PLANTED = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
           "ANTHROPIC_BASE_URL", "OPENROUTER_API_KEY", "MC_LANE_SECRET", "SSH_AUTH_SOCK")
# Set by macOS CoreFoundation inside any process that loads it, whatever env it was given.
OS_INJECTED = {"__CF_USER_TEXT_ENCODING"}


class Server:
    def __init__(self):
        self.updates: list[dict] = []

    def api(self, method, path, body=None):
        if path == "/api/mesh/claim/update":
            self.updates.append(body or {})
        return {"ok": True}


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    mod = _load("mesh_runner_plan_lane_env", "mesh/runner.py")
    monkeypatch.setattr(mod, "HOST", "TESTNODE")
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "MESH_KILL_POLL_SECONDS", 0.01)
    monkeypatch.setattr(mod, "AGENT_TIMEOUT_SECONDS", 30)
    monkeypatch.setattr(mod.plan_lane, "PACKET_DIR", tmp_path / "ideas")
    monkeypatch.setattr(mod, "ship_run", SHIPPED)
    mod.server = Server()
    mod._api = mod.server.api
    return mod


@pytest.fixture
def env_printer(tmp_path) -> Path:
    """An agent stand-in that prints the environment it received as JSON.

    The shebang names the interpreter by absolute path through a symlink in tmp_path, so
    a checkout path containing spaces cannot break the ``#!`` line.
    """
    py = tmp_path / "py"
    py.symlink_to(os.path.realpath(sys.executable))
    script = tmp_path / "print-env"
    script.write_text(f"#!{py}\nimport json, os, sys\nsys.stdout.write(json.dumps(dict(os.environ)))\n")
    script.chmod(0o755)
    return script


def _child_env(runner, monkeypatch, env_printer) -> dict:
    monkeypatch.setattr(runner, "AGENT_CMD", str(env_printer))
    plan = runner.run_claim(dict(CLAIM), dry_run=False)
    assert plan.get("state") == "done", plan
    done = [u for u in runner.server.updates if u.get("state") == "done"]
    assert done, runner.server.updates
    return json.loads(done[-1]["packet_md"])


def test_plan_lane_child_gets_only_the_allowlisted_environment(runner, monkeypatch, env_printer, tmp_path):
    sentinel = f"MESH_TEST_SENTINEL_{uuid.uuid4().hex[:12].upper()}"
    for name in (*PLANTED, sentinel):
        monkeypatch.setenv(name, f"planted-{name.lower()}")
    config_dir = str(tmp_path / "claude-config")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", config_dir)

    child = _child_env(runner, monkeypatch, env_printer)

    leaked = sorted(n for n in (*PLANTED, sentinel) if n in child)
    assert not leaked, f"plan-lane agent inherited {leaked}"
    outside = sorted(n for n in child if n.upper() not in runner.agent_sandbox._AGENT_ENV | OS_INJECTED)
    assert not outside, f"names outside the agent allowlist reached the child: {outside}"
    # Positive control: an allowlisted value does reach the child, unchanged.
    assert child.get("CLAUDE_CONFIG_DIR") == config_dir


def test_breadcrumb_and_log_line_name_the_effective_config_dir(runner, monkeypatch, tmp_path):
    config_dir = str(tmp_path / "claude-config")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", config_dir)
    runner.write_state(None, "idle")
    assert json.loads(runner.STATE_FILE.read_text())["claude_config_dir"] == config_dir
    assert json.loads(runner.LOG.line(None, runner="TESTNODE"))["claude_config_dir"] == config_dir


def test_config_dir_defaults_to_the_home_login_when_unset(runner, monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    runner.write_state(None, "idle")
    expected = str(Path.home() / ".claude")
    assert json.loads(runner.STATE_FILE.read_text())["claude_config_dir"] == expected
    assert json.loads(runner.LOG.line(None, runner="TESTNODE"))["claude_config_dir"] == expected
