"""C4: each planted mutant must make the new spend tests fail; the unmutated copy must pass.

Runs on an export of HEAD in a temp dir (never the worktree). Mutants are fixed here, before the build:
each names a file and an exact source snippet; a snippet that is not found is a FAIL (a mutant that
plants nothing proves nothing)."""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT, PY = sys.argv[1], sys.argv[2]
TEST = "tests/test_jev_spend_ledger.py"

# (name, file, find, replace). find must occur exactly once at HEAD.
MUTANTS = [
    ("client-send-no-reserve", "jev_platform/client.py",
     "spend.reserve(", "(lambda *a, **k: 0)("),
    ("spend-reserve-swallows", "jev_platform/spend.py",
     "raise SpendUnrecorded", "return 0  # mutant: swallowed; raise_SpendUnrecorded"),
    ("shadow-no-mirror", "scripts/mission_control_jev_shadow.py",
     "spend.reserve(", "(lambda *a, **k: None)("),
    ("triage-no-reserve", "scripts/jev_triage.py",
     "spend.reserve(", "(lambda *a, **k: 0)("),
    ("harness-no-reserve", "evals/jev_constitution/harness.py",
     "spend.reserve(", "(lambda *a, **k: 0)("),
]


def export(dest):
    archive = subprocess.run(["git", "-C", ROOT, "archive", "HEAD"], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", dest], input=archive, check=True)


def run_tests(cwd):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR="/tmp")
    r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST], cwd=cwd,
                       capture_output=True, text=True, env=env, timeout=600)
    return r.returncode, (r.stdout + r.stderr)[-600:]


failed = False
with tempfile.TemporaryDirectory(prefix="jev-mut-", dir="/tmp") as base:
    clean = os.path.join(base, "clean")
    os.mkdir(clean)
    export(clean)
    code, tail = run_tests(clean)
    print(f"unmutated: exit {code}")
    if code != 0:
        print(tail)
        sys.exit(1)
    for name, path, find, repl in MUTANTS:
        work = os.path.join(base, name)
        shutil.copytree(clean, work)
        target = os.path.join(work, path)
        src = open(target, encoding="utf-8").read()
        if src.count(find) != 1:
            print(f"FAIL {name}: snippet {find!r} occurs {src.count(find)} times in {path} (need exactly 1)")
            failed = True
            continue
        open(target, "w", encoding="utf-8").write(src.replace(find, repl))
        shutil.rmtree(os.path.join(work, "jev_platform", "__pycache__"), ignore_errors=True)
        code, tail = run_tests(work)
        verdict = "KILLED" if code != 0 else "SURVIVED"
        print(f"{verdict} {name}: exit {code}")
        if code == 0:
            failed = True
sys.exit(1 if failed else 0)
