#!/usr/bin/env python3
"""conversation_collector.py — Milestone 3, the per-machine client half.

The user runs Claude Code on three machines. Each machine's transcripts live
only in its own ``~/.claude/projects/**/*.jsonl`` lake, so no machine can see
what the others did. This collector is the shipper: it walks the local lake,
renders the SAME redacted digest ``scripts/sync_claude_sessions.py`` already
produces for the vault, and POSTs those digests to the shared conversation API.

RAW JSONL NEVER LEAVES THE MACHINE. Only ``render_digest`` output — itself
already redacted field by field — is shipped, and it is passed through
``redact`` once more here (the function is idempotent) so a field the renderer
copies verbatim, such as project/branch, cannot carry a secret off the box. The
server runs a second, independent pass.

Incremental marker (``~/.claude/.conversation-sync-markers.json``): one entry
per session file holding ``mtime`` and ``size``, not a content hash — a stat()
is O(1) while hashing re-reads the whole lake every run, and Claude Code only
appends to a session file, so any new turn moves both numbers. The format is
JSON Lines, written atomically via ``.tmp`` + ``os.replace``, so a torn file
costs the damaged line rather than the whole history: the MacBook drops offline
mid-session and rejoins later, and re-shipping months of digests over one
truncated line is the failure this avoids.

``--dry-run`` plans; a real run needs ``CONVERSATION_SYNC_ENABLED=1``.
Exit 0 ok · 2 lake missing · 3 refused · 4 delivery failed · 1 unknown status.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_claude_sessions import (  # noqa: E402
    find_jsonl, parse_session, redact, render_digest, truncate)

log = logging.getLogger("pi-ceo.conversation_collector")

# Incremental-sync state lives in its own module; re-exported here so the
# existing call sites and the tests that monkeypatch them keep working.
from scripts.conversation_markers import (  # noqa: E402
    MARKER_PATH,
    is_unchanged,
    load_markers,
    marker_entry,
    save_markers,
)

LAKE = Path.home() / ".claude" / "projects"
DEFAULT_API_URL = "https://pi-dev-ops-production.up.railway.app"
TRUTHY = {"1", "true", "yes", "on"}

# (url, headers, payload) -> (status, body); injected so tests never open a
# socket. Default implementation: urllib_poster.


def machine_name() -> str:
    """Short hostname used as the machine axis of every row id."""
    return socket.gethostname().split(".")[0]


def _from_env_file(name: str) -> str:
    """Read one key from ~/.hermes/.env without executing it (mesh/runner.py:28)."""
    envf = Path.home() / ".hermes" / ".env"
    if not envf.exists():
        return ""
    try:
        for raw in envf.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        return ""
    return ""


def api_url() -> str:
    """Base URL of the shared Pi-CEO API."""
    return os.environ.get("PI_CEO_API_URL") or _from_env_file("PI_CEO_API_URL") or DEFAULT_API_URL


def api_secret() -> str:
    """Shared-secret header value. Machines hold this, never a Supabase key."""
    return os.environ.get("PI_CEO_API_KEY") or _from_env_file("PI_CEO_API_KEY")


def sync_enabled() -> bool:
    """Real (posting) runs are opt-in per machine; default OFF."""
    return os.environ.get("CONVERSATION_SYNC_ENABLED", "").strip().lower() in TRUTHY


# ── Row building ─────────────────────────────────────────────────────────────
def _iso(epoch: float) -> str:
    """UTC ISO-8601 for a filesystem timestamp."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def build_row(path: Path, machine: str) -> dict | None:
    """Render one shippable, redacted row. None when the file holds no turns."""
    sess = parse_session(path)
    if not sess:
        return None
    session_id = path.stem
    title = truncate(redact(sess["intent"]), 140) or f"session {session_id[:8]}"
    try:
        last_activity = _iso(path.stat().st_mtime)
    except OSError:
        last_activity = ""
    return {
        "id": f"{machine}:{session_id}",
        "machine": machine,
        # Redacted despite being a directory name: cwd paths leak usernames.
        "project_dir": redact(sess["project"] or path.parent.name),
        "title": title,
        # Second pass over the document: redact() is idempotent, so this is
        # free insurance over any field render_digest copies verbatim.
        "digest_md": redact(render_digest(sess, session_id)),
        "turn_count": sess["n_user"] + sess["n_asst"],
        "started_at": sess["ts"] or "",
        "last_activity_at": last_activity,
    }


