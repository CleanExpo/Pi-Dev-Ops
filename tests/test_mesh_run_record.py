"""tests/test_mesh_run_record.py — a mesh build run keeps its transcript and reports its outcome (UNI-2796).

Before this, `run_claim` started the agent with no output capture and reported
only `done` or `failed`. These tests pin the fix:

  * the runner keeps the full log on its own machine (0600) and sends only the
    outcome: run id, duration, exit code, and an error redacted before sending;
  * no log text crosses the wire (three review rounds showed a tail cannot be
    made safe while nodes lack the server's full secret bank);
  * the server redacts the error again, drops it when its bank is incomplete,
    and stores the state change even when the run-record columns do not exist
    yet — retrying only when the error names one of OUR columns on OUR table;
  * `run_claim` sends the record, observed with a real child process that exits 3,
    and still reports a terminal state when the record itself cannot be built.

Secret-shaped strings are assembled at runtime so no key-like literal sits in source.
"""
from __future__ import annotations

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


# ── runner side ──────────────────────────────────────────────────────────────


def test_the_runner_bank_loads_on_this_interpreter():
    """Positive control: every runner redaction test below is vacuous without a bank."""
    assert rr._BANK, "scripts/sync_claude_sessions bank did not load"


def test_the_runner_redacts_the_error_before_sending():
    out = rr.redact_error(f"boom {_token()}")
    assert _token() not in out
    assert "[REDACTED]" in out


def test_the_error_is_capped():
    assert len(rr.redact_error("x" * 2_000)) == rr.ERROR_CHARS


def test_no_bank_withholds_the_error(monkeypatch):
    monkeypatch.setattr(rr, "_BANK", None)
    assert rr.redact_error(f"leak {_token()}") is None


def test_an_empty_bank_is_no_bank(monkeypatch):
    """An empty list matches nothing; treating it as a bank would send text raw."""
    monkeypatch.setattr(rr, "_BANK", [])
    assert rr.redact_error(f"leak {_token()}") is None


def test_no_log_text_is_sent(tmp_path):
    rec = rr.RunRecord("run0", tmp_path)
    rec.popen(["sh", "-c", f"echo {_token()}; echo visible-output"], cwd=str(tmp_path)).wait()
    fields = rec.fields({})
    assert set(fields) == {"run_id", "duration_s", "exit_code", "error"}
    assert "visible-output" not in repr(fields)


def test_a_real_run_records_exit_code_duration_and_keeps_its_log(tmp_path):
    rec = rr.RunRecord("run1", tmp_path)
    rec.popen(["sh", "-c", "echo started; exit 3"], cwd=str(tmp_path)).wait()
    fields = rec.fields({"error": f"agent exited 3 {_token()}"})
    assert fields["run_id"] == "run1"
    assert fields["exit_code"] == 3
    assert fields["duration_s"] >= 0
    assert fields["error"].startswith("agent exited 3")
    assert _token() not in fields["error"]
    assert "started" in rec.path.read_text()
    assert stat.S_IMODE(rec.path.stat().st_mode) == 0o600


def test_an_unopenable_log_still_runs_and_reports(tmp_path):
    (tmp_path / "mesh-runs").write_text("a file where the directory should be")
    rec = rr.RunRecord("run4", tmp_path)
    rec.popen(["sh", "-c", "exit 0"], cwd=str(tmp_path)).wait()
    assert rec.path is None
    assert rec.fields({})["exit_code"] == 0


def test_a_record_that_never_existed_still_reports_its_error():
    assert rr.fields(None, {"error": f"setup failed {_token()}"}) == {
        "error": "setup failed [REDACTED]"}


# ── server side ──────────────────────────────────────────────────────────────


def test_the_server_redacts_the_error_again():
    assert srv._REDACTION_BANK_COMPLETE, "server bank incomplete — this test would be vacuous"
    patch = srv.record_patch(srv.RunRecordFields(run_id="r", exit_code=1, error="boom " + _token()))
    assert _token() not in patch["error"]
    assert patch["exit_code"] == 1


def test_an_incomplete_server_bank_drops_the_error(monkeypatch):
    monkeypatch.setattr(srv, "_REDACTION_BANK_COMPLETE", False)
    monkeypatch.setattr(srv, "_REDACTION_BANK", [])
    patch = srv.record_patch(srv.RunRecordFields(run_id="r", exit_code=2, error="boom " + _token()))
    assert patch == {"run_id": "r", "exit_code": 2}


def _calls(status, body):
    """How many PATCHes `patch_claim` makes when the first answers (status, body)."""
    calls: list = []

    def sb(method, path, payload, prefer=""):
        calls.append(payload)
        return (status, body) if len(calls) == 1 else (200, "[]")

    srv.patch_claim(sb, "PATCH", "mesh_work_claims?linear_id=eq.X", {"state": "done"},
                    fields=srv.RunRecordFields(run_id="r", error="e"))
    return calls


def test_our_missing_column_on_our_table_stores_the_state_change():
    rest = '{"code":"PGRST204","message":"Could not find the \'run_id\' column of \'mesh_work_claims\' in the schema cache"}'
    pg = '{"code":"42703","message":"column \\"run_id\\" of relation \\"mesh_work_claims\\" does not exist"}'
    qualified = '{"code":"42703","message":"column mesh_work_claims.run_id does not exist"}'
    for body in (rest, pg, qualified):
        calls = _calls(400, body)
        assert len(calls) == 2, body
        assert calls[1] == {"state": "done"}


def test_look_alike_errors_are_not_retried():
    for status, body in (
        (400, '{"code":"PGRST100","message":"diagnostic PGRST204"}'),
        (401, '{"code":"PGRST204","message":"Could not find the \'run_id\' column of \'mesh_work_claims\'"}'),
        (400, '{"code":"PGRST204","message":"Could not find the \'terror\' column of \'mesh_work_claims\'"}'),
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
    assert final["error"] == "agent exited 3"
    assert "agent-ran" in (tmp_path / "mesh-runs" / f"{final['run_id']}.log").read_text()


def test_a_record_that_cannot_be_built_still_ends_the_claim(monkeypatch, tmp_path):
    """Construction failing after `working` was reported must not strand the claim."""
    runner, calls, removed, repo = _runner(monkeypatch, tmp_path)

    def boom(*_a, **_k):
        raise OSError("synthetic log setup failure")

    monkeypatch.setattr(runner.run_record, "RunRecord", boom)
    runner.run_claim({"linear_id": "UNI-Z", "repo_dir": str(repo)}, dry_run=False)

    states = [b["state"] for b in _updates(calls)]
    assert states == ["working", "failed"]
    assert _updates(calls)[-1]["error"] == "synthetic log setup failure"
    assert removed, "worktree was not cleaned up"


def test_a_claim_failed_before_running_sends_its_reason_redacted(monkeypatch, tmp_path):
    runner, calls, _removed, _repo = _runner(monkeypatch, tmp_path)
    missing = tmp_path / ("not-a-checkout-" + _token())
    missing.mkdir()
    runner.run_claim({"linear_id": "UNI-Y", "repo_dir": str(missing)}, dry_run=False)
    final = _updates(calls)[-1]
    assert final["state"] == "failed"
    assert final["error"].startswith("repo missing")
    assert _token() not in final["error"]
