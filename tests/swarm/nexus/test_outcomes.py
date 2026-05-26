"""Focused tests for swarm.nexus.outcomes — store contract + Supabase adapter.

No real Supabase. urlopen is monkeypatched everywhere the REST writer is
exercised so we can simulate 5xx and verify the fire-and-forget contract
without network calls.
"""
from __future__ import annotations

import threading
import urllib.error
import urllib.request
from typing import Any

import pytest

from swarm.nexus.outcomes import (
    InMemoryOutcomesStore,
    OutcomesStore,
    SupabaseOutcomesStore,
    _outcome_to_payload,
    _row_to_outcome,
    outcomes_store_factory,
)
from swarm.nexus.types import Outcome


# ============================================================
# Fixtures
# ============================================================


def _make_outcome(
    *,
    id: str = "out-1",
    workspace_slug: str = "acme",
    workspace_id: str = "ws-1",
    source: str = "stripe",
    metric: str = "mrr",
    captured_at: str = "2026-05-26T10:00:00+00:00",
    value_numeric: float | None = 199.0,
    **kw: Any,
) -> Outcome:
    return Outcome(
        id=id,
        workspace_id=workspace_id,
        workspace_slug=workspace_slug,
        source=source,  # type: ignore[arg-type]
        metric=metric,
        captured_at=captured_at,
        value_numeric=value_numeric,
        **kw,
    )


# ============================================================
# InMemoryOutcomesStore — protocol + filter behaviour
# ============================================================


class TestInMemoryStore:
    def test_satisfies_outcomes_store_protocol(self):
        store: OutcomesStore = InMemoryOutcomesStore()
        assert isinstance(store, OutcomesStore)

    def test_write_then_list_round_trip(self):
        store = InMemoryOutcomesStore()
        o = _make_outcome()
        store.write(o)
        rows = store.list()
        assert rows == [o]

    def test_list_filters_by_workspace_slug(self):
        store = InMemoryOutcomesStore()
        store.write(_make_outcome(id="a", workspace_slug="acme"))
        store.write(_make_outcome(id="b", workspace_slug="other"))
        rows = store.list(workspace_slug="acme")
        assert [r.id for r in rows] == ["a"]

    def test_list_orders_newest_first(self):
        store = InMemoryOutcomesStore()
        store.write(_make_outcome(id="old", captured_at="2026-01-01T00:00:00+00:00"))
        store.write(_make_outcome(id="new", captured_at="2026-05-26T00:00:00+00:00"))
        rows = store.list()
        assert [r.id for r in rows] == ["new", "old"]

    def test_list_respects_limit(self):
        store = InMemoryOutcomesStore()
        for i in range(5):
            store.write(_make_outcome(id=f"o{i}", captured_at=f"2026-05-{i+1:02d}T00:00:00+00:00"))
        assert len(store.list(limit=2)) == 2


# ============================================================
# Helpers
# ============================================================


class TestHelpers:
    def test_outcome_to_payload_drops_empty_created_at(self):
        payload = _outcome_to_payload(_make_outcome())
        assert "created_at" not in payload  # let Postgres default fire

    def test_outcome_to_payload_keeps_set_created_at(self):
        o = _make_outcome()
        from dataclasses import replace
        o = replace(o, created_at="2026-05-26T11:00:00+00:00")
        payload = _outcome_to_payload(o)
        assert payload["created_at"] == "2026-05-26T11:00:00+00:00"

    def test_row_to_outcome_handles_missing_optionals(self):
        row = {
            "id": "x",
            "workspace_id": "w",
            "workspace_slug": "acme",
            "source": "stripe",
            "metric": "mrr",
            "captured_at": "2026-05-26T10:00:00+00:00",
        }
        o = _row_to_outcome(row)
        assert o.id == "x"
        assert o.value_numeric is None
        assert o.raw_payload == {}
        assert o.created_at == ""


# ============================================================
# SupabaseOutcomesStore — fire-and-forget contract
# ============================================================


class _CaptureUrlopen:
    """Stand-in for urllib.request.urlopen that records the request + raises on demand."""

    def __init__(self, *, raise_exc: Exception | None = None):
        self.calls: list[urllib.request.Request] = []
        self._raise = raise_exc

    def __call__(self, req: urllib.request.Request, timeout: int = 0):
        self.calls.append(req)
        if self._raise:
            raise self._raise

        class _Resp:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return None

            def read(self_inner):
                return b"[]"

        return _Resp()


class TestSupabaseStoreContract:
    def test_construction_requires_url_and_key(self):
        with pytest.raises(ValueError):
            SupabaseOutcomesStore(url="", service_role_key="abc")
        with pytest.raises(ValueError):
            SupabaseOutcomesStore(url="https://example", service_role_key="")

    def test_write_is_non_blocking_and_swallows_5xx(self, monkeypatch):
        """The pipeline must NEVER raise from outcomes.write — even on Supabase HTTP error."""
        capture = _CaptureUrlopen(raise_exc=urllib.error.HTTPError(
            "u", 503, "service unavailable", {}, None,  # type: ignore[arg-type]
        ))
        monkeypatch.setattr("swarm.nexus.outcomes.urllib.request.urlopen", capture)
        store = SupabaseOutcomesStore(url="https://example.supabase.co", service_role_key="key")
        # write() must return None without raising; the daemon thread does the actual POST
        result = store.write(_make_outcome())
        assert result is None
        # Wait briefly for the daemon thread
        for t in threading.enumerate():
            if t.name == "nexus-outcomes-write":
                t.join(timeout=2)
        assert len(capture.calls) == 1  # the failing POST was attempted

    def test_list_returns_empty_on_http_error(self, monkeypatch):
        capture = _CaptureUrlopen(raise_exc=urllib.error.URLError("DNS failure"))
        monkeypatch.setattr("swarm.nexus.outcomes.urllib.request.urlopen", capture)
        store = SupabaseOutcomesStore(url="https://example.supabase.co", service_role_key="key")
        assert store.list(workspace_slug="acme") == []
        assert len(capture.calls) == 1


# ============================================================
# Factory selection
# ============================================================


class TestFactory:
    def test_in_memory_flag_returns_in_memory(self):
        assert isinstance(outcomes_store_factory(in_memory=True), InMemoryOutcomesStore)

    def test_missing_supabase_creds_falls_back_to_in_memory(self, caplog):
        with caplog.at_level("WARNING"):
            store = outcomes_store_factory(url=None, service_role_key=None)
        assert isinstance(store, InMemoryOutcomesStore)
        assert any("falling back to in-memory" in r.message for r in caplog.records)
