"""
gc.py — Workspace garbage collection.

collect_garbage() removes workspaces for terminal sessions older than
GC_MAX_AGE seconds. Also scans WORKSPACE_ROOT for orphan directories
(on disk but not in _sessions) and removes those too.

Runs every 30 minutes as a background asyncio task started during
server startup. Also exposed as POST /api/gc for manual triggers.
"""
import asyncio
import os
import shutil
import time
from . import config
from . import persistence

_TERMINAL_STATUSES = {"complete", "failed", "killed", "interrupted"}
_GC_LOOP_INTERVAL = 1800  # 30 minutes


def collect_garbage(sessions: dict) -> dict:
    """
    Remove stale workspaces and orphan directories.

    Args:
        sessions: the live _sessions dict from sessions.py

    Returns:
        {"removed": N, "skipped": N, "errors": N}
    """
    now = time.time()
    removed = 0
    skipped = 0
    errors = 0

    # 1. Collect terminal sessions older than GC_MAX_AGE
    to_remove = []
    for sid, session in list(sessions.items()):
        if session.status not in _TERMINAL_STATUSES:
            skipped += 1
            continue
        age = now - (session.started_at or 0)
        if age < config.GC_MAX_AGE:
            skipped += 1
            continue
        to_remove.append(sid)

    for sid in to_remove:
        session = sessions.pop(sid, None)
        if session and session.workspace and os.path.exists(session.workspace):
            try:
                shutil.rmtree(session.workspace, ignore_errors=True)
                removed += 1
            except Exception:
                errors += 1
        persistence.delete_session_file(sid)

    # 2. Scan WORKSPACE_ROOT for orphan directories not in sessions
    if os.path.isdir(config.WORKSPACE_ROOT):
        known_ids = set(sessions.keys())
        for entry in os.listdir(config.WORKSPACE_ROOT):
            full = os.path.join(config.WORKSPACE_ROOT, entry)
            if not os.path.isdir(full):
                continue
            if entry in known_ids:
                continue
            # Only remove if old enough (avoids nuking a session being created)
            try:
                mtime = os.path.getmtime(full)
                if now - mtime > config.GC_MAX_AGE:
                    shutil.rmtree(full, ignore_errors=True)
                    removed += 1
            except Exception:
                errors += 1

    return {"removed": removed, "skipped": skipped, "errors": errors}


async def gc_loop(sessions: dict) -> None:
    """Background task: run collect_garbage every 30 minutes."""
    import logging
    _log = logging.getLogger("pi-ceo.gc")
    while True:
        await asyncio.sleep(_GC_LOOP_INTERVAL)
        result = collect_garbage(sessions)
        if result["removed"] > 0:
            _log.info("GC removed=%d workspaces errors=%d", result["removed"], result["errors"])
