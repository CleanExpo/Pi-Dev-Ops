#!/usr/bin/env python3
"""Idempotent installer for the estate-tidy schedule. Called by bootstrap.sh on every machine.

MacBook: launchd com.unite.estate-tidy, every 2 h at :00.
Mini:    launchd com.unite.estate-tidy at :20, plus com.unite.estate-tidy-relay every 5 min.
PC (WSL, run as root): systemd estate-tidy.timer at :40; the script is copied to a root-owned path.

  install_estate_tidy.py                  install or update (backs up any file it changes)
  install_estate_tidy.py --sessions on    also hand off idle agent tmux sessions each pass (remembered)
  install_estate_tidy.py --check          exit 0 only if what is installed matches what would be written
"""
import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
# The schedule always points at the synced Library copy, whichever checkout runs the installer.
_CANON = [Path.home() / ".claude/skills/estate-tidy/estate_tidy.py",
          Path("/home/cloudroom-agent/.claude/skills/estate-tidy/estate_tidy.py")]
def canonical_script():
    for candidate in _CANON:
        try:
            if candidate.exists():
                return candidate
        except PermissionError:
            # Another account's optional copy is unavailable; preserve its permissions.
            continue
    return HERE / "estate_tidy.py"


SCRIPT = canonical_script()
LABEL = "com.unite.estate-tidy"
RELAY = "com.unite.estate-tidy-relay"
SSD = "/Volumes/Mini Mini 2T Storage"


def machine():
    try:
        if "microsoft" in Path("/proc/version").read_text().lower():
            return "pc"
    except OSError:
        pass
    return "mini" if "mac-mini" in socket.gethostname().lower() else "macbook"


def state_dir(m):
    if m == "mini":
        return Path(SSD + "/hot/estate-tidy")
    if m == "pc":
        return Path("/home/cloudroom-agent/.estate-tidy")
    return Path.home() / ".estate-tidy"


