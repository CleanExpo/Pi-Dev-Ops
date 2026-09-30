"""tests/test_mesh_runner_hold_reporting.py — a held node says why, when, and for how long.

Estate audit 30/09, rank 18. The Mini printed `{"status": "BLOCKED", "reason": "agent
timed out"}` twenty times in a row with no timestamp, while the real cause sat in its
err.log: Claude Code had never trusted the runtime folder, dropped 37 permissions, and
the preflight agent hung until the 300 s timeout. A Railway outage (404 "Application not
found") read exactly like an empty queue, and the runner exited 0 at MESH_MAX_CLAIMS, which
KeepAlive{SuccessfulExit:false} treats as "stay down". Each test below fails on that code.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))
sys.path.insert(0, str(REPO_ROOT / "mesh"))

from mesh_helpers import Break, load_module  # noqa: E402
from test_mesh_bootstrap_reporting import _run_bootstrap, _stub_bins  # noqa: E402

UNTRUSTED = ("Ignoring 37 permissions.allow entries from .claude/settings.json: "
             "this workspace has not been trusted.")
HOST = "testnode"


def _hanging_agent(stderr: str):
    """git makes the scratch worktree; the agent hangs until run() times it out."""
    def run(cmd, cwd=None, **kwargs):
        if cmd[0] == "git" and cmd[4] == "add":
            Path(cmd[6]).mkdir(parents=True)
        elif cmd[0] == "claude":
            raise subprocess.TimeoutExpired(cmd, 300, output="", stderr=stderr)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return run


def test_an_untrusted_agent_that_hangs_is_named_not_reported_as_a_timeout():
    pf = load_module("mesh_preflight_hold", "mesh/preflight.py")
    problem = pf.agent_writes(Path("/repo"), "claude", run=_hanging_agent(UNTRUSTED))
    assert problem.startswith("agent workspace not trusted"), problem
    # control: a hang with no trust warning is still a plain timeout
    assert pf.agent_writes(Path("/repo"), "claude", run=_hanging_agent("")) == "agent timed out"


def test_bootstrap_trusts_the_runtime_folder_and_keeps_every_other_setting(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps(
        {"userID": "keep-me", "projects": {"/elsewhere": {"allowedTools": ["x"]}}}))
    result = _run_bootstrap(tmp_path, uname_s="Darwin", heartbeat_ok=True)
    assert result.returncode == 0, result.stdout + result.stderr
    config = json.loads((home / ".claude.json").read_text())
    # Claude Code checks trust on the canonical git root, which every run worktree shares
    common = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--path-format=absolute",
                             "--git-common-dir"], capture_output=True, text=True, check=True).stdout.strip()
    for key in {os.path.realpath(REPO_ROOT), os.path.realpath(os.path.dirname(common))}:
        assert config["projects"][key]["hasTrustDialogAccepted"] is True, key
    assert config["userID"] == "keep-me"
    assert config["projects"]["/elsewhere"] == {"allowedTools": ["x"]}
    assert not (home / ".claude.json.lock").exists(), "the config lock is released"


def _bootstrap_with_lock(tmp_path, lock_age: float) -> tuple[subprocess.CompletedProcess, Path]:
    """Bootstrap while Claude Code's config lock directory exists, `lock_age` seconds old."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"userID": "keep-me"}))
    lock = home / ".claude.json.lock"
    lock.mkdir()
    old = time.time() - lock_age
    os.utime(lock, (old, old))
    env = {"PATH": f"{_stub_bins(tmp_path, uname_s='Darwin', heartbeat_ok=True)}:/usr/local/bin:/usr/bin:/bin",
           "HOME": str(home), "PI_CEO_API_KEY": "test-key-not-a-real-credential",
           "MESH_TRUST_LOCK_TIMEOUT": "1"}
    result = subprocess.run(["bash", str(REPO_ROOT / "mesh" / "bootstrap.sh")], env=env, cwd=str(REPO_ROOT),
                            capture_output=True, text=True, timeout=120)
    return result, home


