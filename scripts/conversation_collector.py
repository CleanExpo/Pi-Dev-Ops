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
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_claude_sessions import (  # noqa: E402
    find_jsonl, load_marker, parse_session, redact, render_digest, truncate)

log = logging.getLogger("pi-ceo.conversation_collector")

LAKE = Path.home() / ".claude" / "projects"
MARKER_PATH = Path.home() / ".claude" / ".conversation-sync-markers.json"
INGEST_PATH = "/api/conversations/ingest"
DEFAULT_API_URL = "https://pi-dev-ops-production.up.railway.app"
BATCH_SIZE = 25  # server caps a request at CONVERSATION_INGEST_MAX_ROWS (200)
TRUTHY = {"1", "true", "yes", "on"}
WIRE_FIELDS = ("project_dir", "title", "digest_md", "turn_count",
               "started_at", "last_activity_at")

# (url, headers, payload) -> (status, body); injected so tests never open a
# socket. Default implementation: urllib_poster.
Poster = Callable[[str, dict, dict], tuple[int, str]]


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


# ── Incremental marker ───────────────────────────────────────────────────────
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
    return rows, fresh


# ── Shipping ─────────────────────────────────────────────────────────────────
def urllib_poster(url: str, headers: dict, payload: dict) -> tuple[int, str]:
    """Default poster. Replaced in tests so no test can reach the network."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST", headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, (response.read() or b"").decode(errors="replace")[:400]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:400].decode(errors="replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)[:400]


def _payload(batch: list[dict]) -> dict:
    """Ingest envelope {machine, digests[]}. The server re-derives each row id
    as "<machine>:<session_id>"; one run collects one machine's sessions."""
    return {"machine": batch[0]["machine"], "digests": [
        {"session_id": row["id"].split(":", 1)[1], **{f: row[f] for f in WIRE_FIELDS}}
        for row in batch]}


def ship_rows(rows: list[dict], *, poster: Poster, url: str, secret: str) -> dict:
    """POST rows in batches. Returns counts and the first failure seen."""
    headers = {"Content-Type": "application/json", "X-Pi-CEO-Secret": secret}
    endpoint = f"{url.rstrip('/')}{INGEST_PATH}"
    sent = 0
    errors: list[str] = []
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        status, body = poster(endpoint, headers, _payload(batch))
        if 200 <= status < 300:
            sent += len(batch)
        else:
            errors.append(f"HTTP {status}: {body[:120]}")
            log.error("conversation-collector: batch failed — HTTP %s", status)
    return {"sent": sent, "batches": (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE, "errors": errors}


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
