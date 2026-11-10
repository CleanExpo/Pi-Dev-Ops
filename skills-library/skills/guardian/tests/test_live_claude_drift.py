#!/usr/bin/env python3
"""Tests for scripts/live_claude_drift.py. Real git: a bare origin, a pusher clone and a target clone,
all in temp dirs. The board, host name and notifier are env seams. Run: python3 test_live_claude_drift.py"""
import json, os, shutil, subprocess, sys, tempfile, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "scripts", "live_claude_drift.py")
ROW = "W-DRIFT-LIVE-CLAUDE-testhost"
BACKUP_ROW = "W-MEMORY-BACKUP-testhost"
DAY = 86400


def git(cwd, *args, when=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid", GIT_CONFIG_NOSYSTEM="1")
    if when is not None:
        stamp = "@%d +0000" % int(when)
        env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    return subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True, env=env).stdout


def commit(repo, name, when):
    open(os.path.join(repo, name), "w").write(name + "\n")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", name, when=when)


def setup(tmp, behind=0, ages=(), ahead=0):
    """target is `behind` commits behind origin/main (committer dates now-ages[i]) and `ahead` local commits ahead."""
    origin, pusher, target = (os.path.join(tmp, n) for n in ("origin.git", "pusher", "target"))
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True)
    subprocess.run(["git", "clone", "-q", origin, pusher], check=True, capture_output=True)
    git(pusher, "checkout", "-q", "-b", "main")
    commit(pusher, "base", time.time() - 30 * DAY)
    git(pusher, "push", "-q", "origin", "main")
    subprocess.run(["git", "clone", "-q", origin, target], check=True, capture_output=True)
    for i in range(behind):
        commit(pusher, "up%d" % i, time.time() - ages[i])
    if behind:
        git(pusher, "push", "-q", "origin", "main")
    for i in range(ahead):
        commit(target, "local%d" % i, time.time())
    ops = os.path.join(tmp, "ops"); os.makedirs(ops)
    json.dump({"jobs": []}, open(os.path.join(ops, "jobs.json"), "w"))
    return target, ops


def run(tmp, target, ops, status=None, installed=False):
    """status: text for the backup status file (None = no file). installed: the backup LaunchAgent plist exists."""
    st, plist = os.path.join(tmp, "backup.status"), os.path.join(tmp, "backup.plist")
    if status is not None:
        open(st, "w").write(status)
    if installed:
        open(plist, "w").write("<plist/>")
    note = os.path.join(tmp, "notified.txt")
    stub = os.path.join(tmp, "notify.sh")
    open(stub, "w").write('#!/bin/sh\necho "$@" >> "%s"\n' % note)
    os.chmod(stub, 0o755)
    env = dict(os.environ, LIVE_DRIFT_REPO=target, LIVE_DRIFT_OPS=ops, LIVE_DRIFT_HOST="testhost",
               LIVE_DRIFT_NOTIFY=stub, LIVE_DRIFT_BACKUP_STATUS=st, LIVE_DRIFT_BACKUP_PLIST=plist,
               PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr, (open(note).read() if os.path.exists(note) else "")


def rows(ops):
    return {j["id"]: j for j in json.load(open(os.path.join(ops, "jobs.json")))["jobs"]}


def test_behind_with_old_commits_is_fail_naming_counts(tmp):
    target, ops = setup(tmp, behind=3, ages=(3 * DAY, 2 * DAY, 2 * DAY), ahead=2)
    rc, out, _ = run(tmp, target, ops)
    assert rc == 1, (rc, out)
    j = rows(ops)[ROW]
    assert j["status"] == "open" and j["check_state"] == "FAIL", j
    assert "3 commits behind" in j["title"] and "2 ahead" in j["title"], j["title"]
    assert "72h" in j["title"] or "71h" in j["title"], j["title"]   # oldest missing commit is 3 days old
    assert j["behind"] == 3 and j["ahead"] == 2, j


def test_refresh_updates_an_existing_fail_row_without_duplicating(tmp):
    target, ops = setup(tmp, behind=2, ages=(3 * DAY, 3 * DAY))
    run(tmp, target, ops)
    d = json.load(open(os.path.join(ops, "jobs.json")))
    d["jobs"][0]["title"] = "stale"
    json.dump(d, open(os.path.join(ops, "jobs.json"), "w"))
    rc, out, _ = run(tmp, target, ops)
    assert rc == 1, (rc, out)
    jobs = json.load(open(os.path.join(ops, "jobs.json")))["jobs"]
    assert len(jobs) == 1 and "2 commits behind" in jobs[0]["title"], jobs


def test_behind_with_fresh_commits_is_ok(tmp):
    target, ops = setup(tmp, behind=2, ages=(3600, 1800))
    rc, out, note = run(tmp, target, ops)
    assert rc == 0, (rc, out)
    assert ROW not in rows(ops) and not note, (rows(ops), note)


def test_even_is_ok_and_marks_fail_row_done(tmp):
    target, ops = setup(tmp)
    json.dump({"jobs": [{"id": ROW, "status": "open", "check_state": "FAIL", "title": "ALERT: old"}]},
              open(os.path.join(ops, "jobs.json"), "w"))
    rc, out, _ = run(tmp, target, ops)
    assert rc == 0, (rc, out)
    j = rows(ops)[ROW]
    assert j["status"] == "done" and j["check_state"] == "OK", j


def test_ahead_only_is_ok_and_quiet(tmp):
    target, ops = setup(tmp, ahead=18)   # the live checkout after the 06/11/2026 resync: ahead 18, behind 0
    rc, out, note = run(tmp, target, ops)
    assert rc == 0, (rc, out)
    assert ROW not in rows(ops) and not note, (rows(ops), note)


def test_fetch_failure_is_unknown_and_keeps_fail_row(tmp):
    target, ops = setup(tmp, behind=1, ages=(3 * DAY,))
    run(tmp, target, ops)
    assert rows(ops)[ROW]["check_state"] == "FAIL"
    git(target, "remote", "set-url", "origin", os.path.join(tmp, "gone.git"))
    rc, out, _ = run(tmp, target, ops)
    assert rc == 2 and "fetch" in out, (rc, out)
    j = rows(ops)[ROW]
    assert j["status"] == "open" and j["check_state"] == "FAIL" and "1 commits behind" in j["title"], j
    assert j.get("unknown_since"), j


def test_not_a_git_repo_is_unknown(tmp):
    _, ops = setup(tmp)
    plain = os.path.join(tmp, "plain"); os.makedirs(plain)
    rc, out, _ = run(tmp, plain, ops)
    assert rc == 2 and "not a git repo" in out, (rc, out)
    j = rows(ops)[ROW]
    assert j["check_state"] == "UNKNOWN" and j["status"] == "open", j


def test_board_missing_notifies_and_exits_nonzero(tmp):
    target, ops = setup(tmp, behind=4, ages=(5 * DAY,) * 4)
    shutil.rmtree(ops)
    rc, out, note = run(tmp, target, ops)
    assert rc != 0 and "board" in out, (rc, out)
    assert "4 commits behind" in note, note
    assert not os.path.exists(ops)


def ts(age_s):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - age_s))


