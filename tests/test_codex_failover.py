"""Codex review failover, Mini -> MacBook (RA-8191, AR-05).

Each test names the why (W1-W5) it traces to; the chain is in docs/codex-failover.md.
No test spends Codex quota or opens ssh: a fake runner records every command, and the one
CLI test puts an ssh shim that exits 255 first on PATH. HEADROOM_LOG always points at tmp_path.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import codex_failover as cf  # noqa: E402

NOW = 1_762_335_600.0  # 2025-11-05T09:40:00Z, fixed so records are comparable
HEAD = "a" * 40
# Seen live on the Mini, 5 Nov 2026: `codex exec` with an empty CODEX_HOME.
SEEN_401 = ("ERROR: unexpected status 401 Unauthorized: Missing bearer or basic authentication "
            "in header, url: https://api.openai.com/v1/responses, cf-ray: x, request id: req_x\n")
CREDITS = "ERROR: Your workspace is out of credits\n"
QUOTA = "You've hit your usage limit · resets 11am\n"


def _auth(tmp_path, mode="chatgpt", key=None):
    home = tmp_path / "codex-home"
    home.mkdir(exist_ok=True)
    (home / "auth.json").write_text(json.dumps({"auth_mode": mode, "OPENAI_API_KEY": key}))
    return home


class FakeRun:
    """Records every argv; answers by matching the first rule whose needle is in the command."""

    def __init__(self, rules):
        self.rules, self.calls, self.stdins = rules, [], []

    def __call__(self, argv, stdin=None, cwd=None, timeout=None):
        self.calls.append(list(argv))
        self.stdins.append(stdin)
        joined = " ".join(argv)
        for needle, result in self.rules:
            if (argv[0] == "ssh") if needle == "ssh" else (needle in joined and argv[0] != "ssh"):
                return result(argv) if callable(result) else result
        return (0, b"", b"")


def _local_codex(transcript, last):
    def answer(argv):
        Path(argv[argv.index("--output-last-message") + 1]).write_text(last)
        return (0, transcript.encode(), b"")
    return answer


def _rules(local, remote_transcript="VERDICT: PASS\n", remote_last="VERDICT: PASS", head=HEAD):
    # ssh first: its remote command strings also contain "rev-parse HEAD" and "codex exec".
    return [
        ("ssh", lambda argv: _ssh(argv, remote_transcript, remote_last, head)),
        ("rev-parse HEAD", (0, (head + "\n").encode(), b"")),
        ("bundle create", (0, b"BUNDLE", b"")),
        ("codex exec --skip-git-repo-check", local),
    ]


_SEQ = [0]


def _ssh(argv, transcript, last, head):
    cmd = argv[-1]
    if "mktemp -d" in cmd:
        _SEQ[0] += 1
        return (0, f"agent-work/codex-failover/RA-8191-{head[:12]}-Ab{_SEQ[0]:04d}\n".encode(), b"")
    if "rev-parse" in cmd:
        return (0, (head + "\n").encode(), b"")
    if "codex exec" in cmd:
        return (0, transcript.encode(), b"")
    if "last.md" in cmd and cmd.startswith("cat"):
        return (0, last.encode(), b"")
    return (0, b"", b"")


def _review(tmp_path, monkeypatch, run, home):
    monkeypatch.setenv("CODEX_HOME", str(home))
    log = tmp_path / "h.jsonl"
    monkeypatch.setenv("HEADROOM_LOG", str(log))
    brief = tmp_path / "brief.md"
    brief.write_text("Review the change.\n")
    out = tmp_path / "out.txt"
    rc, summary = cf.review(brief=brief, out=out, repo=tmp_path, job="RA-8191", run=run, now=NOW)
    rows = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    return rc, summary, rows, out


# ---- detectors (W1: tell a dead login apart from every other failure) ----------------

def test_detect_missing_auth_file_is_auth_failed(tmp_path):
    assert cf.auth_file_state(tmp_path / "nowhere") == "missing"
    assert cf.detect("", "", "missing", NOW)["status"] == "auth_failed"


def test_detect_auth_file_is_never_opened(tmp_path, monkeypatch):
    # Review r1 P1: the pre-check must not pull token values into this process. It stats only.
    home = _auth(tmp_path)
    (home / "auth.json").write_text('{"auth_mode": "chatgpt", "tokens": {"access_token": "SENTINEL"}}')

    def boom(*a, **k):
        raise AssertionError("auth.json was opened")
    import builtins
    import io
    for mod, name in [(builtins, "open"), (io, "open"), (os, "open"), (Path, "open"),
                      (Path, "read_text"), (Path, "read_bytes"), (json, "loads"), (json, "load")]:
        monkeypatch.setattr(mod, name, boom)
    assert cf.auth_file_state(home) == "ok"


def test_detect_unreadable_auth_file(tmp_path):
    home = _auth(tmp_path)
    (home / "auth.json").chmod(0)
    try:
        assert cf.auth_file_state(home) == "unreadable"
        assert cf.detect("", "", "unreadable", NOW)["status"] == "auth_failed"
    finally:
        (home / "auth.json").chmod(0o600)


@pytest.mark.parametrize("text,pid", [(SEEN_401, "codex.unauthorized"), (CREDITS, "codex.workspace_credits")])
def test_detect_auth_lines_with_no_final_message(text, pid):
    hit = cf.detect("Reconnecting... 5/5\n" + text, "", "ok", NOW)
    assert hit == {"status": "auth_failed", "pattern_id": pid}


def test_detect_final_message_wins_over_quoted_auth_line():
    # W1: a reviewer that quotes the 401 line still authenticated, or it could not answer.
    assert cf.detect(SEEN_401 + CREDITS, "VERDICT: PASS", "ok", NOW)["status"] == "ok"


def test_detect_quota_is_not_auth_failure():
    # W4: quota is a cooling hold for the picker, not a dead login; no failover.
    assert cf.detect(QUOTA, "", "ok", NOW)["status"] == "failed"


def test_detect_mid_sentence_401_does_not_fire():
    assert cf.detect("the log said unexpected status 401 Unauthorized once\n", "", "ok", NOW)["status"] == "failed"


# ---- failover (W2: the review still happens; W3: the picker learns Mini is down) -----

def test_failover_healthy_mini_never_touches_ssh(tmp_path, monkeypatch):
    run = FakeRun(_rules(_local_codex("ok\n", "VERDICT: PASS")))
    rc, summary, rows, out = _review(tmp_path, monkeypatch, run, _auth(tmp_path))
    assert rc == cf.EXIT_OK and summary["lane"] == "mini" and rows == []
    assert not any(c[0] == "ssh" for c in run.calls)


def test_failover_ssh_never_inherits_caller_stdin(tmp_path, monkeypatch):
    run = FakeRun(_rules(_local_codex(SEEN_401, "")))
    _review(tmp_path, monkeypatch, run, _auth(tmp_path))
    ssh_stdins = [s for c, s in zip(run.calls, run.stdins) if c[0] == "ssh"]
    assert ssh_stdins and all(isinstance(s, bytes) for s in ssh_stdins)
    assert b"Review the change.\n" in ssh_stdins  # the same brief, byte for byte


def test_failover_remote_dir_is_fresh_per_attempt(tmp_path, monkeypatch):
    # Review r1 P1: a reused folder let a stale last.md turn a 401 into a pass.
    run = FakeRun(_rules(_local_codex(SEEN_401, "")))
    for _ in range(2):  # same job, same HEAD, same second
        cf.run_remote(tmp_path, HEAD, b"brief", "RA-8191", run, NOW)
    codex = [c[-1] for c in run.calls if c[0] == "ssh" and "codex exec" in c[-1]]
    assert len(codex) == 2 and codex[0] != codex[1]
    assert all("test ! -e ../last.md" in c for c in codex)
    staged = [c[-1] for c in run.calls if c[0] == "ssh" and "head.bundle" in c[-1] and "mktemp" in c[-1]]
    assert len(staged) == 2


def test_failover_bad_remote_dir_is_unavailable(tmp_path, monkeypatch):
    rules = _rules(_local_codex(SEEN_401, ""))
    rules[0] = ("ssh", lambda argv: (0, b"/etc\n", b"") if "mktemp" in argv[-1] else _ssh(argv, "x", "x", HEAD))
    rc, summary, rows, _ = _review(tmp_path, monkeypatch, FakeRun(rules), _auth(tmp_path))
    assert rc == cf.EXIT_FAILOVER_UNAVAILABLE and summary["macbook"] == "stage_failed"


def test_failover_non_auth_failure_does_not_fail_over(tmp_path, monkeypatch):
    run = FakeRun(_rules(_local_codex(QUOTA, "")))
    rc, summary, rows, _ = _review(tmp_path, monkeypatch, run, _auth(tmp_path))
    assert rc == cf.EXIT_REVIEW_FAILED and summary["mini"] == "failed" and rows == []
    assert not any(c[0] == "ssh" for c in run.calls)


def test_failover_mini_401_runs_same_brief_on_macbook_same_head(tmp_path, monkeypatch):
    run = FakeRun(_rules(_local_codex(SEEN_401, "")))
    rc, summary, rows, out = _review(tmp_path, monkeypatch, run, _auth(tmp_path))
    assert rc == cf.EXIT_OK and summary["lane"] == "macbook" and summary["head"] == HEAD
    assert [(r["machine"], r["provider"], r["event"], r["job"]) for r in rows] == [
        ("mini", "codex", "auth_expired", "RA-8191")]
    assert out.read_text() == "VERDICT: PASS\n"
    assert Path(str(out) + ".last.md").read_text() == "VERDICT: PASS"
    ssh = [c[-1] for c in run.calls if c[0] == "ssh"]
    assert all(c[:3] == ["ssh", "-o", "BatchMode=yes"] for c in run.calls if c[0] == "ssh")
    assert any("cat > " in s and "brief.md" in s for s in ssh)
    assert any(HEAD in s and "checkout" in s for s in ssh)


def test_failover_missing_auth_file_skips_local_codex(tmp_path, monkeypatch):
    run = FakeRun(_rules(_local_codex("ok\n", "VERDICT: PASS")))
    rc, summary, rows, _ = _review(tmp_path, monkeypatch, run, tmp_path / "empty")
    assert rc == cf.EXIT_OK and summary["mini"] == "auth_failed" and summary["lane"] == "macbook"
    assert not any("--output-last-message" in c for c in run.calls if c[0] == "codex")
    assert rows[0]["pattern_id"] == "codex.auth_file"


def test_failover_head_mismatch_is_unavailable(tmp_path, monkeypatch):
    rules = _rules(_local_codex(SEEN_401, ""))
    rules[0] = ("ssh", lambda argv: _ssh(argv, "VERDICT: PASS\n", "VERDICT: PASS", "b" * 40))
    run = FakeRun(rules)
    rc, summary, rows, _ = _review(tmp_path, monkeypatch, run, _auth(tmp_path))
    assert rc == cf.EXIT_FAILOVER_UNAVAILABLE and summary["macbook"] == "head_mismatch"
    assert not any("codex exec" in c[-1] for c in run.calls if c[0] == "ssh")
    assert rows[0]["machine"] == "mini"  # the Mini event is still recorded


def test_failover_ssh_down_is_unavailable(tmp_path, monkeypatch):
    rules = _rules(_local_codex(SEEN_401, ""))
    rules[0] = ("ssh", (255, b"", b"ssh: connect to host macbook: Operation timed out"))
    rc, summary, rows, _ = _review(tmp_path, monkeypatch, FakeRun(rules), _auth(tmp_path))
    assert rc == cf.EXIT_FAILOVER_UNAVAILABLE and summary["macbook"] == "transport_failed"
    assert len(rows) == 1


def test_failover_macbook_also_auth_failed_records_both(tmp_path, monkeypatch):
    run = FakeRun(_rules(_local_codex(SEEN_401, ""), remote_transcript=SEEN_401, remote_last=""))
    rc, summary, rows, _ = _review(tmp_path, monkeypatch, run, _auth(tmp_path))
    assert rc == cf.EXIT_BOTH_DOWN
    assert [r["machine"] for r in rows] == ["mini", "macbook"]


def test_failover_headroom_write_failure_still_fails_over(tmp_path, monkeypatch):
    run = FakeRun(_rules(_local_codex(SEEN_401, "")))
    monkeypatch.setenv("CODEX_HOME", str(_auth(tmp_path)))
    monkeypatch.setenv("HEADROOM_LOG", str(tmp_path / "no" / "such" / "h.jsonl"))
    brief = tmp_path / "brief.md"
    brief.write_text("x")
    rc, summary = cf.review(brief=brief, out=tmp_path / "o", repo=tmp_path, job="RA-8191", run=run, now=NOW)
    assert rc == cf.EXIT_OK and summary["headroom"]["mini"].startswith("failed")


def test_failover_job_name_is_sanitised_in_remote_path(tmp_path, monkeypatch):
    run = FakeRun(_rules(_local_codex(SEEN_401, "")))
    monkeypatch.setenv("CODEX_HOME", str(_auth(tmp_path)))
    monkeypatch.setenv("HEADROOM_LOG", str(tmp_path / "h.jsonl"))
    brief = tmp_path / "brief.md"
    brief.write_text("x")
    cf.review(brief=brief, out=tmp_path / "o", repo=tmp_path, job="x; rm -rf ~", run=run, now=NOW)
    assert not any("rm -rf" in c[-1] for c in run.calls if c[0] == "ssh")


# ---- never sign in or out (W5) --------------------------------------------------------

@pytest.mark.parametrize("argv", [["codex", "login"], ["codex", "logout"],
                                  ["ssh", "-o", "BatchMode=yes", "macbook", "codex login --with-api-key"],
                                  ["ssh", "macbook", "cd x && codex  logout"]])
def test_login_guard_refuses(argv):
    with pytest.raises(cf.ForbiddenCommand):
        cf.guard(argv)


def test_login_never_issued_on_any_path(tmp_path, monkeypatch):
    for local, remote in [(SEEN_401, "VERDICT: PASS\n"), (SEEN_401, SEEN_401), ("ok\n", "x")]:
        run = FakeRun(_rules(_local_codex(local, "" if local == SEEN_401 else "ok"), remote_transcript=remote,
                             remote_last="" if remote == SEEN_401 else "ok"))
        _review(tmp_path, monkeypatch, run, _auth(tmp_path))
        for c in run.calls:
            assert not any(w in ("login", "logout") for w in " ".join(c).split())


def test_login_guard_is_applied_by_default_runner(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("subprocess reached"))
    with pytest.raises(cf.ForbiddenCommand):
        cf.subprocess_run(["codex", "logout"])


def test_failover_cli_detect_subcommand(tmp_path):
    t = tmp_path / "t.txt"
    t.write_text(SEEN_401)
    env = {**os.environ, "CODEX_HOME": str(_auth(tmp_path))}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "codex_failover.py"), "detect", "--transcript", str(t)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == cf.EXIT_AUTH_FAILED
    assert json.loads(r.stdout)["status"] == "auth_failed"
