"""RA-8174 C4: every planted defect must turn the red-main test suite red.

Usage: mutants.py <repo> <python-with-pytest>. Copies the repo's scripts/ and tests
for the watcher into a temp dir, applies one mutant at a time, and runs the suite.
A mutant that leaves the suite green is SURVIVED and fails this criterion. The
unmutated copy must pass first (positive control for the harness itself).
"""
import os
import shutil
import subprocess
import sys
import tempfile

MUTANTS = [
    ("red read as green", "scripts/red_main/detect.py",
     'FAILED = {"failure", "timed_out", "startup_failure", "action_required"}', 'FAILED = {"timed_out"}'),
    ("UNKNOWN treated as green", "scripts/red_main/board.py",
     "        if state == OK:\n", "        if state in (OK, UNKNOWN):\n"),
    ("second lane for the same episode", "scripts/red_main/actions.py",
     '    if alive:\n        return "flag-no-pr" if late_pr else "wait"\n',
     '    if alive:\n        return "relaunch"\n'),
    ("busiest host picked", "scripts/red_main/lanes.py",
     "    _, _, name, via = min(eligible)", "    _, _, name, via = max(eligible)"),
    ("parked job resumed on UNKNOWN", "scripts/red_main/board.py",
     '        elif state == UNKNOWN and live and not card.get("unknown_since"):\n',
     '        elif state == UNKNOWN and live and not card.get("unknown_since") and not resume_parked(d, repo, at):\n'),
    ("PR grace ignored", "scripts/red_main/actions.py",
     "    late_pr = pushed_min is not None and pushed_min >= grace_min",
     "    late_pr = pushed_min is not None"),
    ("unowned line never escalated", "scripts/red_main/annotate.py",
     "            card = _escalate(d, k, line, at, card)\n            changed = True\n",
     "            pass\n"),
    ("lane cap ignored", "scripts/red_main/watch.py",
     "may_launch=budget > 0)", "may_launch=True)"),
    ("unowned red-main card never escalated", "scripts/red_main/watch.py",
     '        if not card.get("escalated"):\n', '        if False:\n'),
]
FILES = ["scripts/red_main", "scripts/red_main_watch.py", "tests/test_red_main_watch.py",
         "tests/test_red_main_cycle.py", "tests/red_main_support.py"]


def suite(root, py):
    env = {"HOME": tempfile.mkdtemp(), "PATH": "/usr/bin:/bin", "TMPDIR": "/tmp"}
    r = subprocess.run([py, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "--rootdir", root,
                        "tests/test_red_main_watch.py", "tests/test_red_main_cycle.py"],
                       cwd=root, env=env, capture_output=True, text=True, timeout=600)
    return r.returncode == 0


def copy(repo, dest):
    for f in FILES:
        src, dst = os.path.join(repo, f), os.path.join(dest, f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)


def main(repo, py):
    base = tempfile.mkdtemp(prefix="ra8174-mut-")
    copy(repo, os.path.join(base, "clean"))
    if not suite(os.path.join(base, "clean"), py):
        print("CONTROL FAILED: the unmutated suite is not green"); return 1
    survived = 0
    for name, path, old, new in MUTANTS:
        root = os.path.join(base, name.replace(" ", "_"))
        copy(repo, root)
        target = os.path.join(root, path)
        text = open(target).read()
        if text.count(old) != 1:
            print(f"BAD MUTANT {name}: anchor found {text.count(old)} times"); survived += 1; continue
        open(target, "w").write(text.replace(old, new))
        killed = not suite(root, py)
        print(f"{'KILLED  ' if killed else 'SURVIVED'} {name}")
        survived += 0 if killed else 1
    print(f"{len(MUTANTS) - survived}/{len(MUTANTS)} killed")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
