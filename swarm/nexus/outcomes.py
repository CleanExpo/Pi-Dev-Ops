"""Outcomes store — fire-and-forget writer + REST-backed read for Nexus.

Phase B / B1. The outcomes table is the feedback-loop ledger:
ingestion adapters (Stripe / Vercel / PostHog / Sentry / Linear) write
to it; the BRA generator and 6-pager read from it.

Two implementations:
  - InMemoryOutcomesStore  — tests; behaves like the StubOutcomesStore
                              already in tests/swarm/nexus/test_api.py.
  - SupabaseOutcomesStore  — production. Writes are fire-and-forget
                              (scheduled on the event loop or a daemon
                              thread); failures log at WARNING level and
                              never surface to the caller.

Selection via `outcomes_store_factory(in_memory=...)`.
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
from typing import Any, Protocol, runtime_checkable

from .types import Outcome

log = logging.getLogger("pi-ceo.nexus.outcomes")

DEFAULT_LIST_LIMIT = 100
SUPABASE_REST_TIMEOUT_S = 8


@runtime_checkable
class OutcomesStore(Protocol):
    def write(self, outcome: Outcome) -> None: ...
    def list(
        self,
        *,
        workspace_slug: str | None = None,
        workspace_id: str | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
    ) -> list[Outcome]: ...


# ============================================================
# In-memory implementation (tests, local dev)
# ============================================================


class InMemoryOutcomesStore:
    def __init__(self) -> None:
        self._rows: list[Outcome] = []

    def write(self, outcome: Outcome) -> None:
        self._rows.append(outcome)

    def list(
        self,
        *,
        workspace_slug: str | None = None,
        workspace_id: str | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
    ) -> list[Outcome]:
        rows = self._rows
        if workspace_slug is not None:
            rows = [r for r in rows if r.workspace_slug == workspace_slug]
        if workspace_id is not None:
            rows = [r for r in rows if r.workspace_id == workspace_id]
        rows = sorted(rows, key=lambda r: r.captured_at, reverse=True)
        return rows[:limit]


# ============================================================
# Supabase REST implementation (production)
# ============================================================


def _outcome_to_payload(outcome: Outcome) -> dict[str, Any]:
    row = asdict(outcome)
    if not row.get("created_at"):
        row.pop("created_at")  # let Postgres default fire
    return row


class SupabaseOutcomesStore:
    """REST-backed writer; failures are swallowed and logged.

    Use the service-role key — RLS bypass for server-side writes.
    """

    def __init__(self, *, url: str, service_role_key: str) -> None:
        if not url or not service_role_key:
            raise ValueError("SupabaseOutcomesStore requires url + service_role_key")
        self._base = f"{url.rstrip('/')}/rest/v1/outcomes"
        self._headers = {
            "Content-Type": "application/json",
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        }

    # ---- write (fire-and-forget) ----

    def write(self, outcome: Outcome) -> None:
        payload = _outcome_to_payload(outcome)
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
                name="nexus-outcomes-write",
            ).start()

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
                "outcomes insert failed (non-fatal) source=%s metric=%s err=%s",
                payload.get("source"), payload.get("metric"), exc,
            )

    # ---- list (synchronous; called from request handler) ----

    def list(
        self,
        *,
        workspace_slug: str | None = None,
        workspace_id: str | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
    ) -> list[Outcome]:
        params: dict[str, str] = {
            "select": "*",
            "order": "captured_at.desc",
            "limit": str(min(max(limit, 1), 1000)),
        }
        if workspace_slug is not None:
            params["workspace_slug"] = f"eq.{workspace_slug}"
        if workspace_id is not None:
            params["workspace_id"] = f"eq.{workspace_id}"
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{self._base}?{qs}",
            method="GET",
            headers=self._headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=SUPABASE_REST_TIMEOUT_S) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            log.warning("outcomes list failed (non-fatal): %s", exc)
            return []
        return [_row_to_outcome(r) for r in rows if isinstance(r, dict)]


def _row_to_outcome(row: dict[str, Any]) -> Outcome:
    return Outcome(
        id=row["id"],
        workspace_id=row["workspace_id"],
        workspace_slug=row["workspace_slug"],
        source=row["source"],
        metric=row["metric"],
        captured_at=row["captured_at"],
        project_id=row.get("project_id"),
        persona_attribution=row.get("persona_attribution"),
        value_numeric=row.get("value_numeric"),
        value_text=row.get("value_text"),
        delta_window=row.get("delta_window"),
        raw_payload=row.get("raw_payload") or {},
        created_at=row.get("created_at") or "",
    )


# ============================================================
# Factory
# ============================================================


def outcomes_store_factory(
    *,
    in_memory: bool = False,
    url: str | None = None,
    service_role_key: str | None = None,
) -> OutcomesStore:
    """Return the appropriate OutcomesStore.

    `in_memory=True` for tests / local dev. Otherwise requires url +
    service_role_key; falls back to an in-memory store with a WARNING
    log if either is missing (so a misconfigured deploy still boots).
    """
    if in_memory:
        return InMemoryOutcomesStore()
    if not url or not service_role_key:
        log.warning(
            "outcomes_store_factory: Supabase URL or service-role key missing — "
            "falling back to in-memory store. Set NEXT_PUBLIC_SUPABASE_URL + "
            "SUPABASE_SERVICE_ROLE_KEY in Railway to persist outcomes."
        )
        return InMemoryOutcomesStore()
    return SupabaseOutcomesStore(url=url, service_role_key=service_role_key)
