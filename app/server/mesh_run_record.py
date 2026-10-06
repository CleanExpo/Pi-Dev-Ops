"""Storing what a mesh build run reports: run id, duration, exit code, error code (UNI-2796).

The runner (`mesh/run_record.py`) keeps the transcript and the full error text on
its own machine and sends only facts. Four review rounds found secrets crossing
in every free-text field tried, so nothing here accepts free text: `error_code`
must be one of the runner's six literal codes, `run_id` must be the runner's hex id,
and anything else is dropped rather than stored. There is no redaction pass,
because there is nothing left that could need one.

Split out of `routes/mesh.py`, which sits on its size-gate baseline.

The columns come from `mesh/schema/0003_mesh_run_records.sql`. Nothing in this
repo applies a migration to production, so they may not exist yet. A PATCH
naming a missing column is refused whole by PostgREST, which would lose the
state transition the runner is reporting. `patch_claim` therefore retries
without the run-record fields — but only when the error names one of those
columns on the table being patched, so an unrelated failure is never masked.
"""
from __future__ import annotations

import json
import logging
import math
import re
from typing import Any, Callable, Optional

from fastapi import HTTPException
from pydantic import BaseModel

log = logging.getLogger("pi-ceo.mesh_run_record")

# Mirrors `mesh/run_record`: a closed set of literals. No suffix, no pattern —
# an exception class name is text somebody chose, and it once carried a secret.
_ERROR_CODES = frozenset({"agent_exit", "timeout", "repo_missing", "worktree_add_failed",
                          "runner_exception", "runner_exception_os", "agent_quota"})
# Exactly what the runner generates (uuid4().hex[:8]); a longer hex string is
# not a run id, it is text of unknown origin. Shape cannot prove a value is not
# a secret — it only bounds what can be stored to what the runner produces.
_RUN_ID = re.compile(r"[0-9a-f]{8}")
_MAX_DURATION_S = 7 * 24 * 3600  # a run is killed after an hour; a week is generous
_EXIT_CODE_RANGE = range(-128, 256)  # negative = killed by that signal
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
    error_code: Optional[str] = None


def record_patch(fields: RunRecordFields) -> dict[str, Any]:
    """The claim-row columns to write for this report; anything not a known shape is dropped."""
    patch: dict[str, Any] = {}
    if fields.run_id and _RUN_ID.fullmatch(fields.run_id):
        patch["run_id"] = fields.run_id
    # A value the column cannot hold (NaN, Infinity, out of range) would make the
    # whole PATCH fail and strand the claim, so it is dropped rather than sent.
    d = fields.duration_s
    if d is not None and math.isfinite(d) and 0 <= d <= _MAX_DURATION_S:
        patch["duration_s"] = d
    if fields.exit_code is not None and fields.exit_code in _EXIT_CODE_RANGE:
        patch["exit_code"] = fields.exit_code
    if fields.error_code in _ERROR_CODES:
        patch["error_code"] = fields.error_code
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


def require_stored(status: int) -> None:
    """Refuse to answer `ok` for a claim change the database did not store (review round 16).

    An `ok` over a failed PATCH told the runner its claim had ended while the
    row stayed `working`; an error reply makes the runner retry instead.
    """
    if status >= 300:
        raise HTTPException(502, f"claim update not stored ({status})")


def patch_claim(sb: Callable[..., tuple[int, str]], method: str, path: str,
                patch: dict[str, Any], *, fields: RunRecordFields,
                prefer: str = "") -> tuple[int, str]:
    """PATCH the claim with its run record, falling back to the bare state change."""
    extra = record_patch(fields)
    status, body = sb(method, path, {**patch, **extra}, prefer=prefer)
    if extra and _missing_run_column(status, body, extra, path.split("?", 1)[0]):
        log.warning("claim run-record columns absent (apply mesh/schema/0003); "
                    "stored the state change only")
        status, body = sb(method, path, patch, prefer=prefer)
    return status, body
