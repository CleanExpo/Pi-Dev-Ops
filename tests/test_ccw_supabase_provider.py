"""RED controls for the aggregate-only CCW Supabase provider."""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone

import pytest

ALLOWED_COLUMNS = (
    "state",
    "reason_code",
    "latest_run_id",
    "heartbeat_at",
    "source_query_ok",
    "pending_count",
    "open_over_30m_count",
    "unresolved_escalation_count",
    "consumer_checkpoint_at",
)
ALLOWED = set(ALLOWED_COLUMNS)
NOW = datetime(2026, 7, 22, 1, 0, tzinfo=timezone.utc)
CHECKPOINT_COLUMNS = (
    "tenant_id",
    "consumer_id",
    "source_run_id",
    "checked_at",
    "completed_at",
    "outcome",
    "derived_state",
    "error_code",
)


def _provider():
    try:
        return importlib.import_module("swarm.providers.ccw_supabase")
    except ModuleNotFoundError as exc:
        raise AssertionError(
            "RED aggregate-only ccw_supabase provider is missing"
        ) from exc


def _valid_aggregate_row():
    return {
        "state": "BACKLOG",
        "reason_code": "FIRST_RESPONSE_OVER_30M",
        "latest_run_id": "run-1",
        "heartbeat_at": NOW.isoformat(),
        "source_query_ok": True,
        "pending_count": 0,
        "open_over_30m_count": 1,
        "unresolved_escalation_count": 0,
        "consumer_checkpoint_at": NOW.isoformat(),
    }


def test_provider_selects_exact_aggregate_columns_and_maps_state():
    calls = []
    row = {
        "state": "BACKLOG",
        "reason_code": "FIRST_RESPONSE_OVER_30M",
        "latest_run_id": "run-1",
        "heartbeat_at": "2026-07-22T01:00:00+00:00",
        "source_query_ok": True,
        "pending_count": 0,
        "open_over_30m_count": 1,
        "unresolved_escalation_count": 0,
        "consumer_checkpoint_at": "2026-07-22T01:00:00+00:00",
    }

    def fetch(view, columns):
        calls.append((view, columns))
        return [row]

    snapshot = _provider().fetch_ccw_state(fetch)
    assert calls == [("ccw_support_state", ALLOWED_COLUMNS)]
    assert snapshot.state.value == "BACKLOG"
    assert set(row) == ALLOWED


def test_provider_rejects_missing_or_extra_columns_and_never_synthesises():
    with pytest.raises(ValueError, match="aggregate contract"):
        _provider().fetch_ccw_state(lambda _view, _columns: [])
    with pytest.raises(ValueError, match="aggregate contract"):
        _provider().fetch_ccw_state(
            lambda _view, _columns: [{"state": "QUIET_HEALTHY", "subject": "x"}]
        )


def test_registry_ccw_selection_is_explicit_and_unknown_does_not_fallback(monkeypatch):
    from swarm.providers.registry import select_cs_provider

    monkeypatch.setenv("TAO_CS_PROVIDER", "ccw_supabase")
    assert select_cs_provider().__name__ == "ccw_supabase_provider"
    monkeypatch.setenv("TAO_CS_PROVIDER", "ccw_typo")
    with pytest.raises(ValueError, match="unknown TAO_CS_PROVIDER"):
        select_cs_provider()


def test_ccw_provider_failure_never_collapses_to_empty_data(monkeypatch):
    import swarm.providers
    from swarm.bots import cs

    monkeypatch.setenv("TAO_CS_PROVIDER", "ccw_supabase")
    monkeypatch.setattr(
        swarm.providers,
        "select_cs_provider",
        lambda: lambda: (_ for _ in ()).throw(RuntimeError("private detail")),
    )
    with pytest.raises(RuntimeError, match="CCW provider unavailable"):
        cs._default_cs_provider()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reason_code", None),
        ("source_query_ok", "true"),
        ("pending_count", -1),
        ("open_over_30m_count", -1),
        ("unresolved_escalation_count", -1),
    ],
)
def test_provider_rejects_semantically_invalid_aggregate_values(field, value):
    row = {
        "state": "BACKLOG",
        "reason_code": "FIRST_RESPONSE_OVER_30M",
        "latest_run_id": "run-1",
        "heartbeat_at": "2026-07-22T01:00:00+00:00",
        "source_query_ok": True,
        "pending_count": 0,
        "open_over_30m_count": 1,
        "unresolved_escalation_count": 0,
        "consumer_checkpoint_at": "2026-07-22T01:00:00+00:00",
    }
    row[field] = value

    with pytest.raises(ValueError, match="invalid values"):
        _provider().fetch_ccw_state(lambda _view, _columns: [row])


