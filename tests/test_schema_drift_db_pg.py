"""The Schema Drift database path against a real, throwaway Postgres (D19).

Runs in pgtap-pilot.yml's rls-assertions job, whose service container is the
only database it may touch. SCRATCH_DB_URL is that container's superuser URL,
and a non-local URL is refused before anything connects. Never a remote
database, never SPINE_DATABASE_URL.

The login is created from the SQL block in docs/schema-drift-db.md, verbatim
except for the role name and password, so the documented least-privilege role
is the one proven here, not a look-alike.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit

import pytest

SCRATCH = os.environ.get("SCRATCH_DB_URL", "")
if not SCRATCH:
    if os.environ.get("SCHEMA_DRIFT_DB_PG_REQUIRED") == "1":
        raise RuntimeError("SCHEMA_DRIFT_DB_PG_REQUIRED=1 but SCRATCH_DB_URL is unset; refusing to skip")
    pytest.skip("needs an ephemeral Postgres in SCRATCH_DB_URL", allow_module_level=True)

import psycopg  # noqa: E402

from app.server import schema_drift_db  # noqa: E402

_PARTS = urlsplit(SCRATCH)
if _PARTS.hostname not in {"localhost", "127.0.0.1"}:
    raise RuntimeError("SCRATCH_DB_URL must point at a local throwaway database")

DOC = Path(__file__).resolve().parents[1] / "docs" / "schema-drift-db.md"
TABLE = "public.schema_drift_db_probe_t"


def _documented_role_sql(role: str, password: str) -> list[str]:
    match = re.search(r"```sql\n(-- schema-drift-role:[^\n]*\n.*?)```", DOC.read_text(encoding="utf-8"), re.S)
    assert match, "docs/schema-drift-db.md lost its schema-drift-role SQL block"
    body = "\n".join(line for line in match.group(1).splitlines() if not line.startswith("--"))
    assert "GENERATED_PASSWORD" in body and re.search(r"\bschema_drift_ro\b", body)
    body = re.sub(r"\bschema_drift_ro\b", role, body).replace("GENERATED_PASSWORD", password)
    return [stmt.strip() for stmt in body.split(";") if stmt.strip()]


def _url(user: str, password: str) -> str:
    return f"postgresql://{user}:{password}@{_PARTS.hostname}:{_PARTS.port or 5432}{_PARTS.path}"


@pytest.fixture(scope="module")
def login():
    role = f"schema_drift_ro_t{secrets.token_hex(4)}"
    password = secrets.token_hex(16)
    with psycopg.connect(SCRATCH, autocommit=True) as admin:
        admin.execute(f"create table if not exists {TABLE} (id int)")
        for stmt in _documented_role_sql(role, password):
            admin.execute(stmt)
        yield {"role": role, "password": password, "url": _url(role, password)}
        admin.execute(f"drop role if exists {role}")
        admin.execute(f"drop table if exists {TABLE}")


def test_documented_login_connects_through_the_probe(login, monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", login["url"])
    result = schema_drift_db.probe()
    assert result["observed"] is True and result["ok"] is True, result
    assert int(re.search(r"(\d+) public tables", result["detail"]).group(1)) >= 1


def test_documented_login_is_read_only_and_cannot_read_rows(login):
    with psycopg.connect(SCRATCH, autocommit=True) as admin:
        # Positive control: the same privilege check answers true for the owner.
        assert admin.execute("select has_table_privilege(current_user, %s, 'SELECT')", (TABLE,)).fetchone()[0] is True
        assert admin.execute("select has_table_privilege(%s, %s, 'SELECT')", (login["role"], TABLE)).fetchone()[0] is False
        members = admin.execute(
            "select count(*) from pg_auth_members m join pg_roles r on r.oid = m.member where r.rolname = %s",
            (login["role"],),
        ).fetchone()[0]
        assert members == 0
    with psycopg.connect(login["url"], autocommit=True) as conn:
        assert conn.execute("show default_transaction_read_only").fetchone()[0] == "on"
        assert conn.execute("show statement_timeout").fetchone()[0] == "15s"
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(f"select * from {TABLE}")
        with pytest.raises((psycopg.errors.ReadOnlySqlTransaction, psycopg.errors.InsufficientPrivilege)):
            conn.execute("create table public.schema_drift_db_write_t (id int)")


def test_wrong_password_reads_red_and_echoes_nothing(login, monkeypatch):
    wrong = _url(login["role"], "wrong-" + login["password"])
    with pytest.raises(psycopg.OperationalError) as raw:
        psycopg.connect(wrong, connect_timeout=5)
    assert login["role"] in str(raw.value)  # positive control: raw driver text names the user

    monkeypatch.setenv("SUPABASE_DB_URL", wrong)
    result = schema_drift_db.probe()
    assert result["observed"] is True and result["ok"] is False, result
    blob = json.dumps(result)
    for secret in (login["role"], login["password"], _PARTS.hostname, str(_PARTS.port or 5432)):
        assert secret not in blob
