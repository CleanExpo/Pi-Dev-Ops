#!/usr/bin/env python3
"""Append one /spm run event to the 2nd brain journal, after a secret scan.

Usage: journal_event.py --summary TEXT [--lane L] [--tier T] [--next TEXT] [--decision TEXT ...]

The event is scanned with gitleaks (stdin mode) before it touches the vault:
- scanner finds a secret      -> exit 3, nothing written
- scanner missing or errors   -> exit 4, nothing written (an unscanned write is refused,
                                 never treated as clean)
- no vault found              -> exit 4, nothing written
- clean                       -> one JSON line appended to
                                 <brain>/2nd Brain/journal/spm/<YYYY-MM>.jsonl, exit 0
Nothing is committed or pushed here; the brain's own sync owns that.

Test hooks (env): SPM_BRAIN (vault root), SPM_GITLEAKS (scanner path).
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOME = Path.home()
CONFIG = Path(__file__).resolve().parent / "gitleaks.toml"


def brain_root():
    if os.environ.get("SPM_BRAIN"):
        return Path(os.environ["SPM_BRAIN"])
    for c in (HOME / "2nd-brain", HOME / "2nd Brain"):
        if (c / "2nd Brain").is_dir():
            return c
    print("UNPROVEN: brain (no vault found at ~/2nd-brain or ~/2nd Brain)", file=sys.stderr)
    sys.exit(4)


def scanner():
    p = os.environ.get("SPM_GITLEAKS") or shutil.which("gitleaks") or str(HOME / ".local/bin/gitleaks")
    return p if Path(p).is_file() and os.access(p, os.X_OK) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", required=True)
    ap.add_argument("--lane", default="")
    ap.add_argument("--tier", default="")
    ap.add_argument("--next", default="")
    ap.add_argument("--decision", action="append", default=[])
    a = ap.parse_args()

    event = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": socket.gethostname(),
        "cwd": str(Path.cwd()),
        "lane": a.lane, "tier": a.tier,
        "summary": a.summary, "decisions": a.decision, "next": a.next,
    }
    line = json.dumps(event, ensure_ascii=False)

    gl = scanner()
    if not gl:
        print("REFUSED: secret scanner not found; nothing written", file=sys.stderr)
        return 4
    # The ruleset is the library's, never the target repo's: pinned --config, a neutral cwd (no
    # .gitleaks.toml / .gitleaksignore to pick up) and no GITLEAKS_CONFIG* from the caller's env.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITLEAKS_CONFIG")}
    # Scan the written line AND each field as typed: JSON escaping turns KEY="value" into
    # KEY=\"value\", a shape gitleaks' rules miss. gitleaks also skips any line carrying its
    # inline allow marker, and event text is model- and user-authored, so it is neutralised.
    fields = [a.summary, a.next, a.lane, a.tier, *a.decision]
    scanned = re.sub(r"gitleaks:allow", "gitleaks-allow", "\n".join([line, *fields]), flags=re.I)
    try:
        with tempfile.TemporaryDirectory() as neutral:
            r = subprocess.run([gl, "stdin", "--no-banner", "--redact", "--exit-code", "3",
                                "--config", str(CONFIG)],
                               input=scanned, capture_output=True, text=True, timeout=30,
                               cwd=neutral, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"REFUSED: secret scan failed ({type(e).__name__}); nothing written", file=sys.stderr)
        return 4
    if r.returncode == 3:
        print("REFUSED: event holds a secret-shaped value; nothing written", file=sys.stderr)
        return 3
    if r.returncode != 0:
        print(f"REFUSED: secret scan exited {r.returncode}; nothing written", file=sys.stderr)
        return 4

    out = brain_root() / "2nd Brain" / "journal" / "spm" / f"{event['ts'][:7]}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(f"journal: appended to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
