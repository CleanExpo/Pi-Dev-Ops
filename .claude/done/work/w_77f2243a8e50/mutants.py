"""C3 (w_77f2243a8e50): every planted mutant must make tests/test_jev_spend_call_id.py fail by assertion; the unmutated copy must pass.

Runs on an export of HEAD under /tmp (never the worktree), with HOME pointed at a throwaway directory so no
run can touch the real ~/.local/state/jev ledger. Each mutant is a list of (file, find, replace) edits applied
in order; every `find` must occur exactly once at the moment it is applied, or the mutant is a FAIL
(a mutant that plants nothing proves nothing). A mutant that breaks import or syntax is also a FAIL.
v3 adds the engineering-bench mutants: settle by row id (in spend and in each caller), an unreported
missed settle, the raced-ALTER guard in both directions, and the live-Mini legacy schema skipped."""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT, PY = sys.argv[1], sys.argv[2]
TEST = "tests/test_jev_spend_call_id.py"
S, SH, SUP = "jev_platform/spend.py", "scripts/mission_control_jev_shadow.py", "scripts/jev_shadow_support.py"
CL, HA, TR = "jev_platform/client.py", "evals/jev_constitution/harness.py", "scripts/jev_triage.py"
MUTANTS = {
    "call-id-not-written": [(S, "(day, caller, float(reserved_usd), created, call_id)", "(day, caller, float(reserved_usd), created, None)")],
    "call-id-reused": [(S, "    call_id = uuid.uuid4().hex\n", "    call_id = 'same'\n")],
    "call-id-not-unique": [(S, "CREATE UNIQUE INDEX IF NOT EXISTS calls_call_id", "CREATE INDEX IF NOT EXISTS calls_call_id")],
    "old-ledger-not-upgraded": [(S, '            db.execute(f"ALTER TABLE calls ADD COLUMN {name} {kind}")\n', "            pass\n")],
    "reserve-returns-tuple": [(S, "    return reserve_call(caller, reserved_usd)[0]\n", "    return reserve_call(caller, reserved_usd)\n")],
    "mirror-drops-call-id": [(SH, "(spend_id, spend_call_id, call_id)", "(spend_id, None, call_id)")],
    "mirror-stores-row-id": [(SH, "(spend_id, spend_call_id, call_id)", "(spend_id, str(spend_id), call_id)")],
    "settle-by-row-id": [(S, '    where, key = ("id=? AND call_id=?", (row, call_id)) if call_id is not None else ("id=?", (row,))\n',
                          '    where, key = ("id=?", (row,))\n')],
    "missed-settle-unreported": [(S, "        if hit != 1:\n", "        if False:\n")],
    "raced-alter-raises": [(S, '            if "duplicate column" not in str(exc):\n', "            if True:\n")],
    "any-alter-failure-swallowed": [(S, '            if "duplicate column" not in str(exc):\n                raise\n',
                                     '            if "duplicate column" not in str(exc):\n                pass\n')],
    "legacy-call-id-only-with-spend-id": [(SUP, '    for name, kind in (("spend_id", "INTEGER"), ("spend_call_id", "TEXT")):\n        spend.add_column(db, name, kind)\n',
                                           '    if "spend_id" not in {r[1] for r in db.execute("PRAGMA table_info(calls)")}:\n'
                                           '        for name, kind in (("spend_id", "INTEGER"), ("spend_call_id", "TEXT")):\n'
                                           '            spend.add_column(db, name, kind)\n')],
    "client-settles-by-row-id": [(CL, "spend.finish(row, *_settled(data), call_id=cid)", "spend.finish(row, *_settled(data))")],
    "harness-settles-by-row-id": [(HA, "spend.finish(row, *client._settled(resp), call_id=cid)", "spend.finish(row, *client._settled(resp))")],
    "triage-settles-by-row-id": [(TR, "used * PRICE_PER_MTOK_INPUT / 1e6, used, call_id=cid)", "used * PRICE_PER_MTOK_INPUT / 1e6, used)")],
    "shadow-settles-by-row-id": [(SH, "spend.finish(machine[0], status, actual, input_tokens, call_id=machine[1])",
                                  "spend.finish(machine[0], status, actual, input_tokens)")],
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


def plant(work, edits, name):
    for path, find, repl in edits:
        target = os.path.join(work, path)
        src = open(target, encoding="utf-8").read()
        if src.count(find) != 1:
            print(f"FAIL {name}: {find!r} occurs {src.count(find)} times in {path} (need exactly 1)")
            return False
        open(target, "w", encoding="utf-8").write(src.replace(find, repl))
    return True


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
        if not plant(work, edits, name):
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
            first = next((line for line in out.splitlines() if line.startswith("FAILED")), "")
            print(f"KILLED {name}: {first[:160]}")
    real = os.path.expanduser("~/.local/state/jev/spend.sqlite")
    print(f"real ledger untouched check: HOME for runs was {home}; real path {real}")
sys.exit(1 if failed else 0)
