"""Can Mission Control reach the database the Schema Drift check reads?

Schema Drift (.github/workflows/schema_drift.yml) compares the live Pi CEO
catalog with the schema this repo declares, over SUPABASE_DB_URL. This probe
reads the same variable and runs the same catalog query, so the
`schema_drift_db` health component answers the question that job depends on.

Two questions, never collapsed into one (the supabase_health.py contract):

  observed=False  no database answered: not configured, driver missing,
                  unreachable, timed out or malformed. UNPROVEN, never a pass.
  observed=True   a database answered; `ok` carries its verdict.

The variable holds a password. Driver error text embeds the host and user and
can quote the connection string itself, so an error is classified and then
discarded: nothing here returns, logs or echoes any part of it.

See docs/schema-drift-db.md.
"""

from __future__ import annotations

import os
import time
from typing import Any

ENV_VAR = "SUPABASE_DB_URL"

# The Schema Drift job's only query, as a count. pg_class and pg_namespace are
# readable by PUBLIC, which is why the login needs no grants at all.
CATALOG_QUERY = (
    "select count(*) from pg_class c join pg_namespace n on c.relnamespace = n.oid"
    " where n.nspname = 'public' and c.relkind = 'r'"
)

# libpq's floor. health_full gives each component 2s, so a slower handshake
# reports a timeout there rather than hanging the whole snapshot.
_CONNECT_TIMEOUT_S = 2

# The login has connection limit 3 and Mission Control polls far more often than
# once a minute, so at most one real connection per process per minute.
_CACHE_TTL_S = 60.0
_cache: dict[str, Any] = {}


def health_check() -> dict[str, Any]:
    """Return the latest probe result, re-probing at most once per _CACHE_TTL_S."""
    now = time.monotonic()
    if "at" not in _cache or now - _cache["at"] >= _CACHE_TTL_S:
        _cache["result"] = probe()
        _cache["at"] = now
    return dict(_cache["result"])


def probe() -> dict[str, Any]:
    """Open one connection with SUPABASE_DB_URL and run CATALOG_QUERY. Uncached."""
    url = os.environ.get(ENV_VAR, "").strip()
    if not url:
        return {"ok": False, "observed": False, "detail": f"not configured — {ENV_VAR} is not set"}
    try:
        import psycopg  # noqa: PLC0415
    except ImportError:
        return {"ok": False, "observed": False, "detail": "psycopg is not installed, so no connection was attempted"}

    try:
        conn = psycopg.connect(url, connect_timeout=_CONNECT_TIMEOUT_S, autocommit=True)
    except Exception as exc:  # noqa: BLE001 — classified, then its text is dropped
        return _connect_failure(exc)

    try:
        with conn:
            row = conn.execute(CATALOG_QUERY).fetchone()
    except Exception as exc:  # noqa: BLE001 — SQLSTATE only, never the message
        sqlstate = getattr(exc, "sqlstate", None) or "unknown"
        return {"ok": False, "observed": True, "detail": f"connected, but the catalog query failed (SQLSTATE {sqlstate})"}

    tables = int(row[0]) if row else 0
    if tables <= 0:
        return {"ok": False, "observed": True, "detail": "connected, but the catalog lists 0 public tables"}
    return {"ok": True, "observed": True, "detail": f"connected — {tables} public tables visible"}


def _connect_failure(exc: Exception) -> dict[str, Any]:
    """A server that sent FATAL answered and refused; anything else never reached one."""
    text = str(exc).lower()
    if "fatal:" in text or "authentication failed" in text:
        return {
            "ok": False,
            "observed": True,
            "detail": "a database answered and refused the login — check the role, password and pooler user form",
        }
    return {
        "ok": False,
        "observed": False,
        "detail": f"no database answered ({type(exc).__name__}) — unreachable, timed out, or {ENV_VAR} is malformed",
    }
