#!/usr/bin/env python3
"""Idempotent installer for the Guardian watchers (macOS only). Copies guardian-watcher.py, jev-cap-watcher.py,
live_claude_drift.py and jobs_lock.py from ../scripts to ~/.local/bin. A differing existing file is first saved as <name>.bak-<YYYYMMDD-HHMMSS>.
Never touches launchd: the plists in ../launchd are reference copies; loading them is a separate, deliberate step.
Usage: install_guardian.py [--dry-run]"""
import datetime, filecmp, os, sys, tempfile

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
FILES = ("guardian-watcher.py", "jev-cap-watcher.py", "jobs_lock.py", "live_claude_drift.py")

def safe_write(src, dst, mode, bin_real):
    """Write src's bytes to dst via a temp file in the bin dir + os.replace, so a link at dst is replaced, never followed."""
    fd, tmp = tempfile.mkstemp(dir=bin_real, prefix=".install-")
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            out.write(inp.read())
        os.chmod(tmp, mode)
        os.replace(tmp, dst)
    except BaseException:
        if os.path.lexists(tmp):
            os.unlink(tmp)
        raise

def refusal(dst, bin_real):
    """Reason string if dst must not be written, else None: a link, or anything resolving outside the bin dir."""
    if os.path.islink(dst):
        return f"{dst} is a symlink"
    real = os.path.realpath(dst)
    if os.path.dirname(real) != bin_real:
        return f"{dst} resolves to {real}, outside {bin_real}"
    return None

def main(argv):
    dry = "--dry-run" in argv
    if sys.platform != "darwin":
        print("install_guardian: macOS only, nothing done"); return 1
    dest = os.path.join(os.path.expanduser("~"), ".local", "bin")
    home = os.path.expanduser("~")
    for part in (os.path.join(home, ".local"), dest):
        if os.path.islink(part):  # islink per component: realpath-vs-abspath would misfire on /var -> /private
            print(f"REFUSED {part} is a symlink; nothing written"); return 1
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"{'DRY RUN: ' if dry else ''}installing to {dest}")
    if not dry:
        os.makedirs(dest, exist_ok=True)
    bin_real = os.path.realpath(dest)
    bad = [f"REFUSED {name}: {why}" for name in FILES if (why := refusal(os.path.join(dest, name), bin_real))]
    if bad:
        print("\n".join(bad)); print("install_guardian: refusing to write through a link; nothing written"); return 1
    for name in FILES:
        src, dst = os.path.join(SRC, name), os.path.join(dest, name)
        if not os.path.exists(src):
            print(f"MISSING source {src}"); return 1
        if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
            print(f"unchanged  {name}"); continue
        if os.path.exists(dst):
            print(f"backup     {name} -> {name}.bak-{stamp}")
            bak = f"{dst}.bak-{stamp}"
            if os.path.lexists(bak):
                print(f"REFUSED backup {bak}: already exists"); return 1
            if not dry:
                safe_write(dst, bak, os.stat(dst).st_mode & 0o777, bin_real)
        print(f"{'would copy' if dry else 'copied    '} {name}")
        if not dry:
            safe_write(src, dst, 0o644 if name == "jobs_lock.py" else 0o755, bin_real)
    print("launchd not touched")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
