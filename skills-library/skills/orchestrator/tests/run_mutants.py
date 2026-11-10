#!/usr/bin/env python3
"""Mutation control for orchestrator.py (spec AC-2).

Each mutant breaks one safety property in a temp copy of the script; its named test must fail
against that copy. The unmutated copy must pass the whole suite first. Exit 0 only when every
mutant is caught. A test that cannot be made to fail is not a control.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "orchestrator.py")

MUTANTS = [
    ("hard-stop-removed", '    if os.path.exists(cfg["hard_stop"]):', "    if False:",
     "test_hard_stop_never_opens_board"),
    ("run-lock-no-op", "        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)", "        pass",
     "test_run_lock_blocks_second_instance"),
    ("board-read-swallowed", '                row["error"] = "board_unreadable: %s" % type(e).__name__',
     '                d = {"jobs": []}', "test_malformed_board_is_reported_not_empty"),
    ("mount-check-removed", '        if not cfg["is_mounted"](cfg["volume"]):', "        if False:",
     "test_unmounted_volume_never_reads_board_or_creates_dirs"),
    ("probe-output-kept", '        lanes[name] = {"state": st, "reason": rs}',
     '        lanes[name] = {"state": st, "reason": rs, "raw": out}', "test_probe_output_never_reaches_disk"),
    ("escaping-removed", '    return _MD.sub(r"\\\\\\1", html.escape(" ".join(str(text).split()), quote=True))[:160]',
     "    return str(text)", "test_titles_are_escaped"),
    ("finally-row-removed", "        append_row(cfg, row)\n    return row", "        pass\n    return row",
     "test_crash_mid_run_still_writes_row"),
    ("deadman-threshold-ignored", "    if age is not None and age <= STALE_AFTER_S:", "    if True:",
     "test_deadman_flags_stale_log"),
    ("missing-priority-default-removed", '    p = j.get("priority")', '    p = j["priority"]',
     "test_missing_priority_is_ranked_last"),
    ("extra-subprocess-call", "def _run(cfg, row):\n", 'def _run(cfg, row):\n    subprocess.run(["/usr/bin/true"])\n',
     "test_every_subprocess_argv_is_allow_listed"),
    ("watcher-exclusion-removed", '             and not str(j.get("id", "")).startswith("W-") and not j.get("filler_key")]',
     '             and not j.get("filler_key")]', "test_watcher_and_filler_jobs_are_not_suggested"),
    ("deadline-swallowable", "class Deadline(BaseException):", "class Deadline(OSError):",
     "test_run_gives_up_on_a_hung_board"),
    ("deadman-deadline-removed", "        signal.alarm(DEADMAN_DEADLINE_S)\n", "        pass\n",
     "test_deadman_gives_up_on_a_hung_mirror"),
    ("allowlist-guard-removed", "    if tuple(argv) not in ALLOWED_ARGV:", "    if False:",
     "test_allow_list_rejects_other_commands"),
    ("hard-link-alias-allowed", "    try:\n        return os.path.samefile(a, b)", "    try:\n        return False",
     "test_outputs_never_overwrite_the_inputs"),
    ("run-path-guard-removed", '    if unsafe_paths(cfg):\n        row["error"] = "unsafe_paths"', '    if False:\n        row["error"] = "unsafe_paths"',
     "test_outputs_never_overwrite_the_inputs"),
]


def run_tests(script, name=None):
    env = dict(os.environ, ORCH_UNDER_TEST=script)
    cmd = [sys.executable, "-m", "unittest"] + (["-k", name] if name else []) + ["test_orchestrator"]
    p = subprocess.run(cmd, cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def main():
    src = open(SCRIPT).read()
    work = tempfile.mkdtemp(prefix="orch-mutants-")
    failures = []
    try:
        clean = os.path.join(work, "orchestrator.py")
        shutil.copy(SCRIPT, clean)
        rc, out = run_tests(clean)
        print("unmutated suite exit=%d" % rc)
        if rc != 0:
            print(out[-2000:])
            return 1
        for label, find, replace, test in MUTANTS:
            if src.count(find) != 1:
                failures.append(label)
                print("%-34s ANCHOR MISSING (found %d times)" % (label, src.count(find)))
                continue
            path = os.path.join(work, "m-%s.py" % label)
            with open(path, "w") as f:
                f.write(src.replace(find, replace))
            rc, out = run_tests(path, test)
            ran = "Ran 0 tests" not in out
            caught = rc != 0 and ran
            print("%-34s %s exit=%d (%s)" % (label, "CAUGHT" if caught else "SURVIVED", rc, test))
            if not caught:
                failures.append(label)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("mutants caught %d/%d" % (len(MUTANTS) - len(failures), len(MUTANTS)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
