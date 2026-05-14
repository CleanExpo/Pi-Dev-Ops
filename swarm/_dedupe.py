"""swarm/_dedupe.py — shared content-hash dedupe for cron generators.

Every autonomous Linear-ticket generator (project_health_monitor,
production_coordinator, enhancement_scout) calls this BEFORE filing.

Pattern:
    from swarm._dedupe import already_filed, record_filed, content_hash
    h = content_hash(title, body)
    existing = already_filed("scout", h)
    if existing:
        log.info("skip dupe %s", h)
        return
    create_linear_ticket(...)
    record_filed("scout", h, linear_identifier)

Rolling window: 14 days. State persisted at .harness/swarm/dedupe_<generator>.jsonl
(append-only). Reads only the last 14 days on each check (fast even at scale).

Root-cause fix for the 2,500-duplicate flood: the three cron generators
re-filed identical tickets every cycle because nothing checked whether
equivalent content already existed. This module is the gate.
"""

from __future__ import annotations
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("swarm.dedupe")

_STATE_DIR = Path(__file__).resolve().parents[1] / ".harness" / "swarm"
_WINDOW_DAYS = 14


def content_hash(title: str, body: str = "") -> str:
    """Stable 16-char content hash. Normalises whitespace and case in title;
    uses first 500 chars of body. Stable across cron cycles for identical content.

    Behaviour notes:
      * Title is lowercased and whitespace-collapsed — "Foo  Bar" and
        "foo bar" produce the same hash. This is intentional because the
        generators format titles with slightly different spacing across
        cycles (e.g. "[WorkOrder] pi-dev-ops — ci_failing" vs the same
        with a trailing newline).
      * Body is truncated to 500 chars before normalising. Cron generators
        regenerate timestamps inside descriptions on every cycle — keeping
        only the first 500 chars stabilises the hash against that drift.
    """
    norm_title = " ".join((title or "").lower().strip().split())
    norm_body = " ".join((body or "")[:500].lower().strip().split())
    raw = f"{norm_title}|{norm_body}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _state_path(generator: str) -> Path:
    return _STATE_DIR / f"dedupe_{generator}.jsonl"


def _load_recent(generator: str) -> dict[str, str]:
    """Return {hash: linear_id} for entries newer than _WINDOW_DAYS."""
    p = _state_path(generator)
    if not p.exists():
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=_WINDOW_DAYS)
    out: dict[str, str] = {}
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                ts = datetime.fromisoformat(row["filed_at"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    out[row["hash"]] = row.get("linear_id", "")
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                log.warning("dedupe state row skipped: %s", e)
    except Exception as e:  # noqa: BLE001
        log.warning("dedupe state read failed (treating as empty): %s", e)
    return out


def already_filed(generator: str, content_hash_value: str) -> Optional[str]:
    """Returns the existing linear_id if already filed in window, else None.

    Empty string is a valid linear_id (when backfilled without an
    identifier) — callers should check `is not None`, not truthiness.
    """
    recent = _load_recent(generator)
    return recent.get(content_hash_value)


def record_filed(generator: str, content_hash_value: str, linear_id: str) -> None:
    """Append-only record. Safe under concurrent cron (each generator runs solo).

    Writes a single JSONL line with the current UTC timestamp. The state
    file is created lazily on first call.
    """
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "hash": content_hash_value,
        "linear_id": linear_id,
        "filed_at": datetime.now(timezone.utc).isoformat(),
    }
    with _state_path(generator).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


__all__ = ["content_hash", "already_filed", "record_filed"]
