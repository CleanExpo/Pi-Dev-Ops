"""tests/test_mesh_run_record.py — a mesh build run keeps its transcript and reports its outcome (UNI-2796).

Before this, `run_claim` started the agent with no output capture and reported
only `done` or `failed`. These tests pin the fix:

  * the runner keeps the full log on its own machine, owner-only from the first
    byte, and sends only facts: run id, duration, exit code, and an error code
    from a fixed vocabulary;
  * NO free text crosses the wire — four review rounds found secrets in every
    free-text field tried (a redacted log tail, then a redacted error string);
  * the server stores only values of a known shape, and stores the state change
    even when the run-record columns do not exist yet, retrying only when the
    error names one of OUR columns on OUR table;
  * `run_claim` sends the record, observed with a real child process that exits 3,
    and still reports a terminal state when the record itself cannot be built.

Secret-shaped strings are assembled at runtime so no key-like literal sits in source.
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mesh_helpers import load_module as _load  # noqa: E402

from app.server import mesh_run_record as srv  # noqa: E402

rr = _load("mesh_run_record_under_test", "mesh/run_record.py")


def _token() -> str:
    """An Anthropic-API-key-shaped string, assembled at runtime."""
    return "sk-ant-" + "api03-" + "Ab3_" * 24


def _server_only_secret() -> str:
    """Round 4's reproduction: a shape the runner's transcript bank does not know."""
    return "token='" + "qwertyuiop" + "asdfghjklz'"


# ── runner side: facts, not prose ────────────────────────────────────────────


def test_each_runner_failure_maps_to_a_fixed_code():
    cases = {
        "agent exited 3": "agent_exit",
        "timed out after 3600s": "timeout",
        "repo missing: /x/" + _token(): "repo_missing",
        "git worktree add failed": "worktree_add_failed",
        "something unforeseen " + _token(): "runner_exception",
    }
    for text, code in cases.items():
        assert rr.error_code({"error": text}) == code, text
    assert rr.error_code({}) is None


def test_an_exception_is_sent_as_its_class_name_only():
    plan = {"error": "Popen setup failed: " + _server_only_secret(), "error_type": "OSError"}
    assert rr.error_code(plan) == "runner_exception:OSError"


def test_only_facts_are_sent(tmp_path):
    rec = rr.RunRecord("run0", tmp_path)
    rec.popen(["sh", "-c", f"echo {_token()}; echo visible-output; exit 3"], cwd=str(tmp_path)).wait()
    fields = rec.fields({"error": f"agent exited 3 {_server_only_secret()}"})
    assert set(fields) == {"run_id", "duration_s", "exit_code", "error_code"}
    assert fields["exit_code"] == 3
    assert fields["error_code"] == "agent_exit"
    for leaked in ("visible-output", _token(), "qwertyuiop"):
        assert leaked not in repr(fields), leaked


def test_the_log_stays_on_the_node_owner_only(tmp_path):
    old = os.umask(0o022)
    try:
        rec = rr.RunRecord("run1", tmp_path)
    finally:
        os.umask(old)
    rec.popen(["sh", "-c", "echo started"], cwd=str(tmp_path)).wait()
    rec.close()
    assert "started" in rec.path.read_text()
    assert stat.S_IMODE(rec.path.stat().st_mode) == 0o600


def test_the_log_is_private_at_creation_not_just_afterwards(tmp_path, monkeypatch):
    """No window with the umask's wider mode: record the mode fchmod finds on arrival."""
    seen: list = []
    real_fchmod = rr.os.fchmod

    def spy(fd, mode):
        seen.append(stat.S_IMODE(os.fstat(fd).st_mode))
        real_fchmod(fd, mode)

    monkeypatch.setattr(rr.os, "fchmod", spy)
    old = os.umask(0o022)
    try:
        rr.RunRecord("run1b", tmp_path).close()
    finally:
        os.umask(old)
    assert seen == [0o600]


def test_a_pre_existing_wider_log_is_narrowed(tmp_path):
    (tmp_path / "mesh-runs").mkdir()
    stale = tmp_path / "mesh-runs" / "run2.log"
    stale.write_text("old")
    stale.chmod(0o644)
    rec = rr.RunRecord("run2", tmp_path)
    rec.close()
    assert stat.S_IMODE(stale.stat().st_mode) == 0o600


def test_a_log_that_cannot_be_made_private_is_removed_not_written(tmp_path, monkeypatch):
    def refuse(_fd, _mode):
        raise OSError("synthetic fchmod failure")

    monkeypatch.setattr(rr.os, "fchmod", refuse)
    rec = rr.RunRecord("run3", tmp_path)
    assert rec.path is None
    assert not (tmp_path / "mesh-runs" / "run3.log").exists()
    rec.popen(["sh", "-c", "exit 0"], cwd=str(tmp_path)).wait()
    assert rec.fields({})["exit_code"] == 0


def test_an_unopenable_log_still_runs_and_reports(tmp_path):
    (tmp_path / "mesh-runs").write_text("a file where the directory should be")
    rec = rr.RunRecord("run4", tmp_path)
    rec.popen(["sh", "-c", "exit 0"], cwd=str(tmp_path)).wait()
    assert rec.path is None
    assert rec.fields({})["exit_code"] == 0


# ── server side: known shapes only ───────────────────────────────────────────


def test_the_server_stores_known_shapes():
    patch = srv.record_patch(srv.RunRecordFields(
        run_id="0a1b2c3d", duration_s=1.5, exit_code=3, error_code="runner_exception:OSError"))
    assert patch == {"run_id": "0a1b2c3d", "duration_s": 1.5, "exit_code": 3,
                     "error_code": "runner_exception:OSError"}


