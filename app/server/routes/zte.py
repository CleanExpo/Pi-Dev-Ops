"""ZTE v2 score read API — serves the daily cron's cached score to Mission Control.

The dashboard's `/api/zte` (TopBar / ModelBadge) asks upstream for `/api/zte/score`.
No backend route served it, so the badge could only ever show the harness file or
"unavailable". The score itself is computed daily by the `zte-v2-score-daily` cron
(`scripts/zte_v2_score.py`, `compute_v2_score`), which writes `.harness/zte-v2-score.json`.
This route reads that file and never recomputes: a read must not trigger Supabase
queries or scanner walks on every dashboard poll.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..auth import require_auth

log = logging.getLogger("pi-ceo.zte")

router = APIRouter(prefix="/api/zte", tags=["zte"])

SCORE_FILE = Path(__file__).resolve().parents[3] / ".harness" / "zte-v2-score.json"
STALE_AFTER = timedelta(hours=48)


def _read_score(path: Path) -> dict | None:
    """Return the cached score fields, or None when absent or malformed."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    score = raw.get("v2_total") if isinstance(raw, dict) else None
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100:
        return None
    return {"score": score, "band": raw.get("band"), "computed_at": raw.get("computed_at")}


def _is_stale(computed_at: object, now: datetime) -> bool:
    """A score with no parseable timestamp is treated as stale, never as fresh."""
    if not isinstance(computed_at, str):
        return True
    try:
        at = datetime.fromisoformat(computed_at)
    except ValueError:
        return True
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return now - at > STALE_AFTER


@router.get("/score", dependencies=[Depends(require_auth)])
async def zte_score() -> JSONResponse:
    """Latest cached ZTE v2 score, with an explicit staleness flag."""
    found = _read_score(SCORE_FILE)
    if found is None:
        log.info("zte score requested but %s is absent or malformed", SCORE_FILE)
        return JSONResponse({"error": "no score computed yet"}, status_code=404)
    found["stale"] = _is_stale(found["computed_at"], datetime.now(timezone.utc))
    return JSONResponse(found)
