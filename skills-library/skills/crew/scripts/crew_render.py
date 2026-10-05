#!/usr/bin/env python3
"""Terminal render of a /crew run, read from the evidence log. Offline; no network.

The property this file is built around: an absent run must not look like a broken one, and
neither may look like a healthy empty one. A renderer that draws all three the same way is
the failure the brief's verification step 3 exists to catch, so each state has its own
message and its own exit code:

  0  a run was found and rendered
  2  nothing to render, and the reason is named (no log / empty log / unknown session)
  3  the log exists but could not be parsed

Malformed lines are counted and reported rather than swallowed; a log that is half garbage
must say so, because the alternative is a confident render of partial evidence.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

LOG = Path.home() / ".claude" / "state" / "crew" / "runs.jsonl"

ROLES = ["scout", "planner", "builder", "verifier",
         "reviewer", "security", "ci-recovery", "release-monitor"]

GLYPH = {"start": "▶", "tool": "•", "done": "✓", "refused": "⊘", "error": "✗"}


def _parse_ts(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S%z")
    except (ValueError, TypeError):
        return None


def load(path):
    """Return (events, malformed_count). Raises FileNotFoundError if the log is absent."""
    events, malformed = [], 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError("not an object")
                events.append(obj)
            except (json.JSONDecodeError, ValueError):
                malformed += 1
    return events, malformed


def render(events, session_id):
    rows = [e for e in events if e.get("session_id") == session_id]
    starts = [e for e in rows if e.get("type") == "run_start"]
    header = f"/crew  session {session_id}"
    if starts:
        task = starts[0].get("fields", {}).get("task", "")
        grounding = starts[0].get("fields", {}).get("grounding", "")
        if task:
            header += f"  —  {task}"
        if grounding:
            header += f"\n  GROUNDING: {grounding}"
    out = [header, ""]

    for role in ROLES:
        rel = [e for e in rows if e.get("actor_role") == role]
        if not rel:
            out.append(f"  {'·':<2} {role:<16} not dispatched")
            continue
        last = rel[-1]
        kind = last.get("type", "?")
        glyph = GLYPH.get(kind, "?")
        ts_first = _parse_ts(rel[0].get("ts"))
        ts_last = _parse_ts(last.get("ts"))
        elapsed = ""
        if ts_first and ts_last:
            elapsed = f"{(ts_last - ts_first).total_seconds():.0f}s"
        detail = last.get("fields", {}).get("tool") or last.get("fields", {}).get("note") or ""
        out.append(f"  {glyph:<2} {role:<16} {kind:<10} {elapsed:>6}  {detail}")

    out.append("")
    out.append(f"  {len(rows)} event(s) for this session, {len(events)} in the log")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a /crew run from the evidence log.")
    ap.add_argument("--session", default=None, help="session id; default = most recent")
    ap.add_argument("--log", default=str(LOG))
    args = ap.parse_args()
    path = Path(args.log)

    if not path.exists():
        print(f"NO LOG at {path}", file=sys.stderr)
        print("Nothing has ever been recorded here. This is not an empty run — it is the "
              "absence of any run at all.", file=sys.stderr)
        return 2

    try:
        events, malformed = load(path)
    except OSError as exc:
        print(f"LOG UNREADABLE at {path}: {exc}", file=sys.stderr)
        return 3

    if malformed:
        print(f"WARNING: {malformed} malformed line(s) skipped in {path}", file=sys.stderr)

    if not events:
        print(f"LOG EMPTY at {path}", file=sys.stderr)
        print("The log exists and parses, and contains no events.", file=sys.stderr)
        return 2

    session = args.session
    if session is None:
        session = events[-1].get("session_id")

    known = {e.get("session_id") for e in events if e.get("session_id")}
    if session not in known:
        print(f"SESSION {session} NOT FOUND", file=sys.stderr)
        print(f"{len(known)} other session(s) are present: "
              f"{', '.join(sorted(str(s) for s in known)[:5])}", file=sys.stderr)
        return 2

    print(render(events, session))
    return 0


if __name__ == "__main__":
    sys.exit(main())
