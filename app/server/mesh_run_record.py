"""Storing what a mesh build run reports: run id, duration, exit code, error (UNI-2796).

The runner (`mesh/run_record.py`) keeps the transcript on its own machine and
sends only the outcome. `error` is free text (`str(exc)` on the runner), so the
runner redacts it with the one bank a bare node python can import, and this
module redacts it again with the server's full bank before storing it. When
that bank is incomplete the error is dropped — the same fail-closed rule
`routes/conversations.py` applies to transcripts.

Split out of `routes/mesh.py`, which sits on its size-gate baseline.

The columns come from `mesh/schema/0002_mesh_run_records.sql`. Nothing in this
repo applies a migration to production, so they may not exist yet. A PATCH
naming a missing column is refused whole by PostgREST, which would lose the
state transition the runner is reporting. `patch_claim` therefore retries
without the run-record fields — but only when the error names one of those
columns on the table being patched, so an unrelated failure is never masked.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

from pydantic import BaseModel

from .conversation_redaction import _REDACTION_BANK, _REDACTION_BANK_COMPLETE

log = logging.getLogger("pi-ceo.mesh_run_record")

ERROR_CHARS = 500
# PostgREST's "column not in schema cache" code, and Postgres's undefined_column.
_MISSING_COLUMN = ("PGRST204", "42703")
# (column, table) as each names them: PostgREST "the 'col' column of 'table'",
# Postgres 'column "col" of relation "table"' or "column table.col".
_COLUMN_OF_TABLE = (
    re.compile(r"'([^']+)' column of '([^']+)'"),
    re.compile(r'column "([^"]+)" of relation "([^"]+)"'),
    re.compile(r"column (\w+)\.(\w+) does not exist"),
)


class RunRecordFields(BaseModel):
    """What a build-lane runner adds to `/claim/update`. All optional: older runners send none."""

    run_id: Optional[str] = None
    duration_s: Optional[float] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None


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
    if fields.error and _REDACTION_BANK_COMPLETE:
        patch["error"] = _redact(fields.error)[:ERROR_CHARS]
    return patch


def _names_missing(message: str) -> Optional[tuple[str, str]]:
    """The (column, table) a missing-column message names, or None."""
    for i, rx in enumerate(_COLUMN_OF_TABLE):
        found = rx.search(message)
        if found:
            a, b = found.group(1), found.group(2)
            return (b, a) if i == 2 else (a, b)
    return None


def _missing_run_column(status: int, body: str, extra: dict[str, Any], table: str) -> bool:
    """True only for a 400 whose structured code says one of OUR columns is missing on `table`.

    Anything looser masks a real failure by quietly dropping the run record:
    a code mentioned in passing, "terror" containing "error", or `run_id`
    missing on some other relation.
    """
    if status != 400:
        return False
    try:
        err = json.loads(body)
    except ValueError:
        return False
    if not isinstance(err, dict) or err.get("code") not in _MISSING_COLUMN:
        return False
    named = _names_missing(str(err.get("message", "")))
    return named is not None and named[0] in extra and named[1] == table


def patch_claim(sb: Callable[..., tuple[int, str]], method: str, path: str,
                patch: dict[str, Any], *, fields: RunRecordFields,
                prefer: str = "") -> tuple[int, str]:
    """PATCH the claim with its run record, falling back to the bare state change."""
    extra = record_patch(fields)
    status, body = sb(method, path, {**patch, **extra}, prefer=prefer)
    if extra and _missing_run_column(status, body, extra, path.split("?", 1)[0]):
        log.warning("claim run-record columns absent (apply mesh/schema/0002); "
                    "stored the state change only")
        status, body = sb(method, path, patch, prefer=prefer)
    return status, body