def _checkpoint_row(consumer_id, *, run_id="run-1", completed_at=NOW):
    return {
        "tenant_id": "ccw",
        "consumer_id": consumer_id,
        "source_run_id": run_id,
        "checked_at": completed_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "outcome": "success",
        "derived_state": "INGEST_STALE",
        "error_code": None,
    }


def test_checkpoint_loader_is_run_scoped_and_canonicalises_storage_order():
    calls = []
    rows = [
        _checkpoint_row("six_pager"),
        _checkpoint_row("alert_intent"),
        _checkpoint_row("cs_metrics"),
    ]

    def fetch(run_id, columns):
        calls.append((run_id, columns))
        return rows

    checkpoints = _provider().load_consumer_checkpoints("run-1", fetch=fetch)

    assert calls == [("run-1", CHECKPOINT_COLUMNS)]
    assert tuple(item.consumer_id for item in checkpoints) == (
        "cs_metrics",
        "six_pager",
        "alert_intent",
    )
    assert all(item.source_run_id == "run-1" for item in checkpoints)


def test_checkpoint_loader_allows_absent_rows_but_rejects_malformed_duplicate_and_cross_run():
    provider = _provider()
    assert (
        provider.load_consumer_checkpoints("run-1", fetch=lambda _run, _columns: [])
        == ()
    )

    cases = [
        [_checkpoint_row("unknown")],
        [_checkpoint_row("cs_metrics"), _checkpoint_row("cs_metrics")],
        [_checkpoint_row("cs_metrics", run_id="run-2")],
        [{**_checkpoint_row("cs_metrics"), "raw_payload": "forbidden"}],
        [{**_checkpoint_row("cs_metrics"), "completed_at": "not-a-time"}],
        [{**_checkpoint_row("cs_metrics"), "completed_at": None}],
        [
            {
                **_checkpoint_row("cs_metrics"),
                "checked_at": (NOW + timedelta(seconds=1)).isoformat(),
            }
        ],
        [{**_checkpoint_row("cs_metrics"), "outcome": "maybe"}],
    ]
    for rows in cases:
        with pytest.raises(ValueError, match="checkpoint"):
            provider.load_consumer_checkpoints(
                "run-1", fetch=lambda _run, _columns, rows=rows: rows
            )


def test_checkpoint_loader_preserves_stale_evidence_for_fail_closed_derivation():
    completed_at = NOW - timedelta(hours=26, microseconds=1)
    rows = [
        _checkpoint_row(name, completed_at=completed_at)
        for name in ("cs_metrics", "six_pager", "alert_intent")
    ]

    checkpoints = _provider().load_consumer_checkpoints(
        "run-1", fetch=lambda _run, _columns: rows
    )

    assert all(item.completed_at == completed_at for item in checkpoints)


def test_alert_intent_checkpoint_writer_is_explicit_and_run_bound():
    calls = []
    payload = {
        "tenant_id": "ccw",
        "consumer_id": "alert_intent",
        "source_run_id": "run-1",
        "checked_at": NOW,
        "completed_at": NOW,
        "outcome": "success",
        "derived_state": "INGEST_STALE",
        "error_code": None,
    }

    _provider().record_alert_intent_checkpoint(payload, write_checkpoint=calls.append)

    assert calls == [payload]
    with pytest.raises(ValueError, match="alert_intent"):
        _provider().record_alert_intent_checkpoint(
            {**payload, "consumer_id": "cs_metrics"},
            write_checkpoint=calls.append,
        )