def test_the_server_drops_anything_that_is_not_a_known_shape():
    for bad in ("agent_exit " + _token(), "boom " + _token(), _server_only_secret(),
                "runner_exception:" + "Bad-Name", "runner_exception:" + "x" * 41, "agent_exit\n"):
        assert "error_code" not in srv.record_patch(srv.RunRecordFields(error_code=bad)), bad
    for bad_id in (_token(), "../../etc", "ZZZZZZZZ"):
        assert "run_id" not in srv.record_patch(srv.RunRecordFields(run_id=bad_id)), bad_id


def _calls(status, body):
    """How many PATCHes `patch_claim` makes when the first answers (status, body)."""
    calls: list = []

    def sb(method, path, payload, prefer=""):
        calls.append(payload)
        return (status, body) if len(calls) == 1 else (200, "[]")

    srv.patch_claim(sb, "PATCH", "mesh_work_claims?linear_id=eq.X", {"state": "done"},
                    fields=srv.RunRecordFields(run_id="0a1b2c3d", error_code="timeout"))
    return calls


def test_our_missing_column_on_our_table_stores_the_state_change():
    rest = '{"code":"PGRST204","message":"Could not find the \'run_id\' column of \'mesh_work_claims\' in the schema cache"}'
    pg = '{"code":"42703","message":"column \\"error_code\\" of relation \\"mesh_work_claims\\" does not exist"}'
    qualified = '{"code":"42703","message":"column mesh_work_claims.run_id does not exist"}'
    for body in (rest, pg, qualified):
        calls = _calls(400, body)
        assert len(calls) == 2, body
        assert calls[1] == {"state": "done"}


def test_look_alike_errors_are_not_retried():
    for status, body in (
        (400, '{"code":"PGRST100","message":"diagnostic PGRST204"}'),
        (401, '{"code":"PGRST204","message":"Could not find the \'run_id\' column of \'mesh_work_claims\'"}'),
        (400, '{"code":"PGRST204","message":"Could not find the \'terror_code\' column of \'mesh_work_claims\'"}'),
        (400, '{"code":"42703","message":"column \\"external_run_id\\" of relation \\"mesh_work_claims\\" does not exist"}'),
        (400, '{"code":"42703","message":"column \\"run_id\\" of relation \\"other_table\\" does not exist"}'),
        (400, '{"code":"42703","message":"column other_table.run_id does not exist"}'),
        (500, "boom"),
    ):
        assert len(_calls(status, body)) == 1, body


# ── run_claim end to end ─────────────────────────────────────────────────────


def _runner(monkeypatch, tmp_path):
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    mod = _load("mesh_runner_run_record", "mesh/runner.py")
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "MESH_KILL_POLL_SECONDS", 0.01)
    removed: list = []

    def git(args, **_kw):
        """Stand in for `git worktree add/remove`: make or remove the directory only."""
        target = Path(args[-1])
        if "add" in args:
            target.mkdir(parents=True, exist_ok=True)
        elif "remove" in args:
            removed.append(target)
            shutil.rmtree(target, ignore_errors=True)

    monkeypatch.setattr(mod.subprocess, "run", git)
    calls: list = []
    monkeypatch.setattr(mod, "_api", lambda m, p, b=None: calls.append((p, b or {})) or {})
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    return mod, calls, removed, repo


def _updates(calls):
    return [b for p, b in calls if p == "/api/mesh/claim/update"]


def test_run_claim_reports_the_run_record_of_a_real_failing_agent(monkeypatch, tmp_path):
    runner, calls, _removed, repo = _runner(monkeypatch, tmp_path)
    agent = tmp_path / "agent"
    agent.write_text("#!/bin/sh\necho agent-ran\nexit 3\n")
    agent.chmod(0o755)
    monkeypatch.setattr(runner, "AGENT_CMD", str(agent))

    plan = runner.run_claim({"linear_id": "UNI-X", "repo_dir": str(repo)}, dry_run=False)

    final = _updates(calls)[-1]
    assert plan["state"] == "failed"
    assert final["state"] == "failed"
    assert final["exit_code"] == 3
    assert final["error_code"] == "agent_exit"
    assert "agent-ran" in (tmp_path / "mesh-runs" / f"{final['run_id']}.log").read_text()


def test_a_record_that_cannot_be_built_still_ends_the_claim(monkeypatch, tmp_path):
    """Construction failing after `working` was reported must not strand the claim,
    and the exception's message — round 4's leak — must not be sent."""
    runner, calls, removed, repo = _runner(monkeypatch, tmp_path)

    def boom(*_a, **_k):
        raise OSError("Popen setup failed: " + _server_only_secret())

    monkeypatch.setattr(runner.run_record, "RunRecord", boom)
    runner.run_claim({"linear_id": "UNI-Z", "repo_dir": str(repo)}, dry_run=False)

    assert [b["state"] for b in _updates(calls)] == ["working", "failed"]
    assert _updates(calls)[-1]["error_code"] == "runner_exception:OSError"
    assert "qwertyuiop" not in repr(calls)
    assert removed, "worktree was not cleaned up"


def test_a_claim_failed_before_running_sends_only_its_code(monkeypatch, tmp_path):
    runner, calls, _removed, _repo = _runner(monkeypatch, tmp_path)
    missing = tmp_path / ("not-a-checkout-" + _token())
    missing.mkdir()
    runner.run_claim({"linear_id": "UNI-Y", "repo_dir": str(missing)}, dry_run=False)
    final = _updates(calls)[-1]
    assert final["state"] == "failed"
    assert final["error_code"] == "repo_missing"
    assert _token() not in repr(calls)
