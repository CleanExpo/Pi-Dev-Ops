"""Per-provider ingest activity probe — read-only.

Phase C / C1. Powers GET /api/nexus/ingest/health. Reads the
outcomes store and groups by source to produce a small per-provider
status summary. No row content surfaces — only counts + timestamps.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .outcomes import OutcomesStore

KNOWN_SOURCES = ("stripe", "vercel", "posthog", "sentry", "linear", "manual")
PROBE_LIMIT = 1000  # bounded scan; aggregations only


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def compute_ingest_health(outcomes_store: OutcomesStore) -> dict:
    """Return {'providers': {source: {last_seen_at, count_24h, count_7d}}}."""
    rows = outcomes_store.list(limit=PROBE_LIMIT)
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    providers: dict[str, dict] = {
        s: {"last_seen_at": None, "count_24h": 0, "count_7d": 0}
        for s in KNOWN_SOURCES
    }

    for row in rows:
        source = getattr(row, "source", None)
        if source not in providers:
            continue
        captured = _parse_iso(getattr(row, "captured_at", None))
        if captured is None:
            continue
        bucket = providers[source]
        prev_last = _parse_iso(bucket["last_seen_at"])
        if prev_last is None or captured > prev_last:
            bucket["last_seen_at"] = captured.isoformat()
        if captured >= cutoff_7d:
            bucket["count_7d"] += 1
        if captured >= cutoff_24h:
            bucket["count_24h"] += 1

    return {
        "providers": providers,
        "as_of": now.isoformat(),
        "scan_limit": PROBE_LIMIT,
    }
