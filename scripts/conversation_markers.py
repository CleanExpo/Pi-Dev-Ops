#!/usr/bin/env python3
"""conversation_markers.py — incremental-sync state for the conversation collector.

Extracted from `scripts/conversation_collector.py`, which sat at exactly the
300-line ceiling. This is a real seam rather than a slice taken to make room:
deciding *which files have already been shipped* is a separate concern from
reading transcripts, building rows and posting them, and it is the half with the
durability requirements — atomic replace, and per-line damage isolation.

The marker file is JSONL, one self-contained record per line, so a truncated
write (the MacBook closing mid-flush) costs the damaged line rather than the
whole history. A whole-file JSON object would make one bad byte re-ship every
session ever recorded.

`load_markers` still falls back to the pre-JSONL whole-file format via
`sync_claude_sessions.load_marker`, so an existing install keeps its state on
first run instead of silently re-shipping months of digests.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from scripts.sync_claude_sessions import load_marker

log = logging.getLogger("pi-ceo.conversation-collector")

MARKER_PATH = Path.home() / ".claude" / ".conversation-sync-markers.json"


def marker_entry(path: Path) -> dict:
    """Freshness fingerprint of one session file: mtime + size."""
    st = path.stat()
    return {"mtime": st.st_mtime, "size": st.st_size}


def load_markers(path: Path) -> dict[str, dict]:
    """Load the marker map line by line, so damage costs one entry not all."""
    markers: dict[str, dict] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return markers
    for line in lines:
        try:
            rec = json.loads(line) if line.strip() else {}
        except ValueError:
            log.warning("conversation-collector: dropping corrupt marker line")
            continue
        key = rec.get("path") if isinstance(rec, dict) else None
        if key:
            markers[key] = {"mtime": rec.get("mtime"), "size": rec.get("size")}
    if markers:
        return markers
    # Pre-JSONL format: one whole-file {path: {...}} object.
    return {k: v for k, v in load_marker(path).items() if isinstance(v, dict)}


def save_markers(markers: dict[str, dict], path: Path) -> None:
    """Atomically write the marker map as one self-contained record per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(
        json.dumps({"path": key, "mtime": val.get("mtime"), "size": val.get("size")})
        for key, val in sorted(markers.items())
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body + "\n" if body else "", encoding="utf-8")
    os.replace(tmp, path)


def is_unchanged(path: Path, markers: dict[str, dict]) -> bool:
    """True when this file matches its marker and can be skipped."""
    seen = markers.get(str(path))
    if not seen:
        return False
    try:
        return marker_entry(path) == {"mtime": seen.get("mtime"), "size": seen.get("size")}
    except OSError:
        return False
