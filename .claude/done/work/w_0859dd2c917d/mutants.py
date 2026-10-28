"""C3 (w_0859dd2c917d, RA-8125 v2): each mutant reintroduces one defect and must make the regression test fail by
assertion; the unmutated export must pass. Runs on an export of HEAD under /tmp, never the worktree.

v2 replaces v1's launch-dir mutant: Codex round 1 showed that preferring the cwd repository runs a foreign hook,
so the settings command stays bound to $CLAUDE_PROJECT_DIR and the mutant puts the cwd preference back.
argv: ROOT PY"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT, PY = sys.argv[1], sys.argv[2]
TEST = "tests/test_autonomy_gate_hook_paths.py"
HOOK, SETTINGS = ".claude/hooks/autonomy_gate_hook.py", ".claude/settings.json"
TRUSTED = '"command": "python3 \\"$CLAUDE_PROJECT_DIR/.claude/hooks/autonomy_gate_hook.py\\""'
CWD_FIRST = ('"command": "d=$(git rev-parse --show-toplevel 2>/dev/null); [ -f \\"$d/.claude/hooks/autonomy_gate_hook.py\\" ]'
             ' || d=\\"$CLAUDE_PROJECT_DIR\\"; python3 \\"$d/.claude/hooks/autonomy_gate_hook.py\\""')
MUTANTS = {
    "hook-root-by-abspath": [(HOOK, "os.path.realpath(__file__)", "os.path.abspath(__file__)")],
    "settings-prefers-cwd-repo": [(SETTINGS, TRUSTED, CWD_FIRST)],
}
BROKEN = re.compile(r"SyntaxError|IndentationError|ImportError while|errors? during collection")


def export(dest):
    archive = subprocess.run(["git", "-C", ROOT, "archive", "HEAD"], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", dest], input=archive, check=True)


def run(cwd):
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "TMPDIR": "/tmp", "HOME": "/tmp", "LANG": "C.UTF-8"}
    r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST], cwd=cwd, capture_output=True,
                       text=True, env=env, timeout=600)
    return r.returncode, r.stdout + r.stderr


failed = False
with tempfile.TemporaryDirectory(prefix="ra8125-mut-", dir="/tmp") as base:
    clean = os.path.join(base, "clean")
    os.mkdir(clean)
    export(clean)
    code, out = run(clean)
    print(f"unmutated: exit {code}")
    if code != 0:
        print(out[-1500:])
        sys.exit(1)
    for name, edits in MUTANTS.items():
        work = os.path.join(base, name)
        shutil.copytree(clean, work, symlinks=True)
        ok = True
        for path, find, repl in edits:
            target = os.path.join(work, path)
            src = open(target, encoding="utf-8").read()
            if src.count(find) != 1:
                print(f"FAIL {name}: {find!r} occurs {src.count(find)} times in {path}")
                ok = False
                break
            open(target, "w", encoding="utf-8").write(src.replace(find, repl))
        if not ok:
            failed = True
            continue
        code, out = run(work)
        if code == 0:
            print(f"SURVIVED {name}")
            failed = True
        elif BROKEN.search(out):
            print(f"FAIL {name}: killed by a crash, not an assertion\n{out[-800:]}")
            failed = True
        else:
            first = next((line for line in out.splitlines() if line.startswith("FAILED")), "")
            print(f"KILLED {name}: {first[:160]}")
sys.exit(1 if failed else 0)
