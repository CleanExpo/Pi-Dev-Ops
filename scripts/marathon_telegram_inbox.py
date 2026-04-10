#!/usr/bin/env python3
"""marathon_telegram_inbox.py — the INBOUND half of the marathon Telegram loop.

Purpose
-------
While Phill is away from the office, he wants to send new ideas, fix commands,
or briefing requests to the marathon build system from his phone. This script
is the bridge: it polls Telegram's getUpdates API, writes every new message
from an allowed chat to `.harness/telegram-inbox/` as a structured JSON file,
and tracks the last-seen update_id in `.harness/telegram-inbox/.offset` so the
same message is never processed twice.

The watchdog (marathon_watchdog.py) drains the inbox on each 30-minute run and
routes each message to the right handler (fix / brief me / idea / plain text).
This script has ONE job: reliable ingest. Routing logic lives in the watchdog.

Zero external dependencies. Designed to run from a scheduled task every 5 min.

Message filter
--------------
Only messages from chat IDs listed in ALLOWED_USERS (or TELEGRAM_CHAT_ID) are
accepted. Everything else is silently dropped — this is the first line of
defence against random bot traffic.

Inbox file format
-----------------
`.harness/telegram-inbox/<update_id>.json`

```
{
  "update_id": 42,
  "message_id": 123,
  "chat_id": "8066...",
  "from": "Phill",
  "date": "2026-04-11T23:45:00+00:00",
  "text": "idea: add a RSS feed for the lessons file",
  "processed": false,
  "received_at": "2026-04-11T23:45:07+00:00"
}
```

The `processed` flag is flipped to `true` by the watchdog after it routes the
message. Processed files older than 7 days are garbage-collected on each run.

Exit codes
----------
  0 — poll succeeded, zero or more new messages ingested
  1 — configuration missing (token / chat id)
  2 — Telegram API returned an error
  3 — network failure (retry next run)

Environment
-----------
    TELEGRAM_BOT_TOKEN   — bot API token (required)
    ALLOWED_USERS        — comma-separated chat IDs (required if no explicit chat)
    TELEGRAM_CHAT_ID     — explicit single chat override (optional)
    TAO_INBOX_DRY        — if "1", do not write files, just print what would happen

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
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = REPO_ROOT / ".harness" / "telegram-inbox"
OFFSET_FILE = INBOX_DIR / ".offset"
GC_MAX_AGE_DAYS = 7


def _load_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    result: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$", line)
        if m:
            result[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return result


def _resolve_config() -> tuple[str, set[str]]:
    """Return (bot_token, allowed_chat_ids)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    allowed = os.environ.get("ALLOWED_USERS", "")
    explicit_chat = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not allowed:
        env_vars = _load_env_file(REPO_ROOT / "telegram-bot" / ".env")
        token = token or env_vars.get("TELEGRAM_BOT_TOKEN", "")
        allowed = allowed or env_vars.get("ALLOWED_USERS", "")
        explicit_chat = explicit_chat or env_vars.get("TELEGRAM_CHAT_ID", "")

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN missing", file=sys.stderr)
        raise SystemExit(1)

    chat_ids: set[str] = set()
    if allowed:
        chat_ids.update(c.strip() for c in allowed.split(",") if c.strip())
    if explicit_chat:
        chat_ids.add(explicit_chat.strip())

    if not chat_ids:
        print("ERROR: ALLOWED_USERS / TELEGRAM_CHAT_ID missing", file=sys.stderr)
        raise SystemExit(1)

    return token, chat_ids


def _read_offset() -> int:
    if not OFFSET_FILE.exists():
        return 0
    try:
        return int(OFFSET_FILE.read_text().strip() or "0")
    except Exception:
        return 0


def _write_offset(offset: int) -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(offset))


def _get_updates(token: str, offset: int, timeout_sec: int = 0) -> list[dict]:
    """Call Telegram getUpdates. Returns list of update dicts."""
    params = {
        "offset": offset,
        "timeout": timeout_sec,
        "allowed_updates": json.dumps(["message"]),
    }
    url = f"https://api.telegram.org/bot{token}/getUpdates?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(f"Telegram API error: {body}")
    return body.get("result", [])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ingest_update(update: dict, allowed_chat_ids: set[str], dry_run: bool) -> Optional[Path]:
    """Write one update to the inbox if it passes the allowlist. Returns path or None."""
    msg = update.get("message")
    if not msg:
        return None
    chat = msg.get("chat", {})
    chat_id = str(chat.get("id", ""))
    if chat_id not in allowed_chat_ids:
        return None

    text = msg.get("text", "").strip()
    if not text:
        return None  # drop stickers, photos, etc. — text only for now

    sender = msg.get("from", {})
    sender_name = sender.get("first_name") or sender.get("username") or "unknown"

    # Convert Telegram unix timestamp to ISO
    unix_ts = msg.get("date")
    if unix_ts:
        msg_date = datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()
    else:
        msg_date = _now_iso()

    payload = {
        "update_id": update["update_id"],
        "message_id": msg.get("message_id"),
        "chat_id": chat_id,
        "from": sender_name,
        "date": msg_date,
        "text": text,
        "processed": False,
        "received_at": _now_iso(),
    }

    filename = f"{update['update_id']:012d}.json"
    path = INBOX_DIR / filename

    if dry_run:
        print(f"[DRY] would write {path.name}: {text[:80]}")
        return path

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _gc_old_files() -> int:
    """Delete processed inbox files older than GC_MAX_AGE_DAYS. Returns count deleted."""
    if not INBOX_DIR.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=GC_MAX_AGE_DAYS)
    deleted = 0
    for path in INBOX_DIR.glob("*.json"):
        if path.name.startswith("."):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not data.get("processed"):
                continue
            received = data.get("received_at", "")
            if received:
                received_dt = datetime.fromisoformat(received)
                if received_dt < cutoff:
                    path.unlink()
                    deleted += 1
        except Exception:
            # Malformed file — leave it alone for manual inspection
            continue
    return deleted


def main() -> int:
    dry_run = os.environ.get("TAO_INBOX_DRY", "0") == "1"

    try:
        token, allowed_chat_ids = _resolve_config()
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1

    offset = _read_offset()
    next_offset = offset  # will advance past every processed update

    try:
        updates = _get_updates(token, offset)
    except urllib.error.URLError as exc:
        print(f"network error: {exc}", file=sys.stderr)
        return 3
    except RuntimeError as exc:
        print(f"telegram api error: {exc}", file=sys.stderr)
        return 2

    ingested = 0
    dropped = 0
    for update in updates:
        result = _ingest_update(update, allowed_chat_ids, dry_run)
        if result is not None:
            ingested += 1
        else:
            dropped += 1
        next_offset = max(next_offset, update["update_id"] + 1)

    if not dry_run and next_offset != offset:
        _write_offset(next_offset)

    gc_count = _gc_old_files() if not dry_run else 0

    print(
        f"telegram-inbox: polled={len(updates)} ingested={ingested} "
        f"dropped={dropped} gc={gc_count} offset={next_offset}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
