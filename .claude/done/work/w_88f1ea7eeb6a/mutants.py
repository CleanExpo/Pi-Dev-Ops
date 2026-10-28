"""RA-8127 mutation control: each planted defect in .claude/settings.json must fail C1 by assertion.

Usage: mutants.py <repo> <python>. Refuses a dirty tracked tree; restores settings.json after every mutant.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO, PY = Path(sys.argv[1]), sys.argv[2]
SETTINGS = REPO / ".claude" / "settings.json"
TEST = "tests/test_hook_missing_target_quiet.py"
OLD_CONT = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/continuation_horizon_hook.py" || exit 1'


def commands(data: dict):
    for event, groups in data["hooks"].items():
        for group in groups:
            for hook in group["hooks"]:
                yield event, hook


def stop_unguarded(data: dict) -> None:
    for event, hook in commands(data):
        if event == "Stop" and "continuation_horizon_hook" in hook["command"]:
            hook["command"] = OLD_CONT


def guard_always_skips(data: dict) -> None:
    for _, hook in commands(data):
        hook["command"] = hook["command"].replace('[ -f "$f" ] || ', "")


def sessionstart_silent(data: dict) -> None:
    for event, hook in commands(data):
        if event == "SessionStart" and "run_setup_driver" in hook["command"]:
            hook["command"] = hook["command"].replace('{ echo', '{ true ||  echo')


MUTANTS = {"stop-unguarded": stop_unguarded, "guard-always-skips": guard_always_skips,
           "sessionstart-silent": sessionstart_silent}


def run_tests() -> subprocess.CompletedProcess:
    env = {"HOME": "/tmp/ra8127-mut-home", "PATH": "/usr/bin:/bin", "TMPDIR": "/tmp"}
    return subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=600)


def main() -> int:
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO,
                           capture_output=True, text=True).stdout.strip()
    dirty = "\n".join(line for line in dirty.splitlines() if ".claude/done/" not in line)
    if dirty:
        print("REFUSED: tracked tree is dirty\n" + dirty)
        return 2
    base = run_tests()
    if base.returncode != 0:
        print("UNMUTATED FAILS\n" + base.stdout[-2000:])
        return 1
    original = SETTINGS.read_text(encoding="utf-8")
    failed = []
    for name, mutate in MUTANTS.items():
        data = json.loads(original)
        mutate(data)
        mutated = json.dumps(data, indent=2) + "\n"
        if mutated == original or json.loads(mutated) == json.loads(original):
            failed.append(f"{name}: mutation changed nothing")
            continue
        try:
            SETTINGS.write_text(mutated, encoding="utf-8")
            result = run_tests()
        finally:
            SETTINGS.write_text(original, encoding="utf-8")
        killed = result.returncode == 1 and "tests/test_hook_missing_target_quiet.py::" in result.stdout
        print(f"{name}: {'KILLED' if killed else 'SURVIVED'} (rc={result.returncode})")
        if not killed:
            failed.append(name)
    if subprocess.run(["git", "diff", "--quiet", "--", str(SETTINGS)], cwd=REPO).returncode != 0:
        print("settings.json not restored")
        return 1
    print("ALL KILLED" if not failed else f"FAILED: {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
