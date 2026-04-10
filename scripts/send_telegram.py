#!/usr/bin/env python3
"""
send_telegram.py — Push a message to Phill's Telegram via the piceoagent_bot.

Purpose
-------
Provide a zero-dependency, single-file helper that any Claude session, cron job,
scheduled task, or CI run can use to push status updates to the founder's phone.
Reads bot token and allowed user ID from the telegram-bot/.env file (or from
environment variables if set).

Usage
-----
From the command line:

    python3 scripts/send_telegram.py "Hello from Pi-CEO"

Or piped:

    echo "Build finished" | python3 scripts/send_telegram.py

Or from Python:

    from scripts.send_telegram import send_telegram
    send_telegram("Build finished — 39 tests green")

Exit codes
----------
    0 — message delivered
    1 — environment not set up (token missing, user ID missing)
    2 — Telegram API returned an error
    3 — network error

Environment
-----------
Required (either set as env vars OR present in telegram-bot/.env):
    TELEGRAM_BOT_TOKEN  — the bot API token
    ALLOWED_USERS       — comma-separated list of allowed chat/user IDs
                          (first ID is used as the default recipient)

Optional:
    TELEGRAM_CHAT_ID    — explicit chat ID override

Style contract: no first-person business language, no filler words.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

# Telegram text limit per send_message call
TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def _load_env_file(env_path: Path) -> dict[str, str]:
    """Parse a .env file into a dict. Returns empty dict if file is absent."""
    if not env_path.exists():
        return {}
    result: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip().strip('"').strip("'")
            result[key] = value
    return result


def _resolve_config() -> tuple[str, str]:
    """Return (bot_token, chat_id) from environment or .env file.

    Raises SystemExit(1) if neither source has what is needed.
    """
    # Try process environment first
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    allowed_users = os.environ.get("ALLOWED_USERS", "")

    # Fall back to the telegram-bot .env file
    if not token or not allowed_users:
        repo_root = Path(__file__).resolve().parent.parent
        env_path = repo_root / "telegram-bot" / ".env"
        env_vars = _load_env_file(env_path)
        token = token or env_vars.get("TELEGRAM_BOT_TOKEN", "")
        allowed_users = allowed_users or env_vars.get("ALLOWED_USERS", "")
        chat_id = chat_id or env_vars.get("TELEGRAM_CHAT_ID", "")

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in environment or .env file", file=sys.stderr)
        raise SystemExit(1)

    # If no explicit chat_id, use the first allowed user
    if not chat_id:
        if not allowed_users:
            print("ERROR: neither TELEGRAM_CHAT_ID nor ALLOWED_USERS is set", file=sys.stderr)
            raise SystemExit(1)
        chat_id = allowed_users.split(",")[0].strip()

    return token, chat_id


def _split_message(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long message into chunks at paragraph boundaries."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remainder = text
    while remainder:
        if len(remainder) <= max_length:
            chunks.append(remainder)
            break
        # Prefer paragraph, then line, then space, then hard cut
        for sep in ("\n\n", "\n", " "):
            pos = remainder.rfind(sep, 0, max_length)
            if pos > 0:
                chunks.append(remainder[:pos])
                remainder = remainder[pos:].lstrip()
                break
        else:
            chunks.append(remainder[:max_length])
            remainder = remainder[max_length:]
    return chunks


def send_telegram(
    text: str,
    *,
    chat_id: Optional[str] = None,
    bot_token: Optional[str] = None,
    parse_mode: Optional[str] = None,
    disable_preview: bool = True,
) -> list[int]:
    """Send one or more messages to Telegram. Returns list of message IDs.

    Splits messages longer than 4096 chars at paragraph boundaries.

    Raises:
        RuntimeError: on Telegram API error
        urllib.error.URLError: on network failure
    """
    if not bot_token or not chat_id:
        resolved_token, resolved_chat = _resolve_config()
        bot_token = bot_token or resolved_token
        chat_id = chat_id or resolved_chat

    chunks = _split_message(text)
    message_ids: list[int] = []

    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": disable_preview,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=data,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Telegram HTTP {exc.code}: {error_body}") from exc

        if not body.get("ok"):
            raise RuntimeError(f"Telegram API error: {body}")

        message_ids.append(body["result"]["message_id"])

    return message_ids


def main() -> int:
    # Collect message text: from argv if given, otherwise from stdin
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        if sys.stdin.isatty():
            print("Usage: send_telegram.py <message>  OR  echo msg | send_telegram.py", file=sys.stderr)
            return 1
        text = sys.stdin.read().strip()

    if not text:
        print("ERROR: empty message", file=sys.stderr)
        return 1

    try:
        ids = send_telegram(text)
        print(f"Sent {len(ids)} message(s). IDs: {ids}")
        return 0
    except RuntimeError as exc:
        print(f"Telegram API error: {exc}", file=sys.stderr)
        return 2
    except urllib.error.URLError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
