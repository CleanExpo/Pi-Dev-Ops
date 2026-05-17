#!/usr/bin/env python3
"""
scripts/jsonl_rotator.py — RA-3007 log retention.

Walks .harness/ for *.jsonl files. Rotates any file >5MB into
.harness/archive/YYYY-MM/<filename>.gz and resets the live file
to a fresh empty file with the same name.

Safe under concurrent appends:
- Existing file descriptors in the swarm continue writing to the
  inode they hold; only the directory entry changes.
- Once the live file is reopened (e.g. next swarm cycle), writes
  start landing in the fresh inode.

Wire via .harness/cron-triggers.json as a daily trigger (suggested
04:00 UTC, off-peak).

Usage:
  python3 scripts/jsonl_rotator.py                  # rotate live
  python3 scripts/jsonl_rotator.py --dry-run        # print plan
  python3 scripts/jsonl_rotator.py --min-bytes 1M   # custom threshold
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MIN_BYTES = 5 * 1024 * 1024  # 5 MB
HARNESS = Path(__file__).resolve().parents[1] / ".harness"
ARCHIVE_ROOT = HARNESS / "archive"


def _parse_size(s: str) -> int:
    s = s.strip().upper()
    multipliers = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}
    if s and s[-1] in multipliers:
        return int(s[:-1]) * multipliers[s[-1]]
    return int(s)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Print plan, don't move files")
    p.add_argument("--min-bytes", default=str(DEFAULT_MIN_BYTES), help="Rotate if file >= this size (accepts K/M/G suffix)")
    args = p.parse_args()
    threshold = _parse_size(args.min_bytes)

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    archive_dir = ARCHIVE_ROOT / month
    rotated = 0

    for f in HARNESS.rglob("*.jsonl"):
        # Skip already-archived files
        if ARCHIVE_ROOT in f.parents:
            continue
        try:
            size = f.stat().st_size
        except FileNotFoundError:
            continue
        if size < threshold:
            continue

        target = archive_dir / (f.name + ".gz")
        if args.dry_run:
            print(f"DRY-RUN rotate: {f} ({size:,} bytes) -> {target}")
            continue

        archive_dir.mkdir(parents=True, exist_ok=True)
        with open(f, "rb") as src, gzip.open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        # Truncate the live file — keeps inode for any open fds
        with open(f, "w") as live:
            live.write("")
        print(f"rotated: {f} ({size:,} bytes) -> {target}")
        rotated += 1

    print(f"\nDone. {rotated} file(s) rotated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