def sh(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def mac_path():
    """Deterministic PATH for the launchd job: the same on every run, whatever shell runs the installer."""
    home = Path.home()
    dirs = [str(home / ".local/bin")]
    nvm = sorted((home / ".nvm/versions/node").glob("v*/bin"), key=lambda p: [int(x) for x in re.findall(r"\d+", p.parent.name)])
    if nvm:
        dirs.append(str(nvm[-1]))
    dirs += [str(home / ".docker/bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    return ":".join(d for d in dirs if os.path.isdir(d))


def plist(label, args, minute=None, interval=None, logdir=None):
    def x(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    sched = ""
    if interval:
        sched = "  <key>StartInterval</key><integer>%d</integer>\n" % interval
    else:
        items = "".join("    <dict><key>Hour</key><integer>%d</integer><key>Minute</key><integer>%d</integer></dict>\n"
                        % (h, minute) for h in range(0, 24, 2))
        sched = "  <key>StartCalendarInterval</key>\n  <array>\n%s  </array>\n" % items
    argv = "".join("    <string>%s</string>\n" % x(a) for a in args)
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
            "<plist version=\"1.0\">\n<dict>\n"
            "  <key>Label</key><string>%s</string>\n"
            "  <key>ProgramArguments</key>\n  <array>\n%s  </array>\n%s"
            "  <key>EnvironmentVariables</key><dict><key>PATH</key><string>%s</string></dict>\n"
            "  <key>Nice</key><integer>10</integer>\n  <key>LowPriorityIO</key><true/>\n"
            "  <key>StandardOutPath</key><string>%s/%s.out.log</string>\n"
            "  <key>StandardErrorPath</key><string>%s/%s.err.log</string>\n"
            "</dict>\n</plist>\n") % (label, argv, sched, x(mac_path()), x(logdir), label, x(logdir), label)


MODES = ("off", "dry", "on")
# Ownership is one exact line this installer has always written into that file, never a mention of the
# name anywhere: a third-party unit that merely says "estate-tidy" in a comment is not ours to replace.
SCRIPT_OWNER = '"""estate-tidy: the 2-hourly settle, handoff and cleanup pass. SKILL.md beside this file is the contract.'
SVC_OWNER = "Description=estate-tidy 2-hourly settle, handoff and cleanup pass"
TMR_OWNER = "Description=estate-tidy every 2 hours at :40"


def plist_owner(label):
    return "  <key>Label</key><string>%s</string>" % label


class RefusedWrite(Exception):
    pass


def parse_mode(text):
    """The persisted sessions mode, or None when the file holds anything but one known word."""
    s = text.strip()
    return s if s in MODES and text in (s, s + "\n") else None


def safe_state(path):
    """A state path a root install may read or write: not a symlink, and root-owned when running as root."""
    p = Path(path)
    if p.is_symlink():
        raise RefusedWrite("%s is a symlink" % p)
    if os.geteuid() == 0 and p.exists() and p.stat().st_uid != 0:
        raise RefusedWrite("%s is not root-owned" % p)
    return p


def write_if_changed(path, text, check, changed, owner):
    """`owner` is the exact line that marks the file as this installer's; it must be in `text` too."""
    if owner not in text.splitlines():
        raise ValueError("owner line missing from the text being written to %s" % path)
    p = Path(path)
    if p.is_symlink():
        raise RefusedWrite("%s is a symlink; not following it" % p)
    old = p.read_text() if p.exists() else None
    if old == text:
        return False
    if old is not None and owner not in old.splitlines():
        raise RefusedWrite("%s exists and was not written by this installer" % p)
    if check:
        changed.append(str(p))
        return True
    if old is not None:
        shutil.copy2(str(p), str(p) + ".bak-tidy-" + time.strftime("%Y%m%d-%H%M%S"))
    p.parent.mkdir(parents=True, exist_ok=True)
    # temp file + rename replaces the directory entry itself, never a file a link points at
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix="." + p.name + ".")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, str(p))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    changed.append(str(p))
    return True


def main():
    try:
        return install()
    except RefusedWrite as e:
        print("estate-tidy: refused: %s" % e)
        return 1


def install():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sessions", choices=["off", "dry", "on"])
    a = ap.parse_args()
    m = machine()
    st = state_dir(m)
    if m == "mini" and not os.path.isdir(SSD):
        print("estate-tidy: Mini SSD not mounted; not installing (mac-mini-external-storage rule)")
        return 1
    if not a.check:
        st.mkdir(parents=True, exist_ok=True)
    safe_state(st)
    mode_file = safe_state(st / "sessions-mode")
    mode = a.sessions
    if not mode:
        mode = parse_mode(mode_file.read_text()) if mode_file.exists() else "off"
        if mode is None:
            print("estate-tidy: %s must hold exactly one of %s; not installing" % (mode_file, ", ".join(MODES)))
            return 1
    if a.sessions and not a.check:
        mode_file.write_text(mode + "\n")
    changed = []
    if m in ("macbook", "mini"):
        py = "/opt/homebrew/bin/python3" if os.path.exists("/opt/homebrew/bin/python3") else "/usr/bin/python3"
        la = Path.home() / "Library/LaunchAgents"
        # launchd cannot open a log on the external SSD (exit 78 EX_CONFIG), so its logs stay on the internal disk
        logs = Path.home() / "Library/Logs/estate-tidy"
        if not a.check:
            logs.mkdir(parents=True, exist_ok=True)
        jobs = [(LABEL, plist(LABEL, [py, str(SCRIPT), "--machine", m, "--sessions", mode],
                              minute=0 if m == "macbook" else 20, logdir=str(logs)))]
        if m == "mini":
            jobs.append((RELAY, plist(RELAY, [py, str(SCRIPT), "--machine", m, "--relay"], interval=300,
                                      logdir=str(logs))))
        uid = os.getuid()
        for label, text in jobs:
            path = la / (label + ".plist")
            did = write_if_changed(path, text, a.check, changed, plist_owner(label))
            loaded = sh(["launchctl", "print", "gui/%d/%s" % (uid, label)])[0] == 0
            if a.check:
                if not loaded:
                    changed.append(label + " (not loaded)")
                continue
            if did or not loaded:
                sh(["launchctl", "bootout", "gui/%d/%s" % (uid, label)])
                rc, out = sh(["launchctl", "bootstrap", "gui/%d" % uid, str(path)])
                if rc != 0:
                    print("estate-tidy: launchctl bootstrap %s failed: %s" % (label, out))
                    return 1
    else:
        if os.geteuid() != 0:
            print("estate-tidy: on the PC run this installer as root inside WSL")
            return 1
        lib = "/usr/local/lib/estate-tidy/estate_tidy.py"  # root-owned copy: root never runs user-writable code
        write_if_changed(lib, SCRIPT.read_text(), a.check, changed, SCRIPT_OWNER)
        svc = ("[Unit]\nDescription=estate-tidy 2-hourly settle, handoff and cleanup pass\n[Service]\nType=oneshot\n"
               "TimeoutStartSec=7200\nNice=10\nExecStart=/usr/bin/python3 %s --machine pc --sessions %s\n" % (lib, mode))
        tmr = ("[Unit]\nDescription=estate-tidy every 2 hours at :40\n[Timer]\nOnCalendar=*-*-* 00/2:40:00\n"
               "AccuracySec=30s\nPersistent=false\n[Install]\nWantedBy=timers.target\n")
        a1 = write_if_changed("/etc/systemd/system/estate-tidy.service", svc, a.check, changed, SVC_OWNER)
        a2 = write_if_changed("/etc/systemd/system/estate-tidy.timer", tmr, a.check, changed, TMR_OWNER)
        enabled = sh(["systemctl", "is-enabled", "estate-tidy.timer"])[1] == "enabled"
        active = sh(["systemctl", "is-active", "estate-tidy.timer"])[1] == "active"
        if a.check:
            if not (enabled and active):
                changed.append("estate-tidy.timer (not enabled/active)")
        elif a1 or a2 or not (enabled and active):
            sh(["systemctl", "daemon-reload"])
            rc, out = sh(["systemctl", "enable", "--now", "estate-tidy.timer"])
            if rc != 0:
                print("estate-tidy: enabling timer failed: " + out)
                return 1
    if a.check:
        print("estate-tidy installed and current (%s, sessions %s)" % (m, mode) if not changed else
              "estate-tidy NOT current: " + ", ".join(changed))
        return 1 if changed else 0
    print("estate-tidy %s: %s (sessions %s)" % (m, ("updated " + ", ".join(changed)) if changed else "unchanged", mode))
    return 0


if __name__ == "__main__":
    sys.exit(main())
