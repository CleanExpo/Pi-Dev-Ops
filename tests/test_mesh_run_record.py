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
  * `run_claim` end to end lives in tests/test_mesh_run_record_claim.py (size gate).

Secret-shaped strings are assembled at runtime so no key-like literal sits in source.
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mesh_helpers import hostile_exception as _hostile  # noqa: E402
from mesh_helpers import load_module as _load  # noqa: E402
from mesh_helpers import secret_token as _token  # noqa: E402
from mesh_helpers import server_only_secret as _server_only_secret  # noqa: E402

from app.server import mesh_run_record as srv  # noqa: E402

rr = _load("mesh_run_record_under_test", "mesh/run_record.py")


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


def test_an_exception_sends_neither_its_message_nor_its_class_name(tmp_path):
    for base, code in ((OSError, "runner_exception_os"), (Exception, "runner_exception")):
        plan: dict = {}

        def raise_hostile(*_a, _base=base, **_k):
            raise _hostile(_base)("Popen setup failed: " + _server_only_secret())

        rec = rr.run_agent(raise_hostile, str(tmp_path), tmp_path, "0a0a0a09", plan, lambda *_: None)
        sent = rr.fields(rec, plan)
        assert sent["error_code"] == code
        assert plan["state"] == "failed"
        for leaked in ("SECRET_QWERTY", "qwertyuiop"):
            assert leaked not in repr(sent), leaked
        assert "error_code" in srv.record_patch(srv.RunRecordFields(error_code=sent["error_code"]))


def test_only_facts_are_sent(tmp_path):
    rec = rr.RunRecord("0a0a0a00", tmp_path)
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
        rec = rr.RunRecord("0a0a0a01", tmp_path)
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
        rr.RunRecord("0a0a0a1b", tmp_path).close()
    finally:
        os.umask(old)
    assert seen == [0o600]


def test_an_existing_file_at_the_log_path_is_never_touched(tmp_path):
    """Round 11: O_TRUNC wiped an earlier transcript under a repeated id, and a hard link's target."""
    (tmp_path / "mesh-runs").mkdir()
    earlier = tmp_path / "mesh-runs" / "0a0a0a02.log"
    earlier.write_text("first agent transcript")
    victim = tmp_path / "victim"
    victim.write_text("must survive")
    (tmp_path / "mesh-runs" / "0a0a0a12.log").hardlink_to(victim)
    for run_id in ("0a0a0a02", "0a0a0a12"):
        rec = rr.RunRecord(run_id, tmp_path)
        assert rec.path is None, run_id
        rec.popen(["sh", "-c", "echo second"], cwd=str(tmp_path)).wait()
        rec.close()
    assert earlier.read_text() == "first agent transcript"
    assert victim.read_text() == "must survive"


def test_a_log_that_cannot_be_made_private_is_removed_not_written(tmp_path, monkeypatch):
    def refuse(_fd, _mode):
        raise OSError("synthetic fchmod failure")

    monkeypatch.setattr(rr.os, "fchmod", refuse)
    rec = rr.RunRecord("0a0a0a03", tmp_path)
    assert rec.path is None
    assert not (tmp_path / "mesh-runs" / "0a0a0a03.log").exists()
    rec.popen(["sh", "-c", "exit 0"], cwd=str(tmp_path)).wait()
    assert rec.fields({})["exit_code"] == 0


def test_a_run_id_that_is_not_the_generated_hex_opens_nothing(tmp_path):
    """Round 6: `../escape` used to create (and os.open would truncate) a file outside mesh-runs."""
    victim = tmp_path / "escape.log"
    victim.write_text("must survive")
    for bad in ("../escape", "../../escape", "/abs/path", "ZZZZZZZZ", "0a0a0a0a/../x", "deadbeef" * 4):
        rec = rr.RunRecord(bad, tmp_path)
        assert rec.path is None, bad
        rec.popen(["sh", "-c", "echo out"], cwd=str(tmp_path)).wait()
        assert rec.fields({})["exit_code"] == 0
    assert victim.read_text() == "must survive"
    assert sorted(x.name for x in tmp_path.iterdir()) == ["escape.log"]


def test_a_log_close_failure_never_raises(tmp_path):
    for run_id, error in (("0a0a0a05", OSError("log flush failed")), ("0a0a0a15", ValueError("close broke"))):
        rec = rr.RunRecord(run_id, tmp_path)

        class Broken:
            closed = False

            def close(self, error=error):
                raise error

        rec._log = Broken()
        assert rec.fields({})["run_id"] == run_id


def test_fields_never_raises_even_if_the_record_does(tmp_path):
    class Exploding:
        def fields(self, plan):
            raise OSError("boom")

    assert rr.fields(Exploding(), {"error": "agent exited 1"}) == {"error_code": "agent_exit"}


def test_worktree_removal_that_cannot_start_does_not_raise(tmp_path, monkeypatch):
    def no_git(*_a, **_k):
        raise OSError("remove-spawn-failed")

    monkeypatch.setattr(rr.subprocess, "run", no_git)
    rr.remove_worktree(tmp_path, tmp_path / "wt")


def test_an_unopenable_log_still_runs_and_reports(tmp_path):
    (tmp_path / "mesh-runs").write_text("a file where the directory should be")
    rec = rr.RunRecord("0a0a0a04", tmp_path)
    rec.popen(["sh", "-c", "exit 0"], cwd=str(tmp_path)).wait()
    assert rec.path is None
    assert rec.fields({})["exit_code"] == 0


# ── server side: known shapes only ───────────────────────────────────────────


def test_the_server_stores_known_shapes():
    for code in ("agent_exit", "timeout", "repo_missing", "worktree_add_failed",
                 "runner_exception", "runner_exception_os"):
        patch = srv.record_patch(srv.RunRecordFields(
            run_id="0a1b2c3d", duration_s=1.5, exit_code=3, error_code=code))
        assert patch == {"run_id": "0a1b2c3d", "duration_s": 1.5, "exit_code": 3,
                         "error_code": code}


def test_the_server_drops_anything_that_is_not_a_known_shape():
    for bad in ("agent_exit " + _token(), "boom " + _token(), _server_only_secret(),
                "runner_exception:" + "SECRET_QWERTY_12345", "agent_exit:" + "SECRET_QWERTY_12345",
                "runner_exception:OSError", "agent_exit\n", "AGENT_EXIT"):
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


def test_finish_runs_every_step_even_when_one_raises():
    """Round 15: the terminal update raising skipped worktree removal and the idle state."""
    import pytest

    ran: list = []

    def broken():
        ran.append("report")
        raise ValueError("unknown url type")

    with pytest.raises(ValueError):
        rr.finish(broken, lambda: ran.append("remove"), lambda: ran.append("idle"))
    assert ran == ["report", "remove", "idle"]


def test_a_terminal_update_that_raises_still_cleans_up(monkeypatch, tmp_path):
    """Round 15, end to end: `_api` raising on the done update left the worktree and state `working`."""
    import json

    import pytest
    from test_mesh_run_record_claim import _runner

    runner, _calls, removed, repo = _runner(monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "AGENT_CMD", "true")

    def api(_method, _path, body=None):
        if (body or {}).get("state") in ("done", "failed"):
            raise ValueError("unknown url type")
        return {}

    monkeypatch.setattr(runner, "_api", api)
    with pytest.raises(ValueError):
        runner.run_claim({"linear_id": "UNI-T", "repo_dir": str(repo)}, dry_run=False)
    assert removed, "worktree was not cleaned up"
    assert json.loads((tmp_path / "state.json").read_text())["state"] == "idle"
