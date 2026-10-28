"""C3 (w_cae13c9af03d): every planted mutant must make tests/test_jev_spend_call_id.py fail by assertion; the unmutated copy must pass.

Runs on an export of HEAD under /tmp (never the worktree), with HOME pointed at a throwaway directory so no
run can touch the real ~/.local/state/jev ledger. Each mutant is a list of (file, find, replace) edits applied
in order; every `find` must occur exactly once at the moment it is applied, or the mutant is a FAIL
(a mutant that plants nothing proves nothing). A mutant that breaks import or syntax is also a FAIL."""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT, PY = sys.argv[1], sys.argv[2]
TEST = "tests/test_jev_spend_call_id.py"
S, SH, SUP = "jev_platform/spend.py", "scripts/mission_control_jev_shadow.py", "scripts/jev_shadow_support.py"
MUTANTS = {
    "call-id-not-written": [(S, "(day, caller, float(reserved_usd), created, call_id)", "(day, caller, float(reserved_usd), created, None)")],
    "call-id-reused": [(S, "    call_id = uuid.uuid4().hex\n", "    call_id = 'same'\n")],
    "call-id-not-unique": [(S, "CREATE UNIQUE INDEX IF NOT EXISTS calls_call_id", "CREATE INDEX IF NOT EXISTS calls_call_id")],
    "old-ledger-not-upgraded": [(S, '            db.execute("ALTER TABLE calls ADD COLUMN call_id TEXT")\n', "            pass\n")],
    "reserve-returns-tuple": [(S, "    return reserve_call(caller, reserved_usd)[0]\n", "    return reserve_call(caller, reserved_usd)\n")],
    "mirror-drops-call-id": [(SH, "(spend_id, spend_call_id, call_id)", "(spend_id, None, call_id)")],
    "mirror-stores-row-id": [(SH, "(spend_id, spend_call_id, call_id)", "(spend_id, str(spend_id), call_id)")],
}
BROKEN = re.compile(r"SyntaxError|IndentationError|ImportError|ModuleNotFoundError|NameError: name '|errors? during collection")


def export(dest):
    archive = subprocess.run(["git", "-C", ROOT, "archive", "HEAD"], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", dest], input=archive, check=True)


def run_tests(cwd, home):
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": home, "TMPDIR": "/tmp", "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"}
    r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST], cwd=cwd,
                       capture_output=True, text=True, env=env, timeout=900)
    return r.returncode, r.stdout + r.stderr


failed = False
with tempfile.TemporaryDirectory(prefix="jev-mut-", dir="/tmp") as base:
    home = os.path.join(base, "home")
    os.mkdir(home)
    clean = os.path.join(base, "clean")
    os.mkdir(clean)
    export(clean)
    code, out = run_tests(clean, home)
    print(f"unmutated: exit {code}")
    if code != 0:
        print(out[-1500:])
        sys.exit(1)
    for name, edits in MUTANTS.items():
        work = os.path.join(base, name)
        shutil.copytree(clean, work)
        ok = True
        for path, find, repl in edits:
            target = os.path.join(work, path)
            src = open(target, encoding="utf-8").read()
            if src.count(find) != 1:
                print(f"FAIL {name}: {find!r} occurs {src.count(find)} times in {path} (need exactly 1)")
                ok = False
                break
            open(target, "w", encoding="utf-8").write(src.replace(find, repl))
        if not ok:
            failed = True
            continue
        code, out = run_tests(work, home)
        if code == 0:
            print(f"SURVIVED {name}")
            failed = True
        elif BROKEN.search(out):
            print(f"FAIL {name}: killed by a crash, not an assertion")
            print(out[-800:])
            failed = True
        else:
            first = next((l for l in out.splitlines() if l.startswith("FAILED")), "")
            print(f"KILLED {name}: {first[:160]}")
    real = os.path.expanduser("~/.local/state/jev/spend.sqlite")
    print(f"real ledger untouched check: HOME for runs was {home}; real path {real}")
sys.exit(1 if failed else 0)
