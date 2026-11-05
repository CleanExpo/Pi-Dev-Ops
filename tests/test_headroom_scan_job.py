"""HEADROOM writer, CLI and job-wrapper helper (RA-8188, AR-02).

Tests never touch the real ops SSD log: every run points HEADROOM_LOG at tmp_path.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import headroom_events as he  # noqa: E402

CLI = [sys.executable, str(ROOT / "scripts" / "headroom_events.py")]
HELPER = ROOT / "scripts" / "headroom_scan_job.sh"
MARKER = "secret-like-value-do-not-log"
WEEKLY = "You've hit your weekly limit · resets Oct 9 at 1am (Australia/Brisbane)"
KEYS = {"schema", "ts", "machine", "provider", "event", "pattern_id", "source",
        "reset_at", "exit_code", "job"}


def run_cli(tmp_path, out_text, *extra, log=None):
    src = tmp_path / "claude.out"
    src.write_text(out_text, encoding="utf-8")
    env = {**os.environ, "HEADROOM_LOG": str(log or tmp_path / "h.jsonl")}
    return subprocess.run([*CLI, "scan", str(src), *extra], capture_output=True, text=True, env=env)


def rows(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines()]


# W5: the log is read by every lane, so it must never carry what the CLI printed.
def test_w5_record_has_fixed_keys_and_no_raw_text(tmp_path):
    r = run_cli(tmp_path, f"{WEEKLY} {MARKER}\n", "--provider", "claude", "--machine", "mini",
                "--exit-code", "1", "--job", "RA-8188")
    assert r.returncode == 0, r.stderr
    raw = (tmp_path / "h.jsonl").read_text()
    assert MARKER not in raw and "Brisbane" not in raw
    (row,) = rows(tmp_path / "h.jsonl")
    assert set(row) == KEYS
    assert row["event"] == "weekly_cooling" and row["machine"] == "mini" and row["job"] == "RA-8188"


def test_w5_fixture_marker_line_is_a_real_limit_line():
    text = (ROOT / "tests/fixtures/headroom/planted_marker.txt").read_text()
    assert MARKER in text and he.classify(text, "claude", 0.0, 1)


def test_w5_hostile_machine_and_job_names_are_cleaned(tmp_path):
    r = run_cli(tmp_path, WEEKLY, "--provider", "claude", "--machine", "mini x@y.com",
                "--job", "../../" + MARKER + "@a.b", "--exit-code", "1")
    assert r.returncode == 0, r.stderr
    raw = (tmp_path / "h.jsonl").read_text()
    assert "@" not in raw and "/" not in json.loads(raw)["job"]


# W4: append-only, one JSON object per line, so AR-03 can read it while jobs write.
def test_w4_appends_never_truncates(tmp_path):
    for _ in range(2):
        assert run_cli(tmp_path, WEEKLY, "--provider", "claude", "--exit-code", "1").returncode == 0
    assert len(rows(tmp_path / "h.jsonl")) == 2


def test_w4_no_limit_message_writes_nothing_and_says_so(tmp_path):
    r = run_cli(tmp_path, "all good\n", "--provider", "claude", "--exit-code", "0")
    assert r.returncode == 0 and "no limit message" in r.stdout
    assert not (tmp_path / "h.jsonl").exists()


# W5: a failed write or read must never look like an empty, successful scan.
def test_w5_unmounted_volume_exits_nonzero_and_creates_nothing(tmp_path):
    log = tmp_path / "not-mounted" / "ops" / "headroom" / "h.jsonl"
    r = run_cli(tmp_path, WEEKLY, "--provider", "claude", "--exit-code", "1", log=log)
    assert r.returncode == he.EXIT_WRITE_FAILED
    assert not (tmp_path / "not-mounted").exists()


def test_w5_unreadable_output_file_exits_nonzero(tmp_path):
    env = {**os.environ, "HEADROOM_LOG": str(tmp_path / "h.jsonl")}
    r = subprocess.run([*CLI, "scan", str(tmp_path / "missing.out"), "--provider", "claude"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == he.EXIT_READ_FAILED and "missing.out" in r.stderr


def test_w5_headroom_dir_is_created_under_an_existing_ops_dir(tmp_path):
    log = tmp_path / "ops" / "headroom" / "h.jsonl"
    (tmp_path / "ops").mkdir()
    assert run_cli(tmp_path, WEEKLY, "--provider", "claude", "--exit-code", "1", log=log).returncode == 0
    assert log.exists()


# W2: wiring into run.sh must never change what a job does, only record what it saw.
def run_helper(tmp_path, log, rc="1", text=WEEKLY):
    job = tmp_path / "RA-1"
    job.mkdir(exist_ok=True)
    (job / "claude.out").write_text(text, encoding="utf-8")
    env = {**os.environ, "HEADROOM_LOG": str(log), "HEADROOM_PYTHON": sys.executable}
    r = subprocess.run(["bash", str(HELPER), str(job), "claude", rc, str(job / "claude.out")],
                       capture_output=True, text=True, env=env)
    return r, (job / "job.log").read_text() if (job / "job.log").exists() else ""


def test_w2_helper_records_event_and_logs_to_job_log(tmp_path):
    r, joblog = run_helper(tmp_path, tmp_path / "h.jsonl")
    assert r.returncode == 0
    assert rows(tmp_path / "h.jsonl")[0]["job"] == "RA-1"
    assert "headroom" in joblog and "weekly_cooling" in joblog


def test_w2_helper_never_fails_the_job_when_the_write_fails(tmp_path):
    r, joblog = run_helper(tmp_path, tmp_path / "gone" / "ops" / "headroom" / "h.jsonl")
    assert r.returncode == 0
    assert "headroom: FAILED" in joblog


def test_w2_helper_touches_no_sign_in_command():
    body = HELPER.read_text()
    for word in ("login", "logout", "auth ", "setup-token", "keychain", "security "):
        assert word not in body.lower(), word
