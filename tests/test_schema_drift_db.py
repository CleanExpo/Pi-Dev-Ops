"""Mission Control's Schema Drift database path fails closed and never echoes the credential.

SUPABASE_DB_URL carries a password. Every failure path a real driver can take
without a database is exercised here with canaries planted in the URL, and each
echo test first proves the DRIVER's own error text does carry target material,
so a passing "not in payload" assertion is not vacuous.

The half that needs a database is tests/test_schema_drift_db_pg.py (ephemeral
Postgres, run by the rls-assertions job).
"""

from __future__ import annotations

import asyncio
import json
import socket

import psycopg
import pytest

from app.server import schema_drift_db
from app.server.routes import health_full

USER, PASSWORD, DBNAME = "canary-user-7f3a", "canary-pass-91c2", "canary-db-5d0e"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    schema_drift_db._cache.clear()
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    yield
    schema_drift_db._cache.clear()


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _driver_error(url: str) -> str:
    try:
        psycopg.connect(url, connect_timeout=2).close()
    except Exception as exc:  # noqa: BLE001
        return str(exc)
    pytest.fail("the driver connected to a URL built to fail, so this test proves nothing")


def test_unset_is_not_configured_and_never_ok():
    result = schema_drift_db.probe()
    assert result["ok"] is False and result["observed"] is False
    assert "SUPABASE_DB_URL" in result["detail"]


def test_unreachable_database_is_unobserved_and_echoes_nothing(monkeypatch):
    port = _closed_port()
    url = f"postgresql://{USER}:{PASSWORD}@127.0.0.1:{port}/{DBNAME}"
    assert "127.0.0.1" in _driver_error(url)  # positive control: raw driver text names the target

    monkeypatch.setenv("SUPABASE_DB_URL", url)
    result = schema_drift_db.probe()
    assert result["ok"] is False and result["observed"] is False
    blob = json.dumps(result)
    for secret in (USER, PASSWORD, DBNAME, "127.0.0.1", str(port)):
        assert secret not in blob


def test_malformed_url_is_unobserved_and_echoes_nothing(monkeypatch):
    url = f"host=127.0.0.1 port=not-a-port-{DBNAME} user={USER} password={PASSWORD}"
    assert DBNAME in _driver_error(url)  # positive control: libpq quotes the bad value back

    monkeypatch.setenv("SUPABASE_DB_URL", url)
    result = schema_drift_db.probe()
    assert result["ok"] is False and result["observed"] is False
    blob = json.dumps(result)
    for secret in (USER, PASSWORD, DBNAME):
        assert secret not in blob


def test_server_refusal_is_observed_red_and_echoes_nothing(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise psycopg.OperationalError(
            'connection to server at "127.0.0.1", port 5432 failed: '
            f'FATAL:  password authentication failed for user "{USER}"'
        )

    monkeypatch.setattr(psycopg, "connect", refuse)
    monkeypatch.setenv("SUPABASE_DB_URL", f"postgresql://{USER}:{PASSWORD}@127.0.0.1:5432/{DBNAME}")
    result = schema_drift_db.probe()
    assert result["ok"] is False and result["observed"] is True
    blob = json.dumps(result)
    assert USER not in blob and PASSWORD not in blob


class _FakeConn:
    def __init__(self, count):
        self.count = count
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query):
        self.queries.append(query)
        return self

    def fetchone(self):
        return (self.count,)


@pytest.mark.parametrize(("count", "ok"), [(0, False), (69, True)])
def test_verdict_rests_on_the_catalog_count(monkeypatch, count, ok):
    conn = _FakeConn(count)
    monkeypatch.setattr(psycopg, "connect", lambda *_a, **_k: conn)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://u:p@127.0.0.1:5432/postgres")
    result = schema_drift_db.probe()
    assert conn.queries == [schema_drift_db.CATALOG_QUERY]
    assert result["observed"] is True and result["ok"] is ok


def test_cache_bounds_real_connections(monkeypatch):
    calls = []

    def fake_probe():
        calls.append(1)
        return {"ok": True, "observed": True, "detail": "stub"}

    monkeypatch.setattr(schema_drift_db, "probe", fake_probe)
    schema_drift_db.health_check()
    schema_drift_db.health_check()
    assert len(calls) == 1


def test_component_is_registered_and_unset_reads_degraded_not_red():
    assert "schema_drift_db" in health_full._CHECKS
    payload = asyncio.run(health_full._check_schema_drift_db())
    assert payload["ok"] is False and payload["observed"] is False
    verdict = health_full.classify({"schema_drift_db": payload})
    assert verdict["degraded_components"] == ["schema_drift_db"]
    assert verdict["red_components"] == []


def test_crashing_probe_reads_unobserved_and_drops_its_message(monkeypatch):
    def boom():
        raise RuntimeError(f"postgresql://{USER}:{PASSWORD}@127.0.0.1:5432/{DBNAME}")

    monkeypatch.setattr(schema_drift_db, "health_check", boom)
    payload = asyncio.run(health_full._check_schema_drift_db())
    assert payload["ok"] is False and payload["observed"] is False
    blob = json.dumps(payload)
    assert PASSWORD not in blob and USER not in blob