def test_checkpoint_writer_serializes_datetimes_and_uses_schema_primary_key(
    monkeypatch,
):
    provider = _provider()
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=None):
            return b"[]"

    monkeypatch.setattr(
        provider, "_credentials", lambda: ("https://example.invalid", "x")
    )

    def urlopen(request, *, timeout):
        captured.update(request=request, timeout=timeout)
        return Response()

    monkeypatch.setattr(provider.urllib.request, "urlopen", urlopen)
    provider.record_consumer_checkpoint(
        {
            "tenant_id": "ccw",
            "consumer_id": "cs_metrics",
            "source_run_id": "run-1",
            "checked_at": NOW,
            "completed_at": NOW,
            "outcome": "success",
            "derived_state": "QUIET_HEALTHY",
            "error_code": None,
        }
    )

    request = captured["request"]
    assert "on_conflict=tenant_id%2Csource_run_id%2Cconsumer_id" in request.full_url
    assert request.headers["Prefer"] == "resolution=ignore-duplicates,return=minimal"
    assert json.loads(request.data) == {
        "tenant_id": "ccw",
        "consumer_id": "cs_metrics",
        "source_run_id": "run-1",
        "checked_at": NOW.isoformat(),
        "completed_at": NOW.isoformat(),
        "outcome": "success",
        "derived_state": "QUIET_HEALTHY",
        "error_code": None,
    }


def test_default_aggregate_read_is_tenant_scoped_and_duplicate_visible(monkeypatch):
    provider = _provider()
    calls = []
    monkeypatch.setattr(
        provider,
        "_request",
        lambda method, resource, **kwargs: calls.append((method, resource, kwargs))
        or [_valid_aggregate_row()],
    )

    snapshot = provider.fetch_ccw_state()

    assert snapshot.tenant_id == "ccw"
    assert calls[0][2]["query"] == {
        "select": ",".join(ALLOWED_COLUMNS),
        "tenant_id": "eq.ccw",
        "limit": "2",
    }
    with pytest.raises(ValueError, match="aggregate contract"):
        provider.fetch_ccw_state(lambda _view, _columns: [_valid_aggregate_row()] * 2)


def test_checkpoint_write_is_tenant_run_consumer_create_only(monkeypatch):
    provider = _provider()
    calls = []
    monkeypatch.setattr(
        provider,
        "_request",
        lambda method, resource, **kwargs: calls.append((method, resource, kwargs)) or [],
    )
    payload = {
        "tenant_id": "ccw",
        "consumer_id": "cs_metrics",
        "source_run_id": "run-1",
        "checked_at": NOW,
        "completed_at": NOW,
        "outcome": "success",
        "derived_state": "INGEST_STALE",
        "error_code": None,
    }

    provider.record_consumer_checkpoint(payload)

    assert calls == [(
        "POST",
        "ccw_support_consumer_checkpoints",
        {
            "query": {"on_conflict": "tenant_id,source_run_id,consumer_id"},
            "payload": payload,
            "prefer": "resolution=ignore-duplicates,return=minimal",
        },
    )]


def test_alert_replay_advances_only_newer_nonterminal_sighting(monkeypatch):
    provider = _provider()
    calls = []
    monkeypatch.setattr(
        provider,
        "_request",
        lambda method, resource, **kwargs: calls.append((method, resource, kwargs)) or [],
    )
    last_seen = NOW + timedelta(minutes=1)
    payload = {
        "tenant_id": "ccw",
        "dedup_key": "a" * 64,
        "state": "ESCALATION",
        "source_run_id": "run-1",
        "opened_at": NOW,
        "last_seen_at": last_seen,
        "status": "pending",
    }

    provider.create_alert_intent(payload)

    assert calls[0][2]["query"] == {"on_conflict": "tenant_id,dedup_key"}
    assert calls[0][2]["prefer"] == "resolution=ignore-duplicates,return=minimal"
    assert calls[1][0] == "PATCH"
    assert calls[1][2]["query"] == {
        "tenant_id": "eq.ccw",
        "dedup_key": "eq." + "a" * 64,
        "status": "in.(pending,drafted)",
        "last_seen_at": "lt." + last_seen.isoformat(),
        "opened_at": "lte." + last_seen.isoformat(),
    }


def test_checkpoint_loader_rejects_cross_tenant_before_fetch():
    with pytest.raises(ValueError, match="tenant identity"):
        _provider().load_consumer_checkpoints(
            "run-1",
            tenant_id="another-client",
            fetch=lambda _run, _columns: pytest.fail("cross-tenant fetch executed"),
        )
