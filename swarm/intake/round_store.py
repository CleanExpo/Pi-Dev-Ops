"""SupabaseBoardRoundStore — the BoardRoundStore adapter for the intake
pipeline. Persists one `intake_board_rounds` row per enqueued Board
deliberation (schema: supabase/migrations/20260526_intake_pipeline.sql).

The SpmForwarder Protocol hands `record_round` (thread_id, project_id,
bot_id, board_id, brief). The board-rounds table additionally needs
`client_slug` (denormalized for RLS) and a per-thread `round_number`
(UNIQUE per thread) — both derived here from the `intake_threads` row,
which carries `client_slug` and a `board_rounds` counter. `project_id`
and `bot_id` are not columns on this table and are unused by the adapter.

Supabase I/O is injected (defaults to the shared `_sb_request` PostgREST
client) so the adapter is unit-testable without a live DB.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import asdict
from typing import Any, Callable
from uuid import uuid4

from swarm.intake.spm import SPMBrief

# Transport: (method, path, params=, body=, extra_headers=) -> parsed JSON | None
SbRequest = Callable[..., Any]

_TIMEOUT = int(os.environ.get("SUPABASE_REST_TIMEOUT_S", "15"))


def _pi_ceo_sb_request(method: str, path: str, params: dict | None = None,
                       body: Any = None, extra_headers: dict | None = None) -> Any:
    """PostgREST client targeting the Pi CEO project.

    The intake_* tables (intake_threads, intake_board_rounds, ...) live in the
    Pi CEO Supabase project, NOT Unite-Group — verified against the live
    schema. So this targets SUPABASE_PI_CEO_* explicitly rather than reusing
    intake_router._sb_request (which points at SUPABASE_UNITE_GROUP_*).
    """
    base = os.environ["SUPABASE_PI_CEO_URL"].rstrip("/")
    key = os.environ["SUPABASE_PI_CEO_SERVICE_KEY"]
    url = f"{base}/rest/v1{path}"
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def _default_id() -> str:
    return f"icbr_{uuid4().hex}"


class SupabaseBoardRoundStore:
    def __init__(
        self,
        *,
        sb_request: SbRequest | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._sb: SbRequest = sb_request or _pi_ceo_sb_request
        self._id = id_factory or _default_id

    def record_round(
        self, *, thread_id: str, project_id: str, bot_id: str,
        board_id: str, brief: SPMBrief,
    ) -> None:
        rows = self._sb(
            "GET", "/intake_threads",
            params={"id": f"eq.{thread_id}", "select": "client_slug,board_rounds"},
        ) or []
        if not rows:
            raise ValueError(f"intake_threads row not found for thread_id={thread_id}")

        thread = rows[0]
        round_number = int(thread.get("board_rounds") or 0) + 1

        self._sb(
            "POST", "/intake_board_rounds",
            body={
                "id": self._id(),
                "thread_id": thread_id,
                "client_slug": thread["client_slug"],
                "round_number": round_number,
                "spm_brief": asdict(brief),
                "board_session_id": board_id,
                "status": "requested",
            },
            extra_headers={"Prefer": "return=minimal"},
        )

        # Advance the thread's counter so the next round_number is correct
        # (UNIQUE (thread_id, round_number) is the backstop against dupes).
        self._sb(
            "PATCH", "/intake_threads",
            params={"id": f"eq.{thread_id}"},
            body={"board_rounds": round_number},
            extra_headers={"Prefer": "return=minimal"},
        )
