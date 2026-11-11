#!/usr/bin/env python3
"""sot_hook.py on a machine with no fcntl. The PC runs Windows: on 26/10/2026 the merged hook imported fcntl at the
top and crashed every PC session start and stop. Runs on any OS: off Windows it hides fcntl and stubs msvcrt; on
Windows it uses the real msvcrt. Stdlib only (no pty, no fcntl), so it also runs under the PC's python."""
import os, subprocess, sys, tempfile, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(os.path.dirname(HERE), "scripts", "sot_hook.py")

PRELUDE = r'''
import sys, types
import subprocess, socket, hashlib   # subprocess probes msvcrt to detect Windows: load it before the stub goes in
calls = []
if sys.platform != "win32":   # simulate the PC for the hook only: fcntl missing, msvcrt present
    sys.modules["fcntl"] = None
    m = types.ModuleType("msvcrt"); m.LK_NBLCK = 2
    m.locking = lambda fd, mode, n: calls.append((mode, n))
    sys.modules["msvcrt"] = m
'''


def probe(body, tmp):
    env = dict(os.environ, SOT_OPS=os.path.join(tmp, "no-mini-ops"), SOT_STATE=os.path.join(tmp, "state"),
               SOT_DEBUG_DIR=tmp)
    return subprocess.run([sys.executable, "-c", PRELUDE + body, HOOK, os.path.join(tmp, "x.lock")],
                          input="", capture_output=True, text=True, timeout=60, env=env)   # never the runner's stdin (UNI-3101)


def test_the_hook_imports_and_locks_without_fcntl(tmp):
    r = probe(r'''
import importlib.util
spec = importlib.util.spec_from_file_location("sot_hook", sys.argv[1]); h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
for _ in range(2):   # a lock released on close can be taken again
    with open(sys.argv[2], "a+") as f:
        h.lock(f)
if sys.platform != "win32":
    assert calls == [(2, 1), (2, 1)], calls
print("locked")
''', tmp)
    assert r.returncode == 0 and "locked" in r.stdout, r.stdout + r.stderr


def test_start_runs_and_fails_open_without_fcntl(tmp):
    r = probe(r'''
import runpy
sys.argv = [sys.argv[1], "start", "--tool", "claude", "--machine", "PortableTest", "--mini", "nohost.invalid"]
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit as e:
    print("exit", e.code)
''', tmp)
    assert "Traceback" not in r.stderr and "exit 0" in r.stdout, r.stdout + r.stderr


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        tmp = tempfile.mkdtemp(prefix="sot-portable-")
        try:
            t(tmp); passed += 1; print("PASS", t.__name__)
        except Exception:
            traceback.print_exc(); print("FAIL", t.__name__)
    print("%d/%d passed" % (passed, len(TESTS)))
    sys.exit(0 if passed == len(TESTS) else 1)
