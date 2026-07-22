"""RED controls for the aggregate-only CCW Supabase provider."""
from __future__ import annotations

import importlib

import pytest

ALLOWED = {
    "state", "reason_code", "latest_run_id", "heartbeat_at", "source_query_ok",
    "pending_count", "open_over_30m_count", "unresolved_escalation_count",
    "consumer_checkpoint_at",
}


def _provider():
    try:
        return importlib.import_module("swarm.providers.ccw_supabase")
    except ModuleNotFoundError as exc:
        raise AssertionError("RED aggregate-only ccw_supabase provider is missing") from exc


def test_provider_selects_exact_aggregate_columns_and_maps_state():
    calls = []
    row = {
        "state": "BACKLOG", "reason_code": "first_response_over_30m",
        "latest_run_id": "run-1", "heartbeat_at": "2026-07-22T01:00:00+00:00",
        "source_query_ok": True, "pending_count": 0, "open_over_30m_count": 1,
        "unresolved_escalation_count": 0,
        "consumer_checkpoint_at": "2026-07-22T01:00:00+00:00",
    }

    def fetch(view, columns):
        calls.append((view, columns))
        return [row]

    snapshot = _provider().fetch_ccw_state(fetch)
    assert calls == [("ccw_support_state", tuple(ALLOWED))]
    assert snapshot.state.value == "BACKLOG"
    assert set(row) == ALLOWED


def test_provider_rejects_missing_or_extra_columns_and_never_synthesises():
    with pytest.raises(ValueError, match="aggregate contract"):
        _provider().fetch_ccw_state(lambda _view, _columns: [])
    with pytest.raises(ValueError, match="aggregate contract"):
        _provider().fetch_ccw_state(lambda _view, _columns: [{"state": "QUIET_HEALTHY", "subject": "x"}])


def test_registry_ccw_selection_is_explicit_and_unknown_does_not_fallback(monkeypatch):
    from swarm.providers.registry import select_cs_provider

    monkeypatch.setenv("TAO_CS_PROVIDER", "ccw_supabase")
    assert select_cs_provider().__name__ == "ccw_supabase_provider"
    monkeypatch.setenv("TAO_CS_PROVIDER", "ccw_typo")
    with pytest.raises(ValueError, match="unknown TAO_CS_PROVIDER"):
        select_cs_provider()
