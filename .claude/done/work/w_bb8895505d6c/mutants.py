"""C4: every planted mutant must make tests/test_jev_spend_ledger.py fail by assertion; the unmutated copy must pass.

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
TEST = "tests/test_jev_spend_ledger.py"
C, S = "jev_platform/client.py", "jev_platform/spend.py"
SH, TR, HA = "scripts/mission_control_jev_shadow.py", "scripts/jev_triage.py", "evals/jev_constitution/harness.py"
INNER = "            row = spend.reserve(CALLER, RESERVE_USD)"
POST = "status, data, retry_after = post(body, min(REQUEST_TIMEOUT, budget.remaining_seconds()))"

MUTANTS = {
    "client-no-reserve": [(C, INNER, "            row = 0")],
    "client-reserve-after-send": [(C, INNER, "            pass"),
                                  (C, POST, POST + "; row = spend.reserve(CALLER, RESERVE_USD)")],
    "client-reserve-outside-retry": [(C, INNER, "            pass"),
                                     (C, "    for attempt in range(MAX_RETRIES + 1):",
                                      "    row = spend.reserve(CALLER, RESERVE_USD)\n    for attempt in range(MAX_RETRIES + 1):")],
    "client-settle-writes-reserve": [(C, "spend.finish(row, *_settled(data))", 'spend.finish(row, "answered", RESERVE_USD)')],
    "shadow-no-reserve": [(SH, "spend.reserve(", "(lambda *a, **k: 0)(")],
    "triage-no-reserve": [(TR, "spend.reserve(", "(lambda *a, **k: 0)(")],
    "harness-no-reserve": [(HA, "spend.reserve(", "(lambda *a, **k: 0)(")],
    "spend-local-day": [(S, "datetime.fromtimestamp(stamp, UTC)", "datetime.fromtimestamp(stamp)")],
    "spend-reserve-swallows": [(S, "raise SpendUnrecorded(", "return 0 and SpendUnrecorded(")],
    "spend-path-at-import": [(S, "target = ledger_path()", "target = _AT_IMPORT"),
                             (S, "\ndef reserve(", "\n_AT_IMPORT = ledger_path()\n\n\ndef reserve(")],
    "spend-finish-raises": [(S, "return False  # settle failed", "raise")],
    "spend-cap-check-removed": [(S, "if cap is not None and spent + reserved_usd > cap:", "if False:")],
    "shadow-canonical-first": [(SH, "    ledger.parent.mkdir(parents=True, exist_ok=True)",
                                "    spend.reserve(_caller(ledger), estimated_tokens * USD_PER_MILLION_INPUT / 1_000_000)\n"
                                "    ledger.parent.mkdir(parents=True, exist_ok=True)")],
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