def collect_rows(
    root: Path, markers: dict[str, dict], *, limit: int = 0, machine: str = ""
) -> tuple[list[dict], dict[str, dict]]:
    """Walk the lake and return (rows to ship, marker entries for those files)."""
    machine = machine or machine_name()
    rows: list[dict] = []
    fresh: dict[str, dict] = {}
    for path in find_jsonl(root):
        if limit and len(rows) >= limit:
            break
        if is_unchanged(path, markers):
            continue
        try:
            entry = marker_entry(path)
        except OSError:
            continue
        row = build_row(path, machine)
        # Empty transcripts still get a marker: nothing to ship, nothing to retry.
        fresh[str(path)] = entry
        if row:
            rows.append(row)
    return _dedupe_by_id(rows), fresh


def _dedupe_by_id(rows: list[dict]) -> list[dict]:
    """Collapse rows sharing an id, keeping the most recently active.

    The id is "<machine>:<session_id>" and session_id is the JSONL filename stem,
    so the same session appearing under two project directories — a worktree, a
    copied or renamed checkout — yields two rows with the SAME id. Postgres
    refuses that: an upsert whose payload hits one row twice fails the whole
    statement with "ON CONFLICT DO UPDATE command cannot affect row a second
    time". One duplicate would therefore reject an entire batch of up to
    BATCH_SIZE digests, not just itself.

    Newest wins, because the two copies are the same conversation and the later
    last_activity_at is the more complete transcript. Rows without the field sort
    first, so a row that has one always beats a row that does not.
    """
    by_id: dict[str, dict] = {}
    for row in rows:
        prior = by_id.get(row["id"])
        if prior is None or (row.get("last_activity_at") or "") >= (
            prior.get("last_activity_at") or ""
        ):
            by_id[row["id"]] = row
    if len(by_id) != len(rows):
        log.warning(
            "conversation-collector: collapsed %d duplicate session id(s) — "
            "the same session appears under more than one project directory",
            len(rows) - len(by_id),
        )
    return list(by_id.values())


# Shipping lives in its own module; re-exported so existing call sites and the
# tests that monkeypatch them keep working.
from conversation_shipper import (  # noqa: E402
    BATCH_SIZE,  # noqa: F401 — re-exported for callers and tests
    INGEST_PATH,  # noqa: F401
    Poster,  # noqa: F401
    WIRE_FIELDS,  # noqa: F401
    _accounting,  # noqa: F401
    _payload,  # noqa: F401
    ship_rows,
    urllib_poster,  # noqa: F401
)


def run(
    *,
    root: Path = LAKE,
    marker_path: Path = MARKER_PATH,
    limit: int = 0,
    dry_run: bool = False,
    poster: Poster | None = None,
    machine: str = "",
    enabled: bool | None = None,
) -> dict:
    """Collect, ship and record one pass over the local lake."""
    if not root.exists():
        return {"status": "no-lake", "root": str(root), "candidates": 0, "sent": 0}
    markers = load_markers(marker_path)
    rows, fresh = collect_rows(root, markers, limit=limit, machine=machine)
    summary = {"status": "ok", "candidates": len(rows), "sent": 0, "errors": []}
    if dry_run:
        summary["status"] = "dry-run"
        return summary
    if not (sync_enabled() if enabled is None else enabled):
        summary["status"] = "disabled"
        return summary
    secret = api_secret()
    if not secret:
        summary["status"] = "no-credential"
        return summary
    result = ship_rows(rows, poster=poster or urllib_poster, url=api_url(), secret=secret)
    summary.update(sent=result["sent"], errors=result["errors"])
    if result["errors"]:
        # Partial failure: keep the un-acked files unmarked so they retry.
        summary["status"] = "partial"
        return summary
    markers.update(fresh)
    save_markers(markers, marker_path)
    return summary


def main() -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ship redacted Claude session digests")
    ap.add_argument("--dry-run", action="store_true", help="plan only; no POST, no marker write")
    ap.add_argument("--limit", type=int, default=0, help="cap rows collected (0 = all)")
    ap.add_argument("--lake", default=str(LAKE), help="override the lake root")
    args = ap.parse_args()
    summary = run(root=Path(args.lake).expanduser(), limit=args.limit, dry_run=args.dry_run)
    print(json.dumps(summary))
    # One code for partial and total failure: run() returns before save_markers(),
    # so nothing committed either way. Unmapped statuses exit 1, never a silent 0.
    return {"ok": 0, "dry-run": 0, "no-lake": 2, "disabled": 3,
            "no-credential": 3, "partial": 4}.get(summary["status"], 1)


if __name__ == "__main__":
    sys.exit(main())
