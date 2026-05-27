"""Production store wiring for app.state.nexus_stores.

Phase B / B9. The B8 scheduler daemon needs four collaborators:

    loops_store      — read `client_loops` rows due for processing
    outcomes_store   — already wired in B1 (SupabaseOutcomesStore)
    audit_store      — append rows to `nexus_audit`
    llm              — WORKING-tier LLM client

This module produces Supabase-REST adapters for the three that B1
didn't cover, plus a thin LLM adapter that delegates to
`swarm.model_router.get_client(Tier.WORKING)`.

All writes are fire-and-forget (same pattern as
SupabaseOutcomesStore): the request thread never blocks on a 5xx,
exceptions log at WARNING and never surface to the caller.

Factory: `build_production_stores(supabase_url, service_role_key)`
returns a dict suitable for `app.state.nexus_stores`. If creds are
missing it falls back to in-memory stubs with a WARNING log — so a
misconfigured deploy still boots cleanly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime
from typing import Any

from .outcomes import outcomes_store_factory
from .types import Loop

log = logging.getLogger("pi-ceo.nexus.store_factory")

SUPABASE_REST_TIMEOUT_S = 8
LOOPS_LIST_LIMIT = 200


# ============================================================
# Loops store — Supabase-backed
# ============================================================


class SupabaseLoopsStore:
    """REST-backed loops store.

    `list_due` returns loops where enabled = true AND
    (next_run_at IS NULL OR next_run_at <= now). `save` upserts on
    the primary key (Postgres ON CONFLICT … DO UPDATE).
    """

    def __init__(self, *, url: str, service_role_key: str) -> None:
        self._base = f"{url.rstrip('/')}/rest/v1/client_loops"
        self._headers = {
            "Content-Type": "application/json",
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        }

    # ---- list_due ----

    def list_due(self, *, now: datetime) -> list[Loop]:
        params: dict[str, str] = {
            "select": "*",
            "enabled": "eq.true",
            "or": f"(next_run_at.is.null,next_run_at.lte.{now.isoformat()})",
            "order": "next_run_at.asc.nullsfirst",
            "limit": str(LOOPS_LIST_LIMIT),
        }
        qs = urllib.parse.urlencode(params, safe=":,()")
        req = urllib.request.Request(
            f"{self._base}?{qs}",
            method="GET",
            headers=self._headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=SUPABASE_REST_TIMEOUT_S) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            log.warning("loops list_due failed (non-fatal): %s", exc)
            return []
        return [_row_to_loop(r) for r in rows if isinstance(r, dict)]

    # ---- save (upsert) ----

    def save(self, loop: Loop) -> Loop:
        payload = asdict(loop)
        try:
            req = urllib.request.Request(
                self._base,
                data=json.dumps(payload).encode(),
                method="POST",
                headers={
                    **self._headers,
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
            )
            with urllib.request.urlopen(req, timeout=SUPABASE_REST_TIMEOUT_S) as resp:
                resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            log.warning(
                "loops save failed (non-fatal) loop=%s err=%s",
                loop.id, exc,
            )
        return loop


def _row_to_loop(row: dict[str, Any]) -> Loop:
    return Loop(
        id=row["id"],
        workspace_id=row["workspace_id"],
        workspace_slug=row["workspace_slug"],
        loop_kind=row["loop_kind"],
        cadence=row["cadence"],
        enabled=bool(row.get("enabled", True)),
        config=row.get("config") or {},
        last_run_at=row.get("last_run_at"),
        next_run_at=row.get("next_run_at"),
        created_at=row.get("created_at") or "",
    )


# ============================================================
# Audit store — Supabase-backed, fire-and-forget
# ============================================================


class SupabaseAuditStore:
    """REST-backed audit ledger writer.

    Append is fire-and-forget — schedules POST via asyncio.create_task
    if an event loop is running, else via a daemon thread. Failures
    log at WARNING and never raise.
    """

    def __init__(self, *, url: str, service_role_key: str) -> None:
        self._base = f"{url.rstrip('/')}/rest/v1/nexus_audit"
        self._headers = {
            "Content-Type": "application/json",
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        }

    def append(self, row) -> str:  # row: NexusAuditRow
        payload = asdict(row)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(asyncio.to_thread(self._post_insert, payload))
        else:
            threading.Thread(
                target=self._post_insert,
                args=(payload,),
                daemon=True,
                name="nexus-audit-write",
            ).start()
        return row.id

    def _post_insert(self, payload: dict[str, Any]) -> None:
        try:
            req = urllib.request.Request(
                self._base,
                data=json.dumps(payload).encode(),
                method="POST",
                headers={**self._headers, "Prefer": "return=minimal"},
            )
            with urllib.request.urlopen(req, timeout=SUPABASE_REST_TIMEOUT_S) as resp:
                resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            log.warning(
                "nexus_audit insert failed (non-fatal) action=%s err=%s",
                payload.get("action"), exc,
            )


# ============================================================
# LLM adapter — bridges LLMProtocol → swarm.model_router
# ============================================================


class WorkingTierLLM:
    """Adapter: LLMProtocol → swarm.model_router (WORKING tier).

    Each call resolves a fresh client (cheap), so we always get the
    current fallback ladder. Returns the response text. On
    NoProviderAvailable, raises — callers wrap their own try/except.
    """

    def complete(
        self, *, system: str, user: str,
        max_tokens: int = 1024, temperature: float = 0.3,
    ) -> str:
        from swarm.model_router import Tier, get_client  # noqa: PLC0415
        client = get_client(Tier.WORKING)
        resp = client.complete(
            system=system, user=user,
            max_tokens=max_tokens, temperature=temperature,
        )
        return resp.text


# ============================================================
# In-memory stubs for fallback
# ============================================================


class _InMemoryLoopsStore:
    def __init__(self) -> None:
        self._rows: list[Loop] = []

    def list_due(self, *, now: datetime) -> list[Loop]:
        return list(self._rows)

    def save(self, loop: Loop) -> Loop:
        self._rows = [r for r in self._rows if r.id != loop.id] + [loop]
        return loop


class _InMemoryAuditStore:
    def __init__(self) -> None:
        self.rows: list = []

    def append(self, row) -> str:
        self.rows.append(row)
        return row.id


# ============================================================
# Factory
# ============================================================


def build_production_stores(
    *,
    supabase_url: str | None,
    service_role_key: str | None,
) -> dict[str, Any]:
    """Return a fully-populated app.state.nexus_stores bag.

    Missing Supabase creds → in-memory fallback for ALL stores so the
    daemon still boots, but writes don't persist. WARNING-logged once.
    """
    if not supabase_url or not service_role_key:
        log.warning(
            "build_production_stores: Supabase creds missing — falling back "
            "to in-memory stores. Set NEXT_PUBLIC_SUPABASE_URL + "
            "SUPABASE_SERVICE_ROLE_KEY on Railway to persist nexus state."
        )
        return {
            "loops": _InMemoryLoopsStore(),
            "outcomes": outcomes_store_factory(in_memory=True),
            "audit": _InMemoryAuditStore(),
            "llm": WorkingTierLLM(),
        }

    return {
        "loops": SupabaseLoopsStore(
            url=supabase_url, service_role_key=service_role_key,
        ),
        "outcomes": outcomes_store_factory(
            url=supabase_url, service_role_key=service_role_key,
        ),
        "audit": SupabaseAuditStore(
            url=supabase_url, service_role_key=service_role_key,
        ),
        "llm": WorkingTierLLM(),
    }


__all__ = [
    "SupabaseLoopsStore",
    "SupabaseAuditStore",
    "WorkingTierLLM",
    "build_production_stores",
]
