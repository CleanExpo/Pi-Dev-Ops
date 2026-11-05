#!/usr/bin/env python3
"""HEADROOM events: known Claude/Codex/Cursor limit strings -> append-only JSONL (RA-8188, AR-02).

A night-lane job that hits an account limit prints one known line and stops. This reads
the end of that job's output, matches it against the strings below, and appends one JSON
line per event to the HEADROOM log on the Mini ops SSD, so the night-queue picker (AR-03)
can skip a cooling account instead of feeding it jobs that will fail.

It never stores what the CLI printed: a record holds a fixed set of keys built here
(event, pattern id, parsed reset time). It never signs in, out or touches credentials.

Where each string was seen (5 Nov 2026, emails redacted):
- cursor.*: `turn_ended` errors in ~/.cursor/projects/*/agent-transcripts on the Mini.
- claude.quota: the 06/10 weekly-limit incident (RA-7930, tests/test_mesh_quota_hold.py).
- claude.login_expired / claude.oauth_expired / claude.org_disabled: ops/SHARED-KNOWLEDGE.md.
- codex.workspace_credits: an expired Codex OAuth token, NOT a billing fact
  (context-cockpit/references/release-incidents-202608-09.md). Never buy credits on it.
- codex.quota: no live sample found on the Mini, so its events say source=unverified.

Log path: $HEADROOM_LOG, else DEFAULT_LOG (a design default; AR-01's map names none).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows; the night lanes run on macOS
    fcntl = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mesh import quota  # noqa: E402

SCHEMA = "headroom/1"
DEFAULT_LOG = "/Volumes/Mini Mini 2T Storage/ops/headroom/headroom-events.jsonl"
EVENTS = ("5h_cooling", "weekly_cooling", "auth_expired", "billing_blocked", "on_demand_capped")
PROVIDERS = ("claude", "codex", "cursor")
MACHINES = ("mini", "macbook", "pc")  # ops/ACCOUNT-MAP.yaml machine ids (AR-01)
TAIL_LINES = 60
TAIL_BYTES = 65536
MAX_LINE = 400
LOCK_WAIT_S = 5.0  # a stuck lock fails the write; it never holds up the job
EXIT_WRITE_FAILED = 3
EXIT_READ_FAILED = 4
# `claude -p` exits non-zero on these messages, so a clean Claude exit is a job that only
# quoted one. `codex exec` exits 0 on its usage limit, so Codex output is always read.
SCAN_ON_CLEAN_EXIT = {"claude": False, "codex": True, "cursor": True}

_QUOTA = (r"(?:claude(?: ai)? )?(?:you've |you have )?"
          r"(?:hit your (?:[\w-]+ )*limit|(?:5-hour |weekly |session |usage )?(?:usage )?limit reached)")


@dataclass(frozen=True)
class Pattern:
    id: str
    provider: str
    event: str
    regex: re.Pattern
    source: str
    quota: bool = False  # reads a reset time; "weekly" in the line makes it weekly_cooling


def _p(pid, provider, event, rx, source="observed", quota_=False):
    return Pattern(pid, provider, event, re.compile(rx, re.I), source, quota_)


PATTERNS = (
    _p("cursor.spend_limit", "cursor", "on_demand_capped",
       r"you've hit your usage limit\b.*\bspend limit to continue"),
    _p("cursor.free_plan", "cursor", "billing_blocked", r"you've hit your usage limit\b.*\bget cursor pro\b"),
    _p("claude.org_disabled", "claude", "billing_blocked", r"your organization has disabled claude subscription access"),
    _p("claude.oauth_expired", "claude", "auth_expired", r"oauth session expired"),
    _p("claude.login_expired", "claude", "auth_expired", r"login expired\b.*please run /login"),
    _p("codex.workspace_credits", "codex", "auth_expired", r"your workspace is out of credits"),
    _p("claude.quota", "claude", "5h_cooling", _QUOTA, quota_=True),
    _p("codex.quota", "codex", "5h_cooling", _QUOTA, "unverified", quota_=True),
)

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_NEWLINE = re.compile(r"\r\n|\r|\n")  # not str.splitlines: \u2028, \x0c etc. are not line starts
_LEAD = re.compile(r"^(?:⎿\s*)?(?:(?:api\s+)?error:\s*)?", re.I)
_TICKET = re.compile(r"^[A-Za-z]{2,10}-\d{1,6}$")


def _candidates(text: str, provider: str) -> Iterator[str]:
    """The last TAIL_LINES lines, cleaned, with a JSON `error` field read as its line.

    Only a line that STARTS with a known message counts (after an optional `Error:`
    or `API Error:`), so a report quoting one mid-sentence or in a bullet does not.
    JSON `error` fields are read only for Cursor, whose `agent` CLI reports limits that way."""
    for raw in _NEWLINE.split(text)[-TAIL_LINES:]:
        line = _ANSI.sub("", raw).strip()
        if provider == "cursor" and line.startswith("{"):
            try:
                obj = json.loads(line)
            except ValueError:
                obj = None
            if isinstance(obj, dict) and isinstance(obj.get("error"), str):
                line = obj["error"].strip()
        line = _LEAD.sub("", line.replace("’", "'"), count=1)
        if 0 < len(line) <= MAX_LINE:
            yield line


def classify(text: str, provider: str, now: float, exit_code: Optional[int] = None) -> list[dict]:
    """Events in the end of one job's output: [{event, pattern_id, source, reset_at}]. Pure.

    One event per pattern however often the line repeats. reset_at is epoch seconds
    when the line prints a readable reset, else None (never a guessed default)."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; expected one of {PROVIDERS}")
    if exit_code == 0 and not SCAN_ON_CLEAN_EXIT[provider]:
        return []
    hits: dict[str, dict] = {}
    mine = [p for p in PATTERNS if p.provider == provider]
    for line in _candidates(text or "", provider):
        p = next((p for p in mine if p.regex.match(line)), None)
        if p is None or p.id in hits:
            continue
        event = "weekly_cooling" if p.quota and "weekly" in line.lower() else p.event
        reset = quota.read_reset(line, now) if p.quota else None
        hits[p.id] = {"event": event, "pattern_id": p.id, "source": p.source, "reset_at": reset}
    return list(hits.values())