def test_bootstrap_waits_on_claude_codes_own_config_lock_and_never_writes_under_it(tmp_path):
    result, home = _bootstrap_with_lock(tmp_path, lock_age=0)
    assert result.returncode != 0
    assert "not trusted by Claude Code" in result.stdout + result.stderr
    assert json.loads((home / ".claude.json").read_text()) == {"userID": "keep-me"}
    assert (home / ".claude.json.lock").is_dir(), "another writer's lock is never removed while live"


def test_a_stale_config_lock_is_taken_over_and_released(tmp_path):
    result, home = _bootstrap_with_lock(tmp_path, lock_age=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert os.path.realpath(REPO_ROOT) in json.loads((home / ".claude.json").read_text())["projects"]
    assert not (home / ".claude.json.lock").exists()


def test_a_config_bootstrap_cannot_parse_is_left_alone_and_the_node_is_not_enlisted(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text("{broken-json")
    result = _run_bootstrap(tmp_path, uname_s="Darwin", heartbeat_ok=True)
    assert result.returncode != 0
    assert "is enlisted with visibility" not in result.stdout + result.stderr
    assert "not trusted by Claude Code" in result.stdout + result.stderr
    assert (home / ".claude.json").read_text() == "{broken-json"


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    monkeypatch.setenv("MESH_HOLD_ALERT_AFTER", "3")
    mod = load_module("mesh_runner_hold", "mesh/runner.py")
    monkeypatch.setattr(mod, "HOST", HOST)
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(sys, "argv", ["runner"])
    return mod


def _lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.startswith("{")]


def test_every_hold_line_is_timestamped_with_its_reason_and_a_long_hold_alerts(runner, monkeypatch, capsys):
    monkeypatch.setattr(runner, "PREFLIGHT_ENABLED", True)
    monkeypatch.setattr(runner.preflight, "check", lambda repo, agent: "agent timed out")
    monkeypatch.setattr(runner, "get_work", lambda: pytest.fail("a held node claimed"))
    sleeps = []

    def sleep(secs):  # the fourth hold's wait ends the loop
        sleeps.append(secs)
        if len(sleeps) == 4:
            raise Break()
    monkeypatch.setattr(runner.time, "sleep", sleep)
    with pytest.raises(Break):
        runner.main()
    out, err = capsys.readouterr()
    holds = _lines(out)
    assert len(holds) == 4
    assert all(isinstance(h["ts"], int) and h["hold_reason"] == "agent timed out" for h in holds)
    assert [h["holds"] for h in holds] == [1, 2, 3, 4]
    alerts = _lines(err)
    assert [a["holds"] for a in alerts] == [3], "alert once N consecutive holds is reached"
    assert alerts[0]["status"] == "ALERT" and alerts[0]["hold_reason"] == "agent timed out"


def test_max_claims_exits_non_zero_so_launchd_restarts_the_runner(runner, monkeypatch):
    monkeypatch.setattr(runner, "MAX_CLAIMS", 1)
    monkeypatch.setattr(runner, "get_work", lambda: [{"linear_id": "RA-1"}])
    monkeypatch.setattr(runner, "run_claim", lambda c, dry_run: {"linear_id": "RA-1", "state": "done"})
    monkeypatch.setattr(runner, "active_agent_count", lambda *a: 0)
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    assert runner.main() != 0


def _api(fleet: dict, self_claim: dict):
    return lambda method, path, body=None: fleet if path == "/api/mesh/fleet" else self_claim


EMPTY_FLEET = {"claims": [], "agents": [], "degraded": False}


@pytest.mark.parametrize("fleet, self_claim, outcome", [
    ({"error": "HTTP 502"}, {}, "unavailable"),
    ({"error": "HTTP 401", "detail": "bad secret"}, {}, "rejected"),
    ({**EMPTY_FLEET, "degraded": True}, {}, "unavailable"),
    ({}, {"claimed": None}, "unavailable"),
    ({**EMPTY_FLEET, "claims": [{"machine": HOST, "state": "claimed", "linear_id": "RA-1"}]}, {}, "assigned"),
    (EMPTY_FLEET, {"error": "HTTP 404", "detail": "Application not found"}, "unavailable"),
    (EMPTY_FLEET, {"error": "<urlopen error timed out>"}, "unavailable"),
    (EMPTY_FLEET, {"error": "HTTP 401", "detail": "bad secret"}, "rejected"),
    (EMPTY_FLEET, {"claimed": None, "reason": "queue empty or fully claimed"}, "empty"),
    (EMPTY_FLEET, {"claimed": {"linear_id": "RA-2"}}, "assigned"),
])
def test_each_poll_names_its_outcome(fleet, self_claim, outcome):
    fs = load_module("mesh_fleet_state_outcome", "mesh/fleet_state.py")
    seen = []
    fs.next_work(_api(fleet, self_claim), HOST, seen.append)
    assert seen == [outcome]


def test_the_poll_line_carries_the_outcome_and_the_last_good_contact(runner, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["runner", "--once"])
    ticks = iter(range(1000, 2000, 100))  # every read of the clock is a later second
    monkeypatch.setattr(runner, "LOG", runner.runner_idle.Log(clock=lambda: next(ticks)))
    monkeypatch.setattr(runner, "_api", _api(EMPTY_FLEET, {"claimed": None}))
    runner.main()
    empty = _lines(capsys.readouterr().out)[-1]
    assert empty["poll"] == "empty" and isinstance(empty["last_contact"], int) and "ts" in empty
    railway_down = {"error": "HTTP 404", "detail": "Application not found"}
    monkeypatch.setattr(runner, "_api", _api(railway_down, railway_down))
    runner.main()
    outage = _lines(capsys.readouterr().out)[-1]
    assert outage["poll"] == "unavailable"
    assert outage["last_contact"] == empty["last_contact"], "an outage is not a contact"


def test_a_fleet_read_that_answered_is_contact_even_when_the_self_claim_then_fails():
    fs = load_module("mesh_fleet_state_contact", "mesh/fleet_state.py")
    seen, contacts = [], []
    fs.next_work(_api(EMPTY_FLEET, {"error": "HTTP 503"}), HOST, seen.append, lambda: contacts.append(1))
    assert seen == ["unavailable"] and contacts == [1]
    fs.next_work(_api({"error": "HTTP 502"}, {}), HOST, seen.append, lambda: contacts.append(1))
    fs.next_work(_api({}, {"claimed": None}), HOST, seen.append, lambda: contacts.append(1))
    assert contacts == [1], "a failed or empty-bodied fleet read is not contact"


@pytest.mark.parametrize("linear, outcome", [({}, "unavailable"), ({"issues": {"nodes": None}}, "unavailable"),
                                             ({"issues": {"nodes": []}}, "empty")])
def test_claim_self_tells_the_runner_an_unread_linear_from_an_empty_queue(monkeypatch, linear, outcome):
    """Codex round 5: `_linear_graphql` returns {} on any failure, and /claim/self answered
    that with the same `queue empty` as a real empty queue, so the runner logged "empty"."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    sys.path.insert(0, str(REPO_ROOT))
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    sys.modules.pop("app.server.routes.mesh", None)
    from app.server.routes import mesh
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    monkeypatch.setattr(mesh, "_sb", lambda method, path, body=None, *, prefer="": (200, "[]"))
    monkeypatch.setattr(mesh, "_linear_graphql", lambda q: linear)
    app = FastAPI()
    app.include_router(mesh.router)
    reply = TestClient(app).post("/api/mesh/claim/self", json={"host": HOST},
                                 headers={"X-Pi-CEO-Secret": "test-secret"})
    as_runner_sees_it = reply.json() if reply.status_code < 400 else {"error": f"HTTP {reply.status_code}"}
    fs = load_module("mesh_fleet_state_route", "mesh/fleet_state.py")
    seen = []
    fs.next_work(_api(EMPTY_FLEET, as_runner_sees_it), HOST, seen.append)
    assert seen == [outcome]
