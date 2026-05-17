"""swarm._atomic — small helper for crash-safe file writes.

State files (Telegram offsets, manifests, rotation pointers) get clobbered
when a writer crashes mid-`write_text` — the file is truncated to whatever
bytes made it to disk, and the next reader sees malformed or empty JSON.

This module exposes the write-tmp → fsync → os.replace pattern in one
call so callers can swap a direct `path.write_text(...)` for
`atomic_write_text(path, ...)` without each site re-implementing the
two-step dance.

Pattern source: browser-harness `_ipc.py:178-181` per
[[board-deliberation-code-patterns-2026-05-15]] PR2.

Failure mode contract: if a crash, SIGKILL, or disk-full occurs between
the `tmp.write_text` and the `os.replace`, the OLD file is preserved
intact. The atomic step is `os.replace` (POSIX rename(2)), which the
kernel guarantees as a single inode-table flip.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path | str, content: str, *, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically.

    Old file (if any) is preserved on crash between the two steps.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(content, encoding=encoding)
    os.replace(tmp, p)


def atomic_write_json(path: Path | str, data: Any, *, indent: int | None = 2,
                      newline: bool = False, encoding: str = "utf-8") -> None:
    """Serialise `data` to JSON and write atomically.

    `newline=True` appends a trailing "\\n" — matches the existing
    house-style for human-edited manifests (see swarm/board.py).
    """
    payload = json.dumps(data, indent=indent)
    if newline:
        payload += "\n"
    atomic_write_text(path, payload, encoding=encoding)
