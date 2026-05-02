"""Shared Telegram delivery helpers for rendered media.

Extracted from `scripts/daily_video_sender.py` so both the existing daily
NotebookLM job and the new remotion-render-pipeline can ship MP4s via the
same code path.

Environment:
- TELEGRAM_BOT_TOKEN (required) — bot token from BotFather.
- TELEGRAM_CHAT_ID (default: "8792816988") — destination chat.

Behaviour:
- send_telegram_message: plain text (HTML mode).
- send_telegram_video: streams a video file. Returns True on HTTP 200.
- send_telegram_document: fallback path when video upload fails or file is
  too large for the inline-video API. Telegram caps inline video at ~50 MB;
  document attachments tolerate up to 2 GB.
- send_telegram_video_or_link: convenience wrapper — if the file is over
  TELEGRAM_INLINE_LIMIT_MB (default 45), sends the provided URL as a text
  message; else uploads the file inline.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8792816988")
TELEGRAM_INLINE_LIMIT_MB = int(os.environ.get("TELEGRAM_INLINE_LIMIT_MB", "45"))


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def send_telegram_message(text: str, *, chat_id: Optional[str] = None) -> bool:
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("[telegram] no bot token — message dropped: %s", text[:80])
        return False
    try:
        r = httpx.post(
            _api("sendMessage"),
            json={
                "chat_id": chat_id or TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        return r.status_code == 200
    except Exception as exc:  # noqa: BLE001 — best-effort delivery
        logger.error("[telegram] sendMessage failed: %s", exc)
        return False


def send_telegram_video(
    video_path: Path,
    caption: str,
    *,
    chat_id: Optional[str] = None,
) -> bool:
    """Stream a video file inline. Returns True on HTTP 200."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("[telegram] no bot token — would send: %s", video_path)
        return False
    try:
        with open(video_path, "rb") as fh:
            r = httpx.post(
                _api("sendVideo"),
                data={
                    "chat_id": chat_id or TELEGRAM_CHAT_ID,
                    "caption": caption,
                },
                files={"video": (video_path.name, fh, "video/mp4")},
                timeout=120,
            )
        return r.status_code == 200
    except Exception as exc:  # noqa: BLE001
        logger.error("[telegram] sendVideo failed: %s", exc)
        return False


def send_telegram_document(
    file_path: Path,
    caption: str,
    *,
    chat_id: Optional[str] = None,
) -> bool:
    """Fallback path — sends as document (up to 2 GB)."""
    if not TELEGRAM_BOT_TOKEN:
        return False
    try:
        with open(file_path, "rb") as fh:
            r = httpx.post(
                _api("sendDocument"),
                data={
                    "chat_id": chat_id or TELEGRAM_CHAT_ID,
                    "caption": caption,
                },
                files={"document": (file_path.name, fh, "application/octet-stream")},
                timeout=120,
            )
        return r.status_code == 200
    except Exception as exc:  # noqa: BLE001
        logger.error("[telegram] sendDocument failed: %s", exc)
        return False


def send_telegram_video_or_link(
    video_path: Path,
    caption: str,
    *,
    fallback_url: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """If the file is over the inline limit, ship the URL via text; else upload inline.

    Returns True if some form of delivery (inline upload or URL message) succeeded.
    """
    size_mb = video_path.stat().st_size / (1024 * 1024) if video_path.exists() else 0
    if size_mb > TELEGRAM_INLINE_LIMIT_MB and fallback_url:
        return send_telegram_message(
            f"{caption}\n\n<a href=\"{fallback_url}\">Download video ({size_mb:.1f} MB)</a>",
            chat_id=chat_id,
        )
    if send_telegram_video(video_path, caption, chat_id=chat_id):
        return True
    # Last resort: try as document.
    return send_telegram_document(video_path, caption, chat_id=chat_id)


__all__ = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "send_telegram_message",
    "send_telegram_video",
    "send_telegram_document",
    "send_telegram_video_or_link",
]