def test_backup_fail_status_fires(tmp):
    target, ops = setup(tmp)
    rc, out, _ = run(tmp, target, ops, status="FAIL %s exit=3 ERROR: main rejected the update\n" % ts(3600), installed=True)
    assert rc == 1, (rc, out)
    j = rows(ops)[BACKUP_ROW]
    assert j["status"] == "open" and j["check_state"] == "FAIL" and "exit=3" in j["title"], j
    assert ROW not in rows(ops)   # the checkout itself is even: drift row untouched


def test_backup_stale_ok_fires(tmp):
    target, ops = setup(tmp)
    rc, out, _ = run(tmp, target, ops, status="OK %s\n" % ts(40 * 3600), installed=True)
    assert rc == 1, (rc, out)
    j = rows(ops)[BACKUP_ROW]
    assert j["check_state"] == "FAIL" and "40h" in j["title"], j


def test_backup_fresh_ok_is_quiet_and_marks_row_done(tmp):
    target, ops = setup(tmp)
    json.dump({"jobs": [{"id": BACKUP_ROW, "status": "open", "check_state": "FAIL", "title": "ALERT: old"}]},
              open(os.path.join(ops, "jobs.json"), "w"))
    rc, out, note = run(tmp, target, ops, status="OK %s\n" % ts(2 * 3600), installed=True)
    assert rc == 0 and not note, (rc, out, note)
    j = rows(ops)[BACKUP_ROW]
    assert j["status"] == "done" and j["check_state"] == "OK", j


def test_backup_status_missing_after_install_fires(tmp):
    target, ops = setup(tmp)
    rc, out, _ = run(tmp, target, ops, installed=True)
    assert rc == 1, (rc, out)
    assert "missing" in rows(ops)[BACKUP_ROW]["title"], rows(ops)


def test_backup_not_installed_and_no_status_is_quiet(tmp):
    target, ops = setup(tmp)
    rc, out, note = run(tmp, target, ops)
    assert rc == 0 and BACKUP_ROW not in rows(ops) and not note, (rc, out, rows(ops))


def test_backup_malformed_lines_are_unknown_not_healthy(tmp):
    # review P2 on 9fcb1f69: "OK <fresh ts> garbage" read as a healthy backup
    for line in ("OK %s garbage\n" % ts(60), "FAIL %s no exit code\n" % ts(60), "FAIL %s exit=x err\n" % ts(60)):
        target, ops = setup(os.path.join(tmp, str(abs(hash(line)))))
        rc, out, _ = run(tmp, target, ops, status=line, installed=True)
        assert rc == 2, (line, rc, out)
        assert rows(ops)[BACKUP_ROW]["check_state"] == "UNKNOWN", (line, rows(ops))


def test_backup_unreadable_status_is_unknown(tmp):
    target, ops = setup(tmp)
    rc, out, _ = run(tmp, target, ops, status="garbage\n", installed=True)
    assert rc == 2, (rc, out)
    assert rows(ops)[BACKUP_ROW]["check_state"] == "UNKNOWN", rows(ops)


def test_ahead_only_with_fresh_backup_is_quiet(tmp):
    target, ops = setup(tmp, ahead=18)
    rc, out, note = run(tmp, target, ops, status="OK %s\n" % ts(3600), installed=True)
    assert rc == 0 and not note and not rows(ops), (rc, out, note, rows(ops))


def test_board_missing_with_backup_fail_notifies(tmp):
    target, ops = setup(tmp)
    shutil.rmtree(ops)
    rc, out, note = run(tmp, target, ops, status="FAIL %s exit=1 ERROR: x\n" % ts(60), installed=True)
    assert rc == 1 and "exit=1" in note, (rc, out, note)


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        tmp = tempfile.mkdtemp(prefix="live-drift-test-")
        try:
            fn(tmp); print("PASS " + name)
        except BaseException:  # noqa: BLE001
            failed += 1; print("FAIL %s\n%s" % (name, traceback.format_exc()))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
