"""swarm/margot_inflight.py — harvest async Margot deep_research_max results.

Board meeting harvests entries tagged ``board_meeting:*``. Telegram turns
tag ``margot_chat:{chat_id}`` so the next ``handle_turn`` can deliver
completed research without a silent drop.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.margot_inflight")

REPO_ROOT = Path(__file__).resolve().parents[1]
INFLIGHT_LOG = REPO_ROOT / ".harness" / "swarm" / "margot_inflight.jsonl"


def margot_chat_session_id(chat_id: str) -> str:
    return f"margot_chat:{chat_id}"


def _read_entries() -> list[dict[str, Any]]:
    if not INFLIGHT_LOG.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in INFLIGHT_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except Exception as exc:  # noqa: BLE001
        log.warning("margot_inflight: read failed (%s)", exc)
    return entries


def _write_entries(entries: list[dict[str, Any]]) -> None:
    INFLIGHT_LOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = INFLIGHT_LOG.with_suffix(".jsonl.tmp")
    tmp.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
        + ("\n" if entries else ""),
        encoding="utf-8",
    )
    os.replace(tmp, INFLIGHT_LOG)


def _summary_from_result(result: dict[str, Any], *, topic: str) -> str:
    report = (
        result.get("report")
        or result.get("text")
        or result.get("summary")
        or result.get("content")
        or ""
    )
    if isinstance(report, str) and report.strip():
        return report.strip()
    return f"Deep research on «{topic}» completed (no report body returned)."


def harvest_completed_for_chat(
    chat_id: str,
    *,
    max_age_days: int = 32,
) -> list[dict[str, Any]]:
    """Return completed async research for ``chat_id``; mark entries harvested.

    Each finding matches the ``research_findings`` shape used by
    ``build_prompt_with_research``: ``{topic, depth, summary, error}``.
    """
    if not chat_id:
        return []
    try:
        from swarm.margot_tools import check_research  # noqa: PLC0415
    except ImportError:
        return []

    session_prefix = margot_chat_session_id(chat_id)
    entries = _read_entries()
    if not entries:
        return []

    now = datetime.now(timezone.utc)
    cutoff_iso = (now - timedelta(days=max_age_days)).isoformat()
    findings: list[dict[str, Any]] = []
    mutated = False

    for entry in entries:
        sid = entry.get("originating_session_id") or ""
        entry_chat = entry.get("chat_id") or ""
        if sid != session_prefix and entry_chat != chat_id:
            continue
        if sid.startswith("board_meeting:"):
            continue
        if entry.get("status") not in (None, "dispatched"):
            continue

        ts = entry.get("ts", "")
        if ts and ts < cutoff_iso:
            entry["status"] = "harvested:expired"
            mutated = True
            continue

        interaction_id = entry.get("interaction_id")
        if not interaction_id:
            continue
        try:
            result = check_research(interaction_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("margot_inflight: check_research(%s) raised %s",
                        interaction_id, exc)
            continue

        if not isinstance(result, dict):
            continue
        if result.get("error"):
            log.warning("margot_inflight: check_research(%s) error: %s",
                        interaction_id, result.get("error"))
            continue

        status = (result.get("status") or "").lower()
        if status in ("processing", "dispatched", "pending", "running"):
            continue
        if status in ("failed", "error"):
            entry["status"] = "harvested:failed"
            mutated = True
            continue
        if status not in ("completed", "complete", "done", "success"):
            continue

        topic = str(entry.get("topic") or "async research")
        findings.append({
            "topic": topic,
            "depth": "deep",
            "summary": _summary_from_result(result, topic=topic),
            "error": None,
            "interaction_id": interaction_id,
        })
        entry["status"] = "harvested"
        entry["harvested_at"] = now.isoformat()
        mutated = True
        log.info("margot_inflight: harvested %s for chat=%s topic=%r",
                 interaction_id, chat_id, topic[:60])

    if mutated:
        try:
            _write_entries(entries)
        except Exception as exc:  # noqa: BLE001
            log.warning("margot_inflight: rewrite failed (%s)", exc)

    return findings


__all__ = [
    "INFLIGHT_LOG",
    "harvest_completed_for_chat",
    "margot_chat_session_id",
]
