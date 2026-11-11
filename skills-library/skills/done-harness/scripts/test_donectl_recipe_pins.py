"""Controls for recipe-file pinning (20/10/2026, harness weakness #1).

`lock` used to digest contract.json and nothing else. A recipe such as
`bash .claude/done/work/<id>/checks.sh` names a file under .claude/done, which product-dirt
measurement deliberately excludes, so the builder could rewrite the verifier after the
finish line was agreed and `verify` would still PASS. These tests prove the lock now pins
those bytes, and that every consumer of status (verify, integrity, lock) refuses a change.

Plain Python, the same way test_donectl_verify.py runs:
    python3 skills/done-harness/scripts/test_donectl_recipe_pins.py   (exit 1 on any failure)
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
from test_donectl_verify import git, make_repo  # noqa: E402


def open_contract(criteria_for):
    """start, write criteria built from the work dir, return (work_dir, contract_path)."""
    out, rc = donectl.start("prove recipe pinning")
    assert rc == 0, out
    path = out["contract_path"]
    wdir = os.path.dirname(path)
    c = json.load(open(path))
    c["criteria"] = criteria_for(wdir)
    json.dump(c, open(path, "w"), indent=2)
    return wdir, path


def crit(cid, recipe):
    return {"id": cid, "text": f"{cid} holds", "recipe": recipe, "required": True}


def checks_in_workdir(wdir, body="exit 0\n"):
    script = os.path.join(wdir, "checks.sh")
    open(script, "w").write(body)
    rel = os.path.relpath(script, os.getcwd())
    return [crit("C1", f"sh {rel}")]


def commit_all(repo, msg):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def test_control_untouched_recipe_file_verifies(repo):
    open_contract(checks_in_workdir)
    out, rc = donectl.lock()
    assert rc == 0, out
    commit_all(repo, "contract")
    out, rc = donectl.verify()
    assert rc == 0 and out["verification_status"] == "PASS", out


def test_lock_records_a_pin_for_the_workdir_script(repo):
    wdir, _ = open_contract(checks_in_workdir)
    out, rc = donectl.lock()
    assert rc == 0, out
    lk = json.load(open(os.path.join(wdir, "lock.json")))
    pins = lk.get("recipe_pins")
    assert isinstance(pins, dict) and any(k.endswith("checks.sh") for k in pins), lk


def test_editing_the_verifier_after_lock_is_stale_and_cannot_pass(repo):
    wdir, _ = open_contract(lambda w: checks_in_workdir(w, "exit 1\n"))
    out, rc = donectl.lock()
    assert rc == 0, out
    commit_all(repo, "contract")
    # The builder quietly makes the failing verifier pass. .claude/done is excluded from
    # product dirt, so before pinning nothing saw this.
    open(os.path.join(wdir, "checks.sh"), "w").write("exit 0\n")
    st = donectl.status()
    assert st["contract_status"] == "STALE", st
    assert any("checks.sh" in r for r in st["reasons"]), st
    out, rc = donectl.verify()
    assert rc == 1 and out["verification_status"] != "PASS", out
    integ, irc = donectl.integrity()
    assert irc == 1 and integ["integrity"] == "INVALID", integ


def test_a_file_added_to_the_workdir_after_lock_is_stale(repo):
    wdir, _ = open_contract(checks_in_workdir)
    out, rc = donectl.lock()
    assert rc == 0, out
    # checks.sh may `source` a sibling; a new sibling is a new verifier.
    open(os.path.join(wdir, "lib.sh"), "w").write("true\n")
    assert donectl.status()["contract_status"] == "STALE"


def test_a_named_file_elsewhere_under_the_done_tree_is_pinned(repo):
    shared = os.path.join(repo, ".claude", "done", "lib")
    os.makedirs(shared)
    open(os.path.join(shared, "check.sh"), "w").write("exit 0\n")
    open_contract(lambda w: [crit("C1", "sh .claude/done/lib/check.sh")])
    out, rc = donectl.lock()
    assert rc == 0, out
    open(os.path.join(shared, "check.sh"), "w").write("echo forged; exit 0\n")
    st = donectl.status()
    assert st["contract_status"] == "STALE", st


def test_a_named_but_absent_file_must_stay_absent(repo):
    open_contract(lambda w: [crit("C1", "sh .claude/done/lib/later.sh || true")])
    out, rc = donectl.lock()
    assert rc == 0, out
    os.makedirs(os.path.join(repo, ".claude", "done", "lib"))
    open(os.path.join(repo, ".claude", "done", "lib", "later.sh"), "w").write("exit 0\n")
    assert donectl.status()["contract_status"] == "STALE"


def test_relock_refuses_when_pins_moved(repo):
    wdir, _ = open_contract(checks_in_workdir)
    out, rc = donectl.lock()
    assert rc == 0, out
    open(os.path.join(wdir, "checks.sh"), "w").write("exit 0 # edited\n")
    out, rc = donectl.lock()
    assert rc == 1 and "revise" in out.get("error", ""), out


def test_a_recipe_that_rewrites_its_own_script_mid_run_is_blocked(repo):
    def crits(w):
        script = os.path.join(w, "checks.sh")
        open(script, "w").write("echo '# rewritten' >> \"$0\"\nexit 0\n")
        return [crit("C1", "sh " + os.path.relpath(script, os.getcwd()))]
    open_contract(crits)
    out, rc = donectl.lock()
    assert rc == 0, out
    commit_all(repo, "contract")
    out, rc = donectl.verify()
    assert rc == 1 and out["verification_status"] == "BLOCKED", out


def test_bytecode_caches_do_not_trip_the_pin(repo):
    def crits(w):
        open(os.path.join(w, "helper.py"), "w").write("OK = 0\n")
        open(os.path.join(w, "check.py"), "w").write(
            "import sys; sys.path.insert(0, %r); import helper; raise SystemExit(helper.OK)\n" % w)
        return [crit("C1", "python3 " + os.path.relpath(os.path.join(w, "check.py"), os.getcwd()))]
    wdir, _ = open_contract(crits)
    out, rc = donectl.lock()
    assert rc == 0, out
    commit_all(repo, "contract")
    os.makedirs(os.path.join(wdir, "__pycache__"), exist_ok=True)
    open(os.path.join(wdir, "__pycache__", "helper.cpython-312.pyc"), "wb").write(b"\0")
    out, rc = donectl.verify()
    assert rc == 0 and out["verification_status"] == "PASS", out


def test_a_lock_from_before_pinning_with_recipe_files_is_flagged_not_blocked(repo):
    wdir, _ = open_contract(checks_in_workdir)
    out, rc = donectl.lock()
    assert rc == 0, out
    lp = os.path.join(wdir, "lock.json")
    lk = json.load(open(lp))
    lk.pop("recipe_pins", None)  # what every lock written before 20/10/2026 looks like
    json.dump(lk, open(lp, "w"), indent=2)
    st = donectl.status()
    # Reported loudly, not refused: 34 live contracts were such locks on 20/10/2026.
    assert st["contract_status"] == "LOCKED", st
    assert any("UNPINNED" in r and "revise" in r for r in st["reasons"]), st
    out, rc = donectl.lock()  # re-lock never blesses unpinned files as agreed
    assert rc == 1 and "revise" in out.get("error", ""), out


def test_a_lock_from_before_pinning_with_no_recipe_files_still_holds(repo):
    wdir, _ = open_contract(lambda w: [crit("C1", "true")])
    out, rc = donectl.lock()
    assert rc == 0, out
    lp = os.path.join(wdir, "lock.json")
    lk = json.load(open(lp))
    lk.pop("recipe_pins", None)
    json.dump(lk, open(lp, "w"), indent=2)
    assert donectl.status()["contract_status"] == "LOCKED"


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    home, cwd, failed = os.environ.get("HOME"), os.getcwd(), 0
    for name, fn in tests:
        tmp = tempfile.mkdtemp(prefix="donectl-pin-test-")
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