def _iso(epoch: Optional[float]) -> Optional[str]:
    return None if epoch is None else datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def _hashed(name: str) -> str:
    return "sha256:" + hashlib.sha256(name.encode("utf-8", "replace")).hexdigest()[:12]


def _machine_id(name: str) -> str:
    """A known ACCOUNT-MAP machine id as-is; anything else only as a short hash."""
    low = (name or "").strip().lower()
    return low if low in MACHINES else _hashed(name or "")


def _job_id(name: Optional[str]) -> Optional[str]:
    """A ticket-style job name (RA-8188) as-is, upper-cased; anything else only as a short hash.

    Names come from the caller, so they are metadata, not free text: a token-shaped
    directory name must never reach the shared log."""
    if not name:
        return None
    base = Path(name).name
    return base.upper() if _TICKET.match(base) else _hashed(base)


def build_record(hit: dict, *, machine: str, provider: str, job: Optional[str],
                 exit_code: Optional[int], now: float) -> dict:
    """The JSONL record: a fixed key set, every value built here, no CLI text."""
    return {"schema": SCHEMA, "ts": _iso(now), "machine": _machine_id(machine), "provider": provider,
            "event": hit["event"], "pattern_id": hit["pattern_id"], "source": hit["source"],
            "reset_at": _iso(hit["reset_at"]), "exit_code": exit_code, "job": _job_id(job)}


def append_events(records: list[dict], path: Path) -> None:
    """Append one JSON line per record. Raises OSError when the log volume is not there.

    Creates only the last directory (headroom/), never its parents, so an unmounted ops
    SSD fails loudly instead of growing a fake folder under /Volumes."""
    if not records:
        return
    if not path.is_absolute():
        raise OSError(f"log path must be absolute, got {path}")
    path.parent.mkdir(exist_ok=True)
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records).encode()
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        _lock(fd)
        _write_all(fd, data)
    finally:
        os.close(fd)


def _write_all(fd: int, data: bytes) -> None:
    """Write every byte; a short write is continued, a write that makes no progress raises."""
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        if n <= 0:
            raise OSError("log write made no progress")
        view = view[n:]


def _lock(fd: int) -> None:
    """Take the log's exclusive lock, or raise OSError after LOCK_WAIT_S."""
    if fcntl is None:
        return
    deadline = time.monotonic() + LOCK_WAIT_S
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise OSError(f"log lock still held after {LOCK_WAIT_S:g}s") from None
            time.sleep(0.05)


def default_machine() -> str:
    """$HEADROOM_MACHINE, else the ACCOUNT-MAP machine id this host name implies."""
    host = os.environ.get("HEADROOM_MACHINE") or socket.gethostname()
    low = host.lower()
    return "mini" if "mac-mini" in low else "macbook" if "macbook" in low else host


def _read_tail(path: Path) -> str:
    """The last TAIL_BYTES of a file, minus the first line when the cut lands inside it."""
    with open(path, "rb") as f:
        start = max(0, f.seek(0, 2) - TAIL_BYTES)
        f.seek(start)
        data = f.read()
    if start:
        data = data[data.find(b"\n") + 1:] if b"\n" in data else b""
    return data.decode(errors="replace")


def _parse(argv: Optional[list[str]]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="scan one job's output and append HEADROOM events")
    s.add_argument("output", type=Path, help="the job's captured CLI output (e.g. claude.out)")
    s.add_argument("--provider", required=True, choices=PROVIDERS)
    s.add_argument("--machine", default=None, help="ACCOUNT-MAP machine id (default: from host name)")
    s.add_argument("--job", default=None, help="job name recorded with the event")
    s.add_argument("--exit-code", type=int, default=None, help="the CLI's exit code, if known")
    s.add_argument("--log", type=Path, default=None, help="override $HEADROOM_LOG / the default path")
    return ap.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    a = _parse(argv)
    log = a.log or Path(os.environ.get("HEADROOM_LOG") or DEFAULT_LOG)
    now = time.time()
    try:
        text = _read_tail(a.output)
    except OSError as e:
        print(f"headroom: cannot read {a.output}: {e.strerror or e}", file=sys.stderr)
        return EXIT_READ_FAILED
    hits = classify(text, a.provider, now, a.exit_code)
    if not hits:
        print(f"headroom: no limit message in the last {TAIL_LINES} lines of {a.output.name}")
        return 0
    recs = [build_record(h, machine=a.machine or default_machine(), provider=a.provider,
                         job=a.job, exit_code=a.exit_code, now=now) for h in hits]
    try:
        append_events(recs, log)
    except OSError as e:
        print(f"headroom: cannot write {log}: {e.strerror or e}", file=sys.stderr)
        return EXIT_WRITE_FAILED
    said = ", ".join(f"{r['provider']} {r['event']} ({r['pattern_id']})" for r in recs)
    print(f"headroom: wrote {len(recs)} event(s) to {log}: {said}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
