#!/usr/bin/env python3
"""Tests for jobs_lock: the single shared writer protocol for ops/jobs.json (fcntl.flock on jobs.json.lock,
the same lock pc-board.py takes). Run: python3 test_jobs_lock.py"""
import fcntl, json, os, shutil, stat, subprocess, sys, tempfile, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True


def mkjobs(tmp):
    path = os.path.join(tmp, "jobs.json")
    with open(path, "w") as f:
        json.dump({"jobs": [], "updated": ""}, f)
    return path


def worker(path, tag, n):
    code = (
        "import sys, time; sys.path.insert(0, %r); import jobs_lock\n"
        "def add(i):\n"
        "    def fn(d):\n"
        "        time.sleep(0.002)\n"
        "        d['jobs'].append({'id': '%s-%%d' %% i}); return True\n"
        "    return fn\n"
        "for i in range(%d): jobs_lock.update_jobs(%r, add(i))\n" % (SCRIPTS, tag, n, path))
    return subprocess.Popen([sys.executable, "-B", "-c", code], stderr=subprocess.PIPE, text=True)


def test_update_adds_a_row_and_keeps_file_mode(tmp):
    import jobs_lock
    path = mkjobs(tmp)
    os.chmod(path, 0o644)
    jobs_lock.update_jobs(path, lambda d: d["jobs"].append({"id": "W-X"}) or True)
    assert [j["id"] for j in json.load(open(path))["jobs"]] == ["W-X"]
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o644
    assert not [n for n in os.listdir(tmp) if n.startswith("tmp")], os.listdir(tmp)


def test_unchanged_mutation_does_not_rewrite(tmp):
    import jobs_lock
    path = mkjobs(tmp)
    before = os.stat(path).st_ino
    jobs_lock.update_jobs(path, lambda d: False)
    assert os.stat(path).st_ino == before


def test_a_failing_mutation_leaves_the_file_untouched(tmp):
    import jobs_lock
    path = mkjobs(tmp)
    raw = open(path).read()

    def boom(d):
        d["jobs"].append({"id": "half"})
        raise RuntimeError("boom")
    try:
        jobs_lock.update_jobs(path, boom)
        raise AssertionError("should have raised")
    except RuntimeError:
        pass
    assert open(path).read() == raw


def test_corrupt_jobs_json_raises_and_is_not_overwritten(tmp):
    import jobs_lock
    path = os.path.join(tmp, "jobs.json")
    open(path, "w").write("{not json")
    try:
        jobs_lock.update_jobs(path, lambda d: True)
        raise AssertionError("should have raised")
    except ValueError:
        pass
    assert open(path).read() == "{not json"


def test_update_waits_for_a_holder_of_the_pc_board_lock(tmp):
    """pc-board.py: open(jobs.json.lock) + fcntl.flock(LOCK_EX). A writer must not get past it."""
    import jobs_lock
    path = mkjobs(tmp)
    with open(path + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        t0 = time.time()
        try:
            jobs_lock.update_jobs(path, lambda d: d["jobs"].append({"id": "x"}) or True, timeout=0.5)
            raise AssertionError("writer got past a held lock")
        except TimeoutError:
            pass
        assert time.time() - t0 >= 0.4
    assert json.load(open(path))["jobs"] == []
    jobs_lock.update_jobs(path, lambda d: d["jobs"].append({"id": "x"}) or True, timeout=2)
    assert json.load(open(path))["jobs"] == [{"id": "x"}]


def test_two_concurrent_writers_lose_no_rows(tmp):
    path = mkjobs(tmp)
    procs = [worker(path, "a", 50), worker(path, "b", 50)]
    errs = [p.communicate()[1] for p in procs]
    assert all(p.returncode == 0 for p in procs), errs
    ids = {j["id"] for j in json.load(open(path))["jobs"]}
    want = {"a-%d" % i for i in range(50)} | {"b-%d" % i for i in range(50)}
    assert ids == want, "lost %d rows" % len(want - ids)


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        tmp = tempfile.mkdtemp(prefix="jobslock-test-")
        try:
            fn(tmp)
            print("PASS " + name)
        except BaseException:  # noqa: BLE001
            failed += 1
            print("FAIL %s\n%s" % (name, traceback.format_exc()))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
