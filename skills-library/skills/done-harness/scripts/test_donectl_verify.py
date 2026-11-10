"""Controls for the 02/10/2026 verify hardening (3-vendor audit: Codex, Gemini, Claude).

Each test builds a real throwaway git repository, opens and locks a contract through donectl itself,
and asserts one behaviour. Plain Python, as scripts/run-estate-checks.py runs it:
    python3 skills/done-harness/scripts/test_donectl_verify.py      (exit 1 on any failure)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import donectl  # noqa: E402


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True)


def make_repo(tmp):
    os.environ["HOME"] = os.path.join(tmp, "home")
    r = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(r, "sub"))
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "t")
    open(os.path.join(r, "a.txt"), "w").write("a\n")
    open(os.path.join(r, "sub", "b.txt"), "w").write("b\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "init")
    os.chdir(r)
    out, rc = donectl.init()
    assert rc == 0, out
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "done tree")
    return r


def locked(criteria):
    out, rc = donectl.start("prove the controls")
    assert rc == 0, out
    path = out["contract_path"]
    c = json.load(open(path))
    c["criteria"] = criteria
    json.dump(c, open(path, "w"), indent=2)
    return donectl.lock()


def crit(cid, recipe, **kw):
    return {"id": cid, "text": f"{cid} holds", "recipe": recipe, "required": True, **kw}


def test_full_output_is_logged_and_the_early_line_survives(repo):
    locked([crit("C1", "python3 -c \"print('SURVIVED idx=59'); print('x' * 1100000); raise SystemExit(1)\"")])
    out, rc = donectl.verify()
    m = out["matrix"][0]
    assert rc == 1 and out["verification_status"] == "FAIL"
    assert "SURVIVED idx=59" not in m["output_tail"]  # control: the tail alone still loses it
    assert "SURVIVED idx=59" in open(m["output_log"]).read()  # past the old 1 MiB cut too
    assert not m["output_log"].startswith(repo)  # the log never dirties the tree


def test_ids_that_sanitise_alike_get_separate_logs(repo):
    locked([crit("C/1", "echo one"), crit("C?1", "echo two")])
    out, _ = donectl.verify()
    logs = [m["output_log"] for m in out["matrix"]]
    assert len(set(logs)) == 2 and "one" in open(logs[0]).read() and "two" in open(logs[1]).read()


def test_a_dirty_tree_is_refused_before_any_recipe_runs(repo):
    locked([crit("C1", "touch ran.flag")])
    open(os.path.join(repo, "a.txt"), "w").write("changed\n")
    out, rc = donectl.verify()
    assert rc == 1 and out["verification_status"] == "BLOCKED" and "nothing was run" in out["blockers"][0]
    assert not os.path.exists(os.path.join(repo, "ran.flag"))


def test_dirt_outside_the_cwd_is_seen_from_a_subdirectory(repo):
    locked([crit("C1", "true")])
    open(os.path.join(repo, "a.txt"), "w").write("changed\n")
    os.chdir(os.path.join(repo, "sub"))
    out, _ = donectl.verify()
    assert out["verification_status"] == "BLOCKED"


def test_an_unmeasurable_tree_is_never_clean(repo):
    assert donectl._product_dirt({"dirty_count_product": None, "dirty_count": None}) == 1
    assert donectl._product_dirt({"dirty_count_product": 0, "dirty_count": 3}) == 0


def test_a_tree_that_moves_mid_run_cannot_pass(repo):
    locked([crit("C1", "echo moved > a.txt")])
    out, rc = donectl.verify()
    assert rc == 1 and out["verification_status"] == "BLOCKED"
    assert any("moved while recipes ran" in b for b in out["blockers"])


def test_a_clean_run_passes(repo):
    locked([crit("C1", "true"), crit("C2", "test -f a.txt")])
    out, rc = donectl.verify()
    assert rc == 0 and out["verification_status"] == "PASS", out


def test_a_contract_timeout_is_honoured(repo):
    locked([crit("C1", "sleep 5", timeout=1)])
    out, _ = donectl.verify()
    assert out["matrix"][0]["exit_code"] == 124 and out["matrix"][0]["timeout_s"] == 1


def test_lock_refuses_a_bad_timeout(repo):
    for bad in (0, -1, "900", 1.5, True, 999999, None):
        work = os.path.join(repo, ".claude", "done")
        shutil.rmtree(os.path.join(work, "work"), ignore_errors=True)
        open(os.path.join(work, "ACTIVE.json"), "w").write("{}")
        out, rc = locked([crit("C1", "true", timeout=bad)])
        assert rc == 2 and out["criteria_bad_timeout"] == ["C1"], (bad, out)


def test_a_legacy_lock_with_a_bad_timeout_fails_closed(repo):
    """Review P1-LEGACY-TIMEOUT-UNBOUNDED: an older donectl locked timeout:null; it must never
    reach subprocess as None (no limit at all)."""
    locked([crit("C1", "true")])
    st = donectl.status()
    wdir = os.path.join(repo, ".claude", "done", "work", st["work_id"])
    c = json.load(open(os.path.join(wdir, "contract.json")))
    c["criteria"][0]["timeout"] = None
    json.dump(c, open(os.path.join(wdir, "contract.json"), "w"), indent=2)
    lk = json.load(open(os.path.join(wdir, "lock.json")))
    lk["contract_digest"] = donectl.digest(c)  # as the old lock() would have written it
    json.dump(lk, open(os.path.join(wdir, "lock.json"), "w"), indent=2)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "legacy lock")
    out, rc = donectl.verify()
    assert rc != 0 and out["verification_status"] == "FAIL", out
    assert out["matrix"][0]["exit_code"] != 0 and "timeout" in out["matrix"][0]["reason"]


def test_lock_refuses_duplicate_ids(repo):
    out, rc = locked([crit("C1", "true"), crit("C1", "true")])
    assert rc == 2 and "unique" in out["error"]


def test_a_subset_is_partial_and_never_a_pass(repo):
    locked([crit("C1", "true"), crit("C2", "false")])
    out, rc = donectl.verify(only=["C1"])
    assert rc == 0 and out["verification_status"] == "PARTIAL" and out["subset_result"] == "PROVEN"
    assert donectl.status()["verification_status"] != "PASS"
    out, rc = donectl.verify(only=["nope"])
    assert rc == 2


def test_a_failing_partial_withdraws_an_earlier_pass(repo):
    """Review P1-PARTIAL-FAILURE-REPLAYS-PASS: newer failing evidence must not leave a PASS standing."""
    os.makedirs(os.environ["HOME"], exist_ok=True)
    flag = os.path.join(os.environ["HOME"], "c1.ok")
    open(flag, "w").close()
    locked([crit("C1", "test -f '%s'" % flag)])
    out, rc = donectl.verify()
    assert rc == 0 and donectl.status()["verification_status"] == "PASS"
    os.remove(flag)
    out, rc = donectl.verify(only=["C1"])
    assert rc == 1 and out["subset_result"] == "FAILED"
    assert donectl.status()["verification_status"] != "PASS"
    assert donectl.resume()[0].get("replayable") is not True


def test_a_refused_verify_withdraws_an_earlier_pass(repo):
    """Review P1-PRECHECK-REPLAYS-PASS: cleaning the tree after a refusal must not restore an old PASS."""
    locked([crit("C1", "true")])
    assert donectl.verify()[1] == 0
    for only in (None, ["C1"]):
        open(os.path.join(repo, "a.txt"), "w").write("changed\n")
        out, rc = donectl.verify(only=only)
        assert out["verification_status"] == "BLOCKED", out
        git(repo, "checkout", "--", "a.txt")
        assert donectl.status()["verification_status"] != "PASS"
        assert donectl.resume()[0].get("replayable") is not True
    assert donectl.verify()[1] == 0 and donectl.status()["verification_status"] == "PASS"


def test_a_second_verify_cannot_run_while_one_holds_the_lock(repo):
    """Review P1-OVERLAPPING-RUN-RESTORES-REVOKED-PROOF: verifies of one work item are serialised."""
    locked([crit("C1", "true")])
    held = donectl._verify_lock(donectl.status()["work_id"])
    assert held not in (None, True)
    out, rc = donectl.verify(only=["C1"])
    assert rc == 1 and "another verify" in out["blockers"][0]
    held.close()
    assert donectl.verify()[1] == 0


def test_a_contract_changed_then_restored_needs_a_fresh_verify(repo):
    """Review P1-STALE-CONTRACT-PROOF-REPLAY."""
    locked([crit("C1", "true")])
    assert donectl.verify()[1] == 0
    st = donectl.status()
    path = os.path.join(repo, ".claude", "done", "work", st["work_id"], "contract.json")
    original = open(path).read()
    c = json.loads(original)
    c["criteria"][0]["text"] = "changed after lock"
    json.dump(c, open(path, "w"))
    assert donectl.resume()[0].get("replayable") is not True
    assert donectl.verify()[0]["verification_status"] == "BLOCKED"
    open(path, "w").write(original)
    assert donectl.status()["verification_status"] != "PASS"
    assert donectl.resume()[0].get("replayable") is not True


def test_a_dirty_refresh_withdraws_the_proof(repo):
    """Review P1-REFRESH-DIRT-RETAINS-PROOF."""
    locked([crit("C1", "true")])
    assert donectl.verify()[1] == 0
    open(os.path.join(repo, "a.txt"), "w").write("changed\n")
    donectl.refresh()
    git(repo, "checkout", "--", "a.txt")
    assert donectl.status()["verification_status"] != "PASS"
    assert donectl.resume()[0].get("replayable") is not True


def test_a_later_run_never_overwrites_an_earlier_proof_log(repo):
    """Review P1-PARTIAL-OVERWRITES-FULL-PROOF-LOG: logs are content-addressed."""
    os.makedirs(os.environ["HOME"], exist_ok=True)
    src = os.path.join(os.environ["HOME"], "out.txt")
    open(src, "w").write("EARLY_FULL_PROOF" + "x" * 6000)
    locked([crit("C1", "cat '%s'" % src)])
    full = donectl.verify()[0]["matrix"][0]
    open(src, "w").write("second diagnosis")
    assert donectl.verify(only=["C1"])[1] == 0
    kept = open(full["output_log"]).read()
    assert "EARLY_FULL_PROOF" in kept
    assert donectl.sha256_bytes(kept.encode("utf-8")) == full["output_digest"]


def test_refresh_waits_for_a_running_verify(repo):
    locked([crit("C1", "true")])
    held = donectl._verify_lock(donectl.status()["work_id"])
    out, rc = donectl.refresh()
    held.close()
    assert rc == 1 and "running" in out["error"]


def test_status_has_no_default_fallback(repo):
    locked([crit("C1", "true")])
    p = os.path.join(donectl.done_root(donectl.identity()), "ACTIVE.json")
    a = json.load(open(p))
    a["default"] = next(iter(a["by_identity"].values()))
    a["by_identity"] = {}
    json.dump(a, open(p, "w"))
    assert donectl.status()["work_id"] is None


def with_git(fake, fn):
    """Run fn with each git subprocess donectl starts answered by fake(argv); None passes through."""
    real = donectl.subprocess.run

    def run(argv, *a, **kw):
        got = fake(argv) if argv and argv[0] == "git" else None
        return real(argv, *a, **kw) if got is None else got

    donectl.subprocess.run = run
    try:
        return fn()
    finally:
        donectl.subprocess.run = real


def git_times_out(argv):
    raise subprocess.TimeoutExpired(argv, 30)


def test_a_timed_out_git_probe_fails_closed(repo):
    # 12/10/2026, load 17-21: a 30 s timeout read as "not a repository" -> ALLOW.
    d = with_git(git_times_out, lambda: donectl.preflight("Bash", {"command": "rm -rf build"}, repo))
    assert d["decision"] == "DENY" and "UNPROVEN" in d["reason"], d


def test_a_genuine_non_repo_stays_out_of_scope(repo):
    def not_a_repo(argv):
        return subprocess.CompletedProcess(argv, 128, "", "fatal: not a git repository (or any of the parent directories): .git\n")
    d = with_git(not_a_repo, lambda: donectl.preflight("Bash", {"command": "rm -rf build"}, repo))
    assert d["decision"] == "ALLOW" and "out of scope" in d["reason"], d


def test_a_selftest_whose_fixture_fails_is_unproven_not_a_defect(repo):
    def init_times_out(argv):
        if argv[1:2] == ["init"]:
            raise subprocess.TimeoutExpired(argv, 30)
    out, rc = with_git(init_times_out, donectl.selftest)
    assert rc == 1 and out["enforcement"] == "ENFORCEMENT_UNPROVEN", out
    assert out["probe_setup"].startswith("FAILED"), out
    assert not [c for c in out["checks"] if c["ok"] is False], out  # nothing reported as a gate defect


def test_a_recipe_can_expand_systemdrive_without_inheriting_it(repo):
    r"""02/11/2026: a recipe with no SYSTEMDRIVE made the verifier dirty its own repo.

    An npm recipe held %SystemDrive%\ProgramData from the registry, could not expand
    it, and created a directory literally named "%SystemDrive%" in the worktree -- so
    verify refused the next run on a dirty tree and ran nothing. The variable must be
    present, and it must be DERIVED from the allowlisted root rather than taken from
    the caller, or it becomes the eighth way to move a recipe's root of trust.
    """
    if os.name != "nt":
        return  # skipped: the unexpandable registry value is a Windows-only mechanism
    rc, out = donectl._run("echo [%SYSTEMDRIVE%]")
    assert rc == 0, out
    assert "[C:]" in out, "a recipe cannot expand %SYSTEMDRIVE%: " + out

    saved = {k: os.environ.get(k) for k in ("SYSTEMROOT", "SystemRoot", "SYSTEMDRIVE")}
    try:
        os.environ["SYSTEMROOT"] = r"C:\ATTACKER"
        os.environ["SystemRoot"] = r"C:\ATTACKER"
        os.environ["SYSTEMDRIVE"] = "Z:"
        rc, out = donectl._run("echo [%SYSTEMDRIVE%]")
        assert rc == 0, out
        assert "[C:]" in out, "the caller moved SYSTEMDRIVE: " + out
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main():
    tests =[(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    home, cwd, failed = os.environ.get("HOME"), os.getcwd(), 0
    for name, fn in tests:
        tmp = tempfile.mkdtemp(prefix="donectl-test-")
        try:
            fn(make_repo(tmp))
            print(f"PASS {name}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}\n{traceback.format_exc()}")
        finally:
            os.chdir(cwd)
            if home is not None:
                os.environ["HOME"] = home
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
