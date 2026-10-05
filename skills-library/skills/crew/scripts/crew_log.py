#!/usr/bin/env python3
"""Append-only evidence log for /crew runs.

Two properties this file exists to guarantee, both of them findings from the brief's
challenge rounds:

1. Concurrent appends do not interleave. Eight roles fan out in parallel and more than one
   /crew can run at once, so every write takes an exclusive flock, appends one
   newline-terminated line under O_APPEND, and releases. An evidence log that corrupts under
   load is worse than no log: it fails silently and still looks fine.

2. The Pi-CEO mirror is optional and is NEVER created. When ~/Pi-CEO/.harness/swarm/ exists
   the line is mirrored there so the existing dashboard can consume it later with no rework.
   When it does not exist the mirror is skipped and the skip is recorded in the returned
   status -- it is not an error, and the directory is not conjured. Creating it on a machine
   with no Pi-CEO checkout would fabricate harness state for a harness that is not installed.
   The challenge round offered both branches; this is the skip branch, implemented and tested
   rather than merely implied by prose.
"""
import argparse
import fcntl
import json
import os
import sys
import time
from pathlib import Path

PRIMARY = Path.home() / ".claude" / "state" / "crew" / "runs.jsonl"
MIRROR_DIR = Path.home() / "Pi-CEO" / ".harness" / "swarm"
MIRROR = MIRROR_DIR / "runs.jsonl"

# Acquiring the lock can contend with up to N writers. Block rather than spin, but do not
# block forever -- a stuck writer must degrade to a reported failure, not a hung dispatch.
LOCK_TIMEOUT_S = 10.0
LOCK_POLL_S = 0.02


def _append_locked(path: Path, line: str) -> None:
    """Append one line to path under an exclusive lock. Raises on timeout.

    Two mechanisms, and it is worth being precise about which does the work, because the
    obvious answer is wrong. The atomicity of a whole record comes from O_APPEND: the kernel
    couples the seek-to-end and the write, so concurrent appenders cannot land on top of one
    another. Measured on APFS, records of 300 KB still arrive intact with the lock removed.

    The lock earns its place on the path below: os.write may write FEWER bytes than asked, so
    a correct writer must loop, and the moment a record takes more than one syscall the
    O_APPEND guarantee no longer covers the whole line. The lock is what keeps a resumed
    write from being split by another writer's append, and it is also what holds on
    filesystems where O_APPEND is not atomic at all (NFS). Neither mechanism is redundant;
    they cover different halves.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        deadline = time.monotonic() + LOCK_TIMEOUT_S
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"could not lock {path} within {LOCK_TIMEOUT_S}s")
                time.sleep(LOCK_POLL_S)
        try:
            payload = line.encode("utf-8")
            written = 0
            while written < len(payload):
                n = os.write(fd, payload[written:])
                if n <= 0:
                    raise OSError(f"append to {path} stalled after {written} bytes")
                written += n
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def emit(event: dict) -> dict:
    """Write one event. Returns a status describing what actually happened."""
    record = {
        "ts": event.get("ts") or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "type": event["type"],
        "actor_role": event.get("actor_role"),
        "session_id": event.get("session_id"),
        "fields": event.get("fields") or {},
    }
    line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"

    _append_locked(PRIMARY, line)
    status = {"primary": str(PRIMARY), "mirrored": False, "mirror_skipped_reason": None}

    # The mirror is best-effort and never created. Absence is a normal state, not a fault.
    if MIRROR_DIR.is_dir():
        try:
            _append_locked(MIRROR, line)
            status["mirrored"] = True
        except OSError as exc:
            # A present-but-unwritable mirror must not take the run down with it; the
            # primary log is the evidence of record.
            status["mirror_skipped_reason"] = f"unwritable: {exc}"
    else:
        status["mirror_skipped_reason"] = "absent"
    return status


def main() -> int:
    ap = argparse.ArgumentParser(description="Append one /crew evidence event.")
    ap.add_argument("--type", required=True)
    ap.add_argument("--role", default=None)
    ap.add_argument("--session", default=None)
    ap.add_argument("--field", action="append", default=[], metavar="K=V")
    args = ap.parse_args()

    fields = {}
    for pair in args.field:
        k, _, v = pair.partition("=")
        fields[k] = v

    try:
        status = emit({
            "type": args.type,
            "actor_role": args.role,
            "session_id": args.session,
            "fields": fields,
        })
    except (TimeoutError, OSError) as exc:
        # A dropped record must be loud and legible. Raising through as a traceback reads as
        # a crashed dispatcher; a named failure with a non-zero exit lets the caller record
        # that the evidence log lost this event rather than assume it landed.
        print(json.dumps({"error": str(exc), "written": False}, sort_keys=True),
              file=sys.stderr)
        return 1
    print(json.dumps(status, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
