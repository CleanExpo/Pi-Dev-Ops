"""tests/test_mesh_run_record.py — a mesh build run keeps its transcript and reports its outcome (UNI-2796).

Before this, `run_claim` started the agent with no output capture and reported
only `done` or `failed`. These tests pin the three halves of the fix:

  * the runner keeps a local log and sends a redacted, capped tail;
  * the server redacts again, and stores the state change even when the
    run-record columns do not exist yet (migrations are applied by hand here);
  * `run_claim` actually sends the record — exercised with a real child process
    that exits 3, so the exit code is observed, not stubbed.

The secret-shaped strings are built at runtime so no key-like literal sits in
source for a scanner to flag.
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
    """Positive control: every redaction test below is vacuous without a bank."""
    assert rr._BANK, "scripts/sync_claude_sessions bank did not load"


def test_the_tail_redacts_a_key_before_it_leaves_the_machine():
    out = rr.redacted_tail(f"agent log {_token()} end")
    assert _token() not in out
    assert "[REDACTED]" in out


def test_the_tail_is_capped():
    assert len(rr.redacted_tail("x" * 10_000)) == rr.TAIL_CHARS


def test_no_bank_means_no_tail_rather_than_a_raw_one(monkeypatch):
    monkeypatch.setattr(rr, "_BANK", None)
    assert rr.redacted_tail(f"leak {_token()}") is None


def test_a_real_run_records_exit_code_duration_and_output(tmp_path):
    rec = rr.RunRecord("run1", tmp_path)
    proc = rec.popen(["sh", "-c", f"echo started; echo {_token()}; exit 3"], cwd=str(tmp_path))
    proc.wait()
    fields = rec.fields({"error": "agent exited 3"})
    assert fields["run_id"] == "run1"
    assert fields["exit_code"] == 3
    assert fields["duration_s"] >= 0
    assert fields["error"] == "agent exited 3"
    assert "started" in fields["log_tail"]
    assert _token() not in fields["log_tail"]
    assert stat.S_IMODE(rec.path.stat().st_mode) == 0o600


def test_a_token_crossing_the_tail_boundary_leaves_no_fragment(tmp_path):
    """The one place a slice can leak: a token straddling the 4k cut. Cut first
    and its back half no longer matches the pattern; redact first and it cannot
    survive. The token starts 20 characters before the tail's first character."""
    rec = rr.RunRecord("run2", tmp_path)
    rec.close()
    tok = _token()
    rec.path.write_text("x" * 20_000 + tok + "y" * (rr.TAIL_CHARS - (len(tok) - 20)))
    tail = rec.fields({})["log_tail"]
    assert len(tail) == rr.TAIL_CHARS
    assert tok[20:] not in tail
    assert tok[20:40] not in tail


def test_a_long_single_line_keeps_its_tail(tmp_path):
    rec = rr.RunRecord("run3", tmp_path)
    rec.close()
    rec.path.write_text("z" * (rr._READ_WINDOW + 500))
    assert rec.fields({})["log_tail"] == "z" * rr.TAIL_CHARS


def test_an_unopenable_log_still_runs_and_reports(tmp_path):
    blocker = tmp_path / "mesh-runs"
    blocker.write_text("a file where the directory should be")
    rec = rr.RunRecord("run4", tmp_path)
    rec.popen(["sh", "-c", "exit 0"], cwd=str(tmp_path)).wait()
    fields = rec.fields({})
    assert fields["exit_code"] == 0
    assert fields["log_tail"] is None


# ── server side ──────────────────────────────────────────────────────────────


def test_the_server_redacts_again_and_caps():
    assert srv._REDACTION_BANK_COMPLETE, "server bank incomplete — the test below would be vacuous"
    patch = srv.record_patch(srv.RunRecordFields(
        run_id="r", exit_code=1, error="boom " + _token(),
        log_tail="head " + _token() + "x" * 5000))
    assert _token() not in patch["error"]
    assert _token() not in patch["log_tail"]
    assert len(patch["log_tail"]) <= srv.TAIL_CHARS
    assert patch["exit_code"] == 1


