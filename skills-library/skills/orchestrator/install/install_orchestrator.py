#!/usr/bin/env python3
"""Idempotent installer for the Orchestrator v1 LaunchAgents (Mac Mini only, stdlib, python 3.9 ok).

Writes two plists to ~/Library/LaunchAgents and loads them in the GUI domain:
  com.unite.orchestrator           orchestrator.py, every 30 min
  com.unite.orchestrator-deadman   orchestrator.py --deadman, every 15 min
Refuses while <state>/ORCHESTRATOR-DISABLED exists, so bootstrap.sh cannot undo an uninstall.
On any other host it does nothing and exits 0.

Usage: install_orchestrator.py [--uninstall]
The paths are fixed to this user's home, the same ones orchestrator.py reads; any other flag is refused.
"""
import os
import plistlib
import socket
import subprocess
import sys
import tempfile

HOME = os.path.expanduser("~")
SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "orchestrator.py")
JOBS = (("com.unite.orchestrator", [], 1800), ("com.unite.orchestrator-deadman", ["--deadman"], 900))
MINI_HOST_PREFIX = "phills-mac-mini"


def plist_bytes(label, extra, interval, state):
    return plistlib.dumps({
        "Label": label,
        "ProgramArguments": ["/usr/bin/python3", SCRIPT] + extra,
        "StartInterval": interval,
        "RunAtLoad": True,
        "ProcessType": "Background",
        # launchd opens these before Python's path guard runs, so they never name a file.
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
    })


def write_atomic(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".orch-install-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv, agents=None, state=None, launchctl="launchctl"):
    """agents, state and launchctl are for tests only; the command line cannot set them."""
    unknown = [a for a in argv if a != "--uninstall"]
    if unknown:
        print("install_orchestrator: unsupported argument(s) %s; only --uninstall is accepted" % " ".join(unknown))
        return 2
    agents = agents or os.path.join(HOME, "Library", "LaunchAgents")
    state = state or os.path.join(HOME, ".local", "state", "orchestrator")
    host = socket.gethostname().lower()
    domain = "gui/%d" % os.getuid()
    marker = os.path.join(state, "ORCHESTRATOR-DISABLED")

    def lc(*a):
        return subprocess.run([launchctl] + list(a), stdout=subprocess.PIPE, stderr=subprocess.STDOUT).returncode

    if not host.startswith(MINI_HOST_PREFIX):
        print("install_orchestrator: not the Mac Mini (%s), nothing done" % host)
        return 0
    os.makedirs(state, exist_ok=True)

    if "--uninstall" in argv:
        open(marker, "a").close()
        for label, _, _ in JOBS:
            lc("bootout", "%s/%s" % (domain, label))
            p = os.path.join(agents, label + ".plist")
            if os.path.exists(p):
                os.remove(p)
        print("install_orchestrator: uninstalled; %s written (delete it to allow reinstall)" % marker)
        return 0

    if os.path.exists(marker):
        print("install_orchestrator: refused, %s exists (an uninstall or manual stop)" % marker)
        return 3
    os.makedirs(agents, exist_ok=True)
    for label, extra, interval in JOBS:
        p = os.path.join(agents, label + ".plist")
        data = plist_bytes(label, extra, interval, state)
        try:
            with open(p, "rb") as f:
                same = f.read() == data
        except OSError:
            same = False
        if not same:
            write_atomic(p, data)
            lc("bootout", "%s/%s" % (domain, label))
        if lc("print", "%s/%s" % (domain, label)) != 0:
            if lc("bootstrap", domain, p) != 0:
                print("install_orchestrator: bootstrap failed for %s" % label)
                return 1
    print("install_orchestrator: installed %s" % ", ".join(l for l, _, _ in JOBS))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
