"""The identity key must not depend on the PROCESS cwd (20/10/2026, found wiring weakness #2).

`git rev-parse --git-dir` answers ".git" at a repository's top level, and identity_key took
os.path.realpath of that - which resolves against the process's own cwd, not the `cwd`
argument. Any caller that asks about another directory (a PreToolUse hook judging the
repository a Write targets) got a key for a directory that does not exist, found no work
item, and read a LOCKED contract as ABSENT.
    python3 skills/done-harness/scripts/test_donectl_identity_cwd.py   (exit 1 on any failure)
"""
import json
import os
import shutil
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import donectl  # noqa: E402
from test_donectl_verify import make_repo  # noqa: E402


def test_status_for_another_directory_finds_its_locked_contract(repo):
    out, rc = donectl.start("identity from elsewhere")
    assert rc == 0, out
    c = json.load(open(out["contract_path"]))
    c["criteria"] = [{"id": "C1", "text": "holds", "recipe": "true"}]
    json.dump(c, open(out["contract_path"], "w"))
    out, rc = donectl.lock()
    assert rc == 0, out
    assert donectl.status()["contract_status"] == "LOCKED"  # control: from inside
    elsewhere = tempfile.mkdtemp(prefix="donectl-elsewhere-")
    try:
        os.chdir(elsewhere)
        st = donectl.status(cwd=repo)
        assert st["contract_status"] == "LOCKED", st["reasons"]
        assert donectl.preflight("Write", {"file_path": os.path.join(repo, "x.py")},
                                 cwd=repo)["decision"] == "ALLOW"
        assert os.path.isabs(st["identity"]["git_dir"]), st["identity"]
    finally:
        os.chdir(repo)
        shutil.rmtree(elsewhere, ignore_errors=True)


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    home, cwd, failed = os.environ.get("HOME"), os.getcwd(), 0
    for name, fn in tests:
        tmp = tempfile.mkdtemp(prefix="donectl-ident-test-")
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
