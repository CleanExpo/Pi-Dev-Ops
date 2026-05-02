"""swarm/six_pager_dispatcher.py — RA-1863 daily-fire dispatcher.

Glue between the orchestrator main loop and the 6-pager assembler. Lives
separately from ``swarm/six_pager.py`` so the assembler stays pure
(file-read composition only) and this dispatcher owns the side effects:
draft_review post, optional voice attachment, audit emit, state stamp.

Public API:
  maybe_fire_daily(state) -> bool   # True if a brief was emitted this call

The orchestrator calls this once per cycle; the dispatcher itself decides
whether the daily-fire window is open (default 06:00 UTC, configurable
via ``TAO_SIX_PAGER_HOUR_UTC``). 23-hour debounce prevents double-fire.

Failure modes are non-fatal — every external-effect step degrades to a
log.warning and returns False. The orchestrator never crashes on a fire.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("swarm.six_pager_dispatcher")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAILY_HOUR_UTC = 6
VOICE_OUT_DIR_REL = ".harness/swarm/voice"
STATE_KEY = "six_pager_last_daily_fire"


def _is_daily_fire_window(state: dict, now: datetime) -> bool:
    """06:00 UTC by default; once-per-23-hours debounce."""
    target_hour = int(os.environ.get(
        "TAO_SIX_PAGER_HOUR_UTC", DEFAULT_DAILY_HOUR_UTC,
    ))
    if now.hour != target_hour:
        return False
    last_fired = state.get(STATE_KEY)
    if last_fired:
        try:
            last_dt = datetime.fromisoformat(last_fired)
            if (now - last_dt).total_seconds() < 23 * 3600:
                return False
        except Exception:
            pass
    return True


def _is_test_mode() -> bool:
    return os.environ.get("TAO_DRAFT_REVIEW_TEST", "0") == "1"


def maybe_fire_daily(state: dict, *,
                      repo_root: Path | None = None,
                      now: datetime | None = None) -> bool:
    """Fire the 6-pager if today's window is open and not yet fired.

    Returns True if a brief was emitted, False otherwise.
    """
    rr = repo_root or REPO_ROOT
    now = now or datetime.now(timezone.utc)

    if not _is_daily_fire_window(state, now):
        return False

    # Compose the brief
    try:
        from . import six_pager  # noqa: PLC0415
        brief = six_pager.assemble_six_pager(
            repo_root=rr, date_str=now.strftime("%Y-%m-%d"),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("6-pager: assemble failed: %s", exc)
        return False

    # Optional voice variant
    audio_path = None
    voice_text = brief
    try:
        from . import voice_compose  # noqa: PLC0415
        voice_text, audio_path = voice_compose.compose_voice_variant(
            brief, out_dir=rr / VOICE_OUT_DIR_REL,
            filename_stem=f"6pager-{now.strftime('%Y-%m-%d')}",
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("6-pager: voice compose suppressed: %s", exc)

    # PII redact + draft_review post (chunked for Telegram 4096-char cap)
    try:
        from . import draft_review, pii_redactor, six_pager  # noqa: PLC0415
        # pii_redactor signature varies across the codebase; degrade safely
        try:
            redacted = pii_redactor.redact(brief)  # type: ignore[attr-defined]
        except Exception:
            redacted = brief

        chunks = six_pager.chunk_for_telegram(redacted)
        total_chunks = len(chunks)
        log.info("6-pager: redacted %d chars → %d chunk(s)",
                 len(redacted), total_chunks)

        draft: dict = {}
        date_key = now.strftime("%Y-%m-%d")
        for idx, chunk_text in enumerate(chunks, start=1):
            prefix = (f"[{idx}/{total_chunks}]\n"
                      if total_chunks > 1 else "")
            draft = draft_review.post_draft(
                draft_text=prefix + chunk_text,
                destination_chat_id=os.environ.get("REVIEW_CHAT_ID", "review"),
                drafted_by_role="CoS",
                originating_intent_id=(
                    f"six-pager-{date_key}-{idx}of{total_chunks}"
                    if total_chunks > 1 else f"six-pager-{date_key}"
                ),
            )

        log.info("6-pager fired: last_draft_id=%s chunks=%d audio=%s",
                 draft.get("draft_id"),
                 total_chunks,
                 audio_path is not None)
    except Exception as exc:  # noqa: BLE001
        if not _is_test_mode():
            log.warning("6-pager: draft_review post failed: %s", exc)
        return False

    state[STATE_KEY] = now.isoformat()

    # Audit emit (best-effort)
    try:
        from . import audit_emit  # noqa: PLC0415
        audit_emit.row(
            "six_pager_emitted", "CoS",
            draft_id=draft.get("draft_id"),
            audio_attached=audio_path is not None,
            length=len(brief),
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("6-pager: audit_emit suppressed: %s", exc)

    return True


__all__ = ["maybe_fire_daily"]
