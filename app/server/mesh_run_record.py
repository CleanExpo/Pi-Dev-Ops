"""Storing what a mesh build run reports: run id, duration, exit code, error, log tail (UNI-2796).

The runner (`mesh/run_record.py`) redacts its log tail with the one secret bank
a bare node python can import. This module redacts again with the server's full
bank before anything is written, and drops the tail when that bank is
incomplete — the same fail-closed rule `routes/conversations.py` applies to
transcripts. `error` is free text too (`str(exc)` on the runner), so it follows
the same rule rather than trusting that errors never carry a secret.

Split out of `routes/mesh.py`, which sits on its size-gate baseline.

The columns these fields land in come from `mesh/schema/0002_mesh_run_records.sql`.
Nothing in this repo applies a migration to production, so the columns may not
exist yet. A PATCH naming a missing column is refused whole by PostgREST, which
would lose the state transition the runner is reporting. `patch_claim` therefore
retries without the run-record fields: the claim's state always lands, and the
record lands once the migration does.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from pydantic import BaseModel

from .conversation_redaction import _REDACTION_BANK, _REDACTION_BANK_COMPLETE

log = logging.getLogger("pi-ceo.mesh_run_record")

TAIL_CHARS = 4000
ERROR_CHARS = 500
# PostgREST's "column not in schema cache" code, and Postgres's undefined_column.
_MISSING_COLUMN = ("PGRST204", "42703")


class RunRecordFields(BaseModel):
    """What a build-lane runner adds to `/claim/update`. All optional: older runners send none."""

    run_id: Optional[str] = None
    duration_s: Optional[float] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None
    log_tail: Optional[str] = None


def _redact(text: str) -> str:
    """Replace every server-bank secret match in `text`."""
    for rx, tag in _REDACTION_BANK:
        text = rx.sub(f"[REDACTED:{tag}]", text)
    return text


def record_patch(fields: RunRecordFields) -> dict[str, Any]:
    """The claim-row columns to write for this report; empty when the runner sent none."""
    patch: dict[str, Any] = {}
    if fields.run_id:
        patch["run_id"] = fields.run_id[:64]
    if fields.duration_s is not None:
        patch["duration_s"] = fields.duration_s
    if fields.exit_code is not None:
        patch["exit_code"] = fields.exit_code
    if not _REDACTION_BANK_COMPLETE:
        return patch
    if fields.error:
        patch["error"] = _redact(fields.error)[:ERROR_CHARS]
    if fields.log_tail:
        patch["log_tail"] = _redact(fields.log_tail)[-TAIL_CHARS:]
    return patch


def _missing_run_column(status: int, body: str, extra: dict[str, Any]) -> bool:
    """True only for a 400 whose structured code is a missing-column code naming one of ours.

    Matching the code anywhere in the body would retry on any error that merely
    mentions it, silently discarding the run record for an unrelated failure.
    """
    if status != 400:
        return False
    try:
        err = json.loads(body)
    except ValueError:
        return False
    if not isinstance(err, dict) or err.get("code") not in _MISSING_COLUMN:
        return False
    message = str(err.get("message", ""))
    return any(column in message for column in extra)


def patch_claim(sb: Callable[..., tuple[int, str]], method: str, path: str,
                patch: dict[str, Any], *, fields: RunRecordFields,
                prefer: str = "") -> tuple[int, str]:
    """PATCH the claim with its run record, falling back to the bare state change."""
    extra = record_patch(fields)
    status, body = sb(method, path, {**patch, **extra}, prefer=prefer)
    if extra and _missing_run_column(status, body, extra):
        log.warning("claim run-record columns absent (apply mesh/schema/0002); "
                    "stored the state change only")
        status, body = sb(method, path, patch, prefer=prefer)
    return status, body
