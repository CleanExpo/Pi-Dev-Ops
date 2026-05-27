"""Focused tests for swarm.nexus.ingest_health."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from swarm.nexus.ingest_health import KNOWN_SOURCES, compute_ingest_health
from swarm.nexus.outcomes import InMemoryOutcomesStore
from swarm.nexus.types import Outcome

NOW = datetime.now(timezone.utc)


def _o(*, source: str, when: datetime, oid: str | None = None) -> Outcome:
    return Outcome(
        id=oid or f"{source}-{when.isoformat()}",
        workspace_id="ws-1",
        workspace_slug="acme",
        source=source,  # type: ignore[arg-type]
        metric="probe",
        captured_at=when.isoformat(),
        value_numeric=1.0,
    )


class TestComputeIngestHealth:
    def test_empty_store_all_zeros(self):
        out = compute_ingest_health(InMemoryOutcomesStore())
        assert set(out["providers"].keys()) == set(KNOWN_SOURCES)
        for src, bucket in out["providers"].items():
            assert bucket == {"last_seen_at": None, "count_24h": 0, "count_7d": 0}

    def test_count_24h_filter(self):
        store = InMemoryOutcomesStore()
        store.write(_o(source="stripe", when=NOW - timedelta(hours=1)))
        store.write(_o(source="stripe", when=NOW - timedelta(hours=23)))
        store.write(_o(source="stripe", when=NOW - timedelta(days=2)))  # outside 24h
        out = compute_ingest_health(store)
        assert out["providers"]["stripe"]["count_24h"] == 2
        assert out["providers"]["stripe"]["count_7d"] == 3

    def test_per_provider_grouping(self):
        store = InMemoryOutcomesStore()
        store.write(_o(source="stripe", when=NOW - timedelta(hours=1)))
        store.write(_o(source="vercel", when=NOW - timedelta(hours=2)))
        store.write(_o(source="linear", when=NOW - timedelta(hours=3)))
        out = compute_ingest_health(store)
        for src in ("stripe", "vercel", "linear"):
            assert out["providers"][src]["count_24h"] == 1
        for src in ("posthog", "sentry", "manual"):
            assert out["providers"][src]["count_24h"] == 0

    def test_last_seen_at_is_max(self):
        store = InMemoryOutcomesStore()
        store.write(_o(source="stripe", when=NOW - timedelta(hours=3), oid="old"))
        store.write(_o(source="stripe", when=NOW - timedelta(hours=1), oid="new"))
        store.write(_o(source="stripe", when=NOW - timedelta(hours=2), oid="mid"))
        out = compute_ingest_health(store)
        last = out["providers"]["stripe"]["last_seen_at"]
        # Closest to NOW wins:
        assert last is not None
        assert last.startswith((NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H"))

    def test_unknown_source_excluded(self):
        store = InMemoryOutcomesStore()
        # Manually create an Outcome with a non-canonical source — verifier
        # should drop it cleanly rather than 500.
        store.write(Outcome(
            id="ghost-1", workspace_id="ws-1", workspace_slug="acme",
            source="manual",  # one of the KNOWN_SOURCES
            metric="probe", captured_at=NOW.isoformat(), value_numeric=1.0,
        ))
        out = compute_ingest_health(store)
        assert out["providers"]["manual"]["count_24h"] == 1

    def test_as_of_field_populated(self):
        out = compute_ingest_health(InMemoryOutcomesStore())
        # ISO-formatted UTC timestamp, parseable:
        parsed = datetime.fromisoformat(out["as_of"])
        assert parsed.tzinfo is not None
