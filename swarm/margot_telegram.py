"""swarm/margot_telegram.py — direct Telegram delivery for Margot user replies.

Margot founder replies must target the inbound ``chat_id`` and may attach
voice. ``telegram_alerts.send`` is for swarm [AGENT OUTPUT] alerts to a
global chat — not for conversational Margot turns.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger("swarm.margot_telegram")

_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_MAX_MESSAGE_CHARS = 3900


def _bot_token() -> str:
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def _post_multipart(
    token: str,
    method: str,
    fields: dict[str, str],
    *,
    file_field: str,
    file_path: Path,
    mime: str = "audio/mpeg",
) -> bool:
    import uuid

    boundary = f"----MargotBoundary{uuid.uuid4().hex}"
    body = bytearray()
    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
        )
        body.extend(f"{value}\r\n".encode())
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{file_path.name}"\r\n'
        ).encode(),
    )
    body.extend(f"Content-Type: {mime}\r\n\r\n".encode())
    body.extend(file_path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        _API_BASE.format(token=token, method=method),
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return bool(payload.get("ok"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        log.warning("margot_telegram: %s failed (%s)", method, exc)
        return False


def _post_json(token: str, method: str, payload: dict[str, str]) -> bool:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _API_BASE.format(token=token, method=method),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return bool(body.get("ok"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        log.warning("margot_telegram: %s failed (%s)", method, exc)
        return False


def send_margot_reply(
    *,
    chat_id: str,
    text: str,
    reply_to_message_id: str | None = None,
    audio_path: Path | None = None,
) -> bool:
    """Send Margot's reply to the founder's chat. Voice is best-effort."""
    token = _bot_token()
    if not token:
        log.warning("margot_telegram: TELEGRAM_BOT_TOKEN missing — log only")
        log.info("margot reply (chat=%s, audio=%s): %s",
                 chat_id, audio_path is not None, text[:500])
        return False

    ok = True
    if audio_path is not None and audio_path.exists():
        fields: dict[str, str] = {"chat_id": str(chat_id)}
        if reply_to_message_id:
            fields["reply_to_message_id"] = str(reply_to_message_id)
        voice_ok = _post_multipart(
            token, "sendVoice", fields,
            file_field="voice", file_path=audio_path,
        )
        ok = voice_ok and ok

    chunks = [text[i:i + _MAX_MESSAGE_CHARS]
              for i in range(0, max(len(text), 1), _MAX_MESSAGE_CHARS)]
    for idx, chunk in enumerate(chunks):
        payload: dict[str, str] = {
            "chat_id": str(chat_id),
            "text": chunk or "(empty)",
        }
        if reply_to_message_id and idx == 0:
            payload["reply_to_message_id"] = str(reply_to_message_id)
        if not _post_json(token, "sendMessage", payload):
            ok = False
    return ok


__all__ = ["send_margot_reply"]