def test_an_incomplete_server_bank_drops_every_free_text_field(monkeypatch):
    """`error` is free text as much as the tail is: neither is stored unredactable."""
    monkeypatch.setattr(srv, "_REDACTION_BANK_COMPLETE", False)
    monkeypatch.setattr(srv, "_REDACTION_BANK", [])
    patch = srv.record_patch(srv.RunRecordFields(
        run_id="r", exit_code=2, error="boom " + _token(), log_tail="tail " + _token()))
    assert "log_tail" not in patch
    assert "error" not in patch
    assert patch == {"run_id": "r", "exit_code": 2}


def _sb_without_columns(calls):
    def sb(method, path, body, prefer=""):
        calls.append(body)
        if "run_id" in body:
            return 400, '{"code":"PGRST204","message":"Could not find the \'run_id\' column"}'
        return 200, "[]"
    return sb


def test_missing_columns_still_store_the_state_change():
    calls: list = []
    status, _ = srv.patch_claim(_sb_without_columns(calls), "PATCH", "p", {"state": "done"},
                                fields=srv.RunRecordFields(run_id="r"))
    assert status == 200
    assert calls == [{"state": "done", "run_id": "r"}, {"state": "done"}]


def _single_call(status, body):
    calls: list = []

    def sb(method, path, payload, prefer=""):
        calls.append(payload)
        return status, body

    srv.patch_claim(sb, "PATCH", "p", {"state": "done"}, fields=srv.RunRecordFields(run_id="r"))
    return calls


def test_a_body_merely_mentioning_the_code_is_not_retried():
    assert len(_single_call(400, '{"code":"PGRST100","message":"diagnostic PGRST204"}')) == 1


def test_a_missing_column_code_on_a_non_400_is_not_retried():
    assert len(_single_call(401, '{"code":"PGRST204","message":"Could not find the \'run_id\' column"}')) == 1


def test_a_missing_column_that_is_not_ours_is_not_retried():
    assert len(_single_call(400, '{"code":"PGRST204","message":"Could not find the \'foo\' column"}')) == 1


def test_other_errors_are_not_retried():
    calls: list = []

    def sb(method, path, body, prefer=""):
        calls.append(body)
        return 500, "boom"

    status, _ = srv.patch_claim(sb, "PATCH", "p", {"state": "done"},
                                fields=srv.RunRecordFields(run_id="r"))
    assert status == 500
    assert len(calls) == 1


# ── run_claim end to end ─────────────────────────────────────────────────────


def _runner(monkeypatch, tmp_path):
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    mod = _load("mesh_runner_run_record", "mesh/runner.py")
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "MESH_KILL_POLL_SECONDS", 0.01)

    def git(args, **_kw):
        """Stand in for `git worktree add/remove`: make or remove the directory only."""
        target = Path(args[-1])
        if "add" in args:
            target.mkdir(parents=True, exist_ok=True)
        elif "remove" in args:
            shutil.rmtree(target, ignore_errors=True)

    monkeypatch.setattr(mod.subprocess, "run", git)
    calls: list = []
    monkeypatch.setattr(mod, "_api", lambda m, p, b=None: calls.append((p, b or {})) or {})
    return mod, calls


def test_run_claim_reports_the_run_record_of_a_real_failing_agent(monkeypatch, tmp_path):
    runner, calls = _runner(monkeypatch, tmp_path)
    agent = tmp_path / "agent"
    agent.write_text("#!/bin/sh\necho agent-ran\nexit 3\n")
    agent.chmod(0o755)
    monkeypatch.setattr(runner, "AGENT_CMD", str(agent))
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)

    plan = runner.run_claim({"linear_id": "UNI-X", "repo_dir": str(repo)}, dry_run=False)

    final = [b for p, b in calls if p == "/api/mesh/claim/update"][-1]
    assert plan["state"] == "failed"
    assert final["state"] == "failed"
    assert final["exit_code"] == 3
    assert final["error"] == "agent exited 3"
    assert "agent-ran" in final["log_tail"]
    assert final["run_id"]
    assert (tmp_path / "mesh-runs" / f"{final['run_id']}.log").exists()


def test_a_claim_failed_before_running_sends_its_reason(monkeypatch, tmp_path):
    runner, calls = _runner(monkeypatch, tmp_path)
    missing = tmp_path / "not-a-checkout"
    missing.mkdir()
    runner.run_claim({"linear_id": "UNI-Y", "repo_dir": str(missing)}, dry_run=False)
    final = [b for p, b in calls if p == "/api/mesh/claim/update"][-1]
    assert final["state"] == "failed"
    assert final["error"].startswith("repo missing")
