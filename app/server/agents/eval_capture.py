"""Flag-gated capture of feedback_loop classifier calls as eval candidates.

RA-7014 slice 4 — spec: docs/specs/spec-cap5-slice4-online-eval.md.

Fire-and-forget: called after a successful classification and must never raise
or slow the fail-soft path. Raw thread text exists only in memory — redaction
(strictness=high) happens before any write. Rows land in the Supabase
eval_candidates table (durable across Railway redeploys); when Supabase is
unconfigured the row falls back to a gitignored local JSONL.
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("pi-ceo.eval_capture")

_FLAG_ENV = "TAO_EVAL_SAMPLING"          # "1" enables capture; default OFF
_RATE_ENV = "TAO_EVAL_SAMPLE_RATE"       # fraction of calls captured; default 0.2
_LOCAL_FALLBACK = Path(".harness/eval-candidates/candidates.jsonl")


def _enabled() -> bool:
    return os.environ.get(_FLAG_ENV, "0") == "1"


def _rate() -> float:
    try:
        return min(1.0, max(0.0, float(os.environ.get(_RATE_ENV, "0.2"))))
    except ValueError:
        return 0.2


def _default_redact(thread: str) -> str:
    from swarm.pii_redactor import redact  # noqa: PLC0415 — heavy import, flag-gated path only
    return redact(thread, context="eval_capture", strictness="high").redacted_payload


def build_thread(comments: list[str], state: str) -> str:
    """Mirror _classify_with_claude's thread construction exactly."""
    thread = "\n---\n".join(comments[:30]) if comments else "(no comments)"
    thread = thread[:4000]
    return f"{thread}\n\nLinear state: {state}"


def maybe_capture_candidate(
    *,
    comments: list[str],
    state: str,
    days_since: int,
    pipeline_id: str,
    predicted: dict[str, Any],
    provider: str,
    model: str,
    redact_fn: Callable[[str], str] | None = None,
    insert_fn: Callable[[dict[str, Any]], bool] | None = None,
    rng: Callable[[], float] | None = None,
    fallback_path: Path | None = None,
) -> bool:
    """Capture one redacted candidate row when the flag + sampling allow it.

    Returns True only when a row was durably written. Never raises.
    """
    try:
        if not _enabled():
            return False
        if (rng or random.random)() >= _rate():
            return False

        redacted = (redact_fn or _default_redact)(build_thread(comments, state))
        row: dict[str, Any] = {
            "pipeline_id": pipeline_id,
            "thread_redacted": redacted,
            "state": state,
            "days_since": int(days_since),
            "predicted_category": predicted.get("category"),
            "predicted_label": predicted.get("label"),
            "confidence": predicted.get("confidence"),
            "provider": provider,
            "model": model,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }

        if insert_fn is None:
            from app.server.supabase_log import insert_eval_candidate  # noqa: PLC0415
            insert_fn = insert_eval_candidate
        if insert_fn(row):
            return True

        target = fallback_path or _LOCAL_FALLBACK
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001 — capture must never affect classification
        log.warning("eval capture failed (non-fatal): %s", type(exc).__name__)
        return False
