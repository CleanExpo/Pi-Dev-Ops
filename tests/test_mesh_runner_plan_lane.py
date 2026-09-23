"""The runner's plan lane: review an idea, touch no repository, hand back a packet.

A `lane: plan` claim must never reach `git worktree add` — the lane exists so an idea is
reviewed before anything is built. The agent runs in a throwaway directory with the
code-changing tools denied, its stdout is the packet, and every way the run can go
wrong ends with the claim reported `failed`, never left `claimed`/`working` — a claim
left open holds `mesh_work_claims_one_open` and locks the ticket from the whole fleet.

`subprocess` is faked throughout. Nothing here may hang: there is no pytest-timeout.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mesh_helpers import ImmediateProc  # noqa: E402
from mesh_helpers import load_module as _load  # noqa: E402

CLAIM = {"linear_id": "UNI-77", "lane": "plan", "title": "Coach cafe owners",
         "description": "A self-paced pricing lesson."}


class Server:
    def __init__(self):
        self.updates: list[dict] = []

    def api(self, method, path, body=None):
        if path == "/api/mesh/claim/update":
            self.updates.append(body or {})
        return {"ok": True}

    def states(self) -> list[str]:
        return [u["state"] for u in self.updates]


class FakeAgent:
    """Stands in for `subprocess.Popen`: writes `stdout` to the handle it is given
    and exits with `code`, or never exits when `code` is None."""

    def __init__(self, stdout: str = "# Board packet\n", code: int | None = 0):
        self.stdout, self.code = stdout, code
        self.argv: list[str] = []
        self.cwd = ""

    def __call__(self, argv, cwd=None, stdout=None, **_kw):
        self.argv, self.cwd = list(argv), cwd
        if stdout is not None:  # the build lane does not capture stdout
            stdout.write(self.stdout.encode())
            stdout.flush()
        proc = ImmediateProc()
        proc.returncode = self.code
        proc.poll = lambda: self.code
        return proc


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    mod = _load("mesh_runner_plan_lane", "mesh/runner.py")
    monkeypatch.setattr(mod, "HOST", "TESTNODE")
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "MESH_KILL_POLL_SECONDS", 0)
    monkeypatch.setattr(mod.plan_lane, "PACKET_DIR", tmp_path / "ideas")
    git_calls: list[list[str]] = []
    monkeypatch.setattr(mod.subprocess, "run",
                        lambda argv, *a, **k: git_calls.append(list(argv)))
    mod.git_calls = git_calls
    mod.server = Server()
    mod._api = mod.server.api
    return mod


def _run(runner, monkeypatch, agent: FakeAgent) -> dict:
    monkeypatch.setattr(runner.plan_lane.subprocess, "Popen", agent)
    monkeypatch.setattr(runner.subprocess, "Popen", agent)
    return runner.run_claim(dict(CLAIM), dry_run=False)


def test_plan_lane_never_creates_a_worktree(runner, monkeypatch):
    _run(runner, monkeypatch, FakeAgent())
    assert not any("worktree" in call for call in runner.git_calls), runner.git_calls


def test_plan_lane_denies_code_changing_tools_in_one_argument(runner, monkeypatch):
    """One `=`-joined argument, last: nothing after it can be read as a tool name,
    and no later argument can be swallowed by the variadic flag."""
    agent = FakeAgent()
    _run(runner, monkeypatch, agent)
    assert agent.argv[-1] == "--disallowedTools=Bash,Edit,Write,NotebookEdit"
    assert agent.argv[:2] == [runner.AGENT_CMD, "-p"] and len(agent.argv) == 4
    assert "/gs-autoplan" in agent.argv[2]


def test_plan_lane_runs_outside_the_repository(runner, monkeypatch):
    agent = FakeAgent()
    _run(runner, monkeypatch, agent)
    assert agent.cwd and "mesh-plan-" in agent.cwd
    assert Path(runner.DEFAULT_REPO_DIR).resolve() not in Path(agent.cwd).resolve().parents


def test_plan_lane_writes_the_packet_and_reports_done_with_it(runner, monkeypatch):
    plan = _run(runner, monkeypatch, FakeAgent(stdout="# Board packet\nVerdict: PARK\n"))
    assert plan["state"] == "done"
    path = Path(plan["packet_path"])
    assert path.parent == runner.plan_lane.PACKET_DIR
    assert path.name.endswith("-UNI-77-packet.md")
    assert path.read_text() == "# Board packet\nVerdict: PARK\n"
    assert runner.server.states() == ["working", "done"]
    done = runner.server.updates[-1]
    assert done["packet_md"].startswith("# Board packet") and done["title"] == CLAIM["title"]
    assert done["host"] == "TESTNODE"  # the server attaches only for the claim's holder


def test_packet_sent_to_the_server_is_capped(runner, monkeypatch):
    _run(runner, monkeypatch, FakeAgent(stdout="x" * 25_000))
    assert len(runner.server.updates[-1]["packet_md"]) == 20_000


@pytest.mark.parametrize("stdout", ["", "  \n\t"])
def test_empty_stdout_is_a_failure(runner, monkeypatch, stdout):
    plan = _run(runner, monkeypatch, FakeAgent(stdout=stdout))
    assert plan["state"] == "failed"
    assert runner.server.states() == ["working", "failed"]
    assert "packet_md" not in runner.server.updates[-1]


def test_non_zero_exit_is_a_failure(runner, monkeypatch):
    plan = _run(runner, monkeypatch, FakeAgent(stdout="half a packet", code=2))
    assert plan["state"] == "failed" and "exited 2" in plan["error"]
    assert runner.server.states() == ["working", "failed"]


def test_timeout_is_a_failure(runner, monkeypatch):
    monkeypatch.setattr(runner, "AGENT_TIMEOUT_SECONDS", 0)
    plan = _run(runner, monkeypatch, FakeAgent(code=None))
    assert plan["state"] == "failed" and "timed out" in plan["error"]
    assert runner.server.states() == ["working", "failed"]


def test_agent_that_cannot_start_is_a_failure(runner, monkeypatch):
    def _boom(*_a, **_k):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(runner.plan_lane.subprocess, "Popen", _boom)
    plan = runner.run_claim(dict(CLAIM), dry_run=False)
    assert plan["state"] == "failed"
    assert runner.server.states() == ["working", "failed"]


# ── the build lane is unchanged ──────────────────────────────────────────────


@pytest.mark.parametrize("lane", ["build", None])
def test_build_lane_still_makes_a_worktree_and_denies_nothing(runner, monkeypatch, tmp_path, lane):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    agent = FakeAgent()
    claim = {"linear_id": "UNI-5", "repo_dir": str(repo), "title": "t"}
    if lane:
        claim["lane"] = lane
    monkeypatch.setattr(runner.subprocess, "Popen", agent)
    plan = runner.run_claim(claim, dry_run=False)
    assert any(call[3:5] == ["worktree", "add"] for call in runner.git_calls)
    assert agent.argv[:2] == [runner.AGENT_CMD, "-p"] and len(agent.argv) == 3
    assert "--disallowedTools" not in agent.argv
    assert plan["state"] == "done" and "packet_path" not in plan


@pytest.mark.parametrize("labels", [["idea:plan"], ["mesh:auto", "idea:plan"],
                                    {"nodes": [{"name": "idea:plan"}]}])
def test_lane_less_claim_carrying_idea_plan_routes_to_plan(runner, monkeypatch, labels):
    """A claim that arrives without `lane` (a dispatcher or fleet-state path) but
    whose labels say idea:plan must still be reviewed, never built."""
    claim = {k: v for k, v in CLAIM.items() if k != "lane"}
    claim["labels"] = labels
    agent = FakeAgent()
    monkeypatch.setattr(runner.plan_lane.subprocess, "Popen", agent)
    monkeypatch.setattr(runner.subprocess, "Popen", agent)
    plan = runner.run_claim(claim, dry_run=False)
    assert plan.get("lane") == "plan"
    assert not any("worktree" in call for call in runner.git_calls)


def test_explicit_build_lane_wins_over_nothing_but_mesh_auto(runner, monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    agent = FakeAgent()
    monkeypatch.setattr(runner.subprocess, "Popen", agent)
    runner.run_claim({"linear_id": "UNI-5", "repo_dir": str(repo), "title": "t",
                      "labels": ["mesh:auto"]}, dry_run=False)
    assert any(call[3:5] == ["worktree", "add"] for call in runner.git_calls)
