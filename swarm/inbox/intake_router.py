"""swarm/inbox/intake_router.py — ContextBot inbound pipeline.

For each bot in `public.context_bots` where `intake_enabled = true`:

1. Long-poll `getUpdates` against the Telegram Bot API using
   `bot.long_poll_offset` as the starting offset.
2. For each Update with a Message:
   - Insert into `public.context_bot_messages` (dedupe via UNIQUE
     constraint on (bot_id, telegram_update_id)).
   - File the message to Linear in `bot.linear_team_key` (optionally
     scoped to `bot.linear_project_id`).
   - Append the message to the wiki at `~/2nd Brain/2nd Brain/Wiki/<bot.wiki_section>`
     under an `## Inbox — <date>` section, or to a per-context inbox
     file if `wiki_section` is unset.
   - If `auto_reply_enabled`, send `greeting_template` back via
     Telegram `sendMessage`.
   - Update `bot.long_poll_offset = update_id + 1`.

Designed to be invoked from a cron job (every minute) or a long-running
daemon. Fire-and-forget per bot — one bot's failure doesn't block
the others.

Public API:
    tick(dry_run: bool = False) -> dict
        Run one full cycle. Returns {bots_polled, messages_filed,
        errors, dry_run}.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger("swarm.inbox.intake_router")

AEST = timezone(timedelta(hours=10))
TELEGRAM_API = "https://api.telegram.org"
DEFAULT_TIMEOUT = 15
LONG_POLL_TIMEOUT = 0  # 0 = short poll; cron calls every minute
WIKI_ROOT = Path(os.environ.get(
    "BRAIN1_WIKI_ROOT",
    str(Path.home() / "2nd Brain" / "2nd Brain" / "Wiki"),
))


@dataclass
class Bot:
    """Snapshot of a context_bots row needed by the intake pipeline."""
    id: str
    bot_username: str
    bot_token: str
    kind: str
    brand: str
    context_id: str
    context_label: str
    linear_team_key: str | None
    linear_project_id: str | None
    wiki_section: str | None
    greeting_template: str | None
    auto_reply_enabled: bool
    long_poll_offset: int
    authorized_chat_ids: list[int]


# ── Supabase access ─────────────────────────────────────────────────────────
def _supabase_url() -> str:
    return os.environ["SUPABASE_UNITE_GROUP_URL"].rstrip("/")


def _supabase_key() -> str:
    return os.environ["SUPABASE_UNITE_GROUP_SERVICE_KEY"]


def _sb_request(method: str, path: str, params: dict | None = None,
                body: Any = None, extra_headers: dict | None = None) -> Any:
    """Make a PostgREST request and return parsed JSON (or None for 204)."""
    url = f"{_supabase_url()}/rest/v1{path}"
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    headers = {
        "apikey": _supabase_key(),
        "Authorization": f"Bearer {_supabase_key()}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as r:
        raw = r.read()
        if not raw:
            return None
        return json.loads(raw)


def load_registry() -> list[Bot]:
    """Return every bot with intake_enabled=true, deserialized to Bot dataclass."""
    rows = _sb_request(
        "GET",
        "/context_bots",
        params={
            "select": "id,bot_username,bot_token,kind,brand,context_id,context_label,"
                      "linear_team_key,linear_project_id,wiki_section,greeting_template,"
                      "auto_reply_enabled,long_poll_offset,authorized_chat_ids",
            "intake_enabled": "eq.true",
            "order": "created_at",
        },
    ) or []
    return [
        Bot(
            id=r["id"],
            bot_username=r["bot_username"],
            bot_token=r["bot_token"],
            kind=r["kind"],
            brand=r["brand"],
            context_id=r["context_id"],
            context_label=r["context_label"],
            linear_team_key=r.get("linear_team_key"),
            linear_project_id=r.get("linear_project_id"),
            wiki_section=r.get("wiki_section"),
            greeting_template=r.get("greeting_template"),
            auto_reply_enabled=bool(r.get("auto_reply_enabled", True)),
            long_poll_offset=int(r.get("long_poll_offset") or 0),
            authorized_chat_ids=list(r.get("authorized_chat_ids") or []),
        )
        for r in rows
    ]


def _update_offset(bot_id: str, offset: int) -> None:
    _sb_request(
        "PATCH",
        "/context_bots",
        params={"id": f"eq.{bot_id}"},
        body={"long_poll_offset": offset},
        extra_headers={"Prefer": "return=minimal"},
    )


def _record_message(*, bot: Bot, update: dict, message: dict, body_text: str,
                    linear_issue: str | None, wiki_path: str | None) -> bool:
    """Insert into context_bot_messages. Returns True if new, False if duplicate."""
    payload = {
        "bot_id": bot.id,
        "context_id": bot.context_id,
        "telegram_update_id": update["update_id"],
        "telegram_message_id": message["message_id"],
        "from_user_id": message["from"]["id"],
        "from_username": message["from"].get("username"),
        "from_name": " ".join(
            filter(None, [message["from"].get("first_name"), message["from"].get("last_name")])
        ) or None,
        "body": body_text,
        "raw_payload": update,
        "filed_linear_issue": linear_issue,
        "filed_wiki_path": wiki_path,
        "filed_at": datetime.now(AEST).isoformat() if (linear_issue or wiki_path) else None,
    }
    try:
        _sb_request(
            "POST", "/context_bot_messages",
            body=payload,
            extra_headers={"Prefer": "return=minimal"},
        )
        return True
    except urllib.error.HTTPError as e:
        if e.code == 409:
            log.info("dedup: %s update_id=%s already filed", bot.bot_username, update["update_id"])
            return False
        raise


# ── Telegram Bot API ────────────────────────────────────────────────────────
def _tg_request(token: str, method: str, params: dict | None = None) -> dict:
    url = f"{TELEGRAM_API}/bot{token}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT + LONG_POLL_TIMEOUT) as r:
        return json.loads(r.read())


def poll_bot(bot: Bot) -> list[dict]:
    """Fetch updates for one bot from its current offset."""
    resp = _tg_request(
        bot.bot_token, "getUpdates",
        {"offset": bot.long_poll_offset, "timeout": LONG_POLL_TIMEOUT,
         "allowed_updates": json.dumps(["message"])},
    )
    if not resp.get("ok"):
        log.warning("getUpdates failed for %s: %s", bot.bot_username, resp)
        return []
    return resp.get("result", [])


def _send_reply(bot: Bot, chat_id: int, text: str) -> None:
    try:
        _tg_request(bot.bot_token, "sendMessage", {"chat_id": chat_id, "text": text})
    except Exception as e:  # noqa: BLE001
        log.warning("auto-reply failed for %s: %s", bot.bot_username, e)


# ── Wiki append ─────────────────────────────────────────────────────────────
def _wiki_path_for(bot: Bot) -> Path:
    if bot.wiki_section:
        return WIKI_ROOT / bot.wiki_section
    # Default: contexts/<id>/inbox.md
    return WIKI_ROOT / "contexts" / bot.context_id / "inbox.md"


def _append_to_wiki(bot: Bot, message: dict, body_text: str) -> str:
    path = _wiki_path_for(bot)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            f"---\ntype: wiki\nupdated: {datetime.now(AEST).date()}\n---\n\n"
            f"# {bot.context_label} — Inbox\n\nMessages routed via @{bot.bot_username}.\n\n"
        )
    ts = datetime.fromtimestamp(message["date"], AEST).strftime("%Y-%m-%d %H:%M")
    sender = message["from"].get("username") or message["from"].get("first_name") or "anon"
    with path.open("a") as f:
        f.write(f"\n### {ts} — @{sender} (telegram)\n\n> {body_text.replace(chr(10), chr(10) + '> ')}\n")
    return str(path)


# ── Linear filing ───────────────────────────────────────────────────────────
def _file_to_linear(bot: Bot, message: dict, body_text: str, *,
                   dry_run: bool = False) -> str | None:
    if not bot.linear_team_key:
        return None
    try:
        from swarm import linear_tools  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover
        log.warning("linear_tools unavailable; skipping Linear filing for %s", bot.bot_username)
        return None
    sender = message["from"].get("username") or message["from"].get("first_name") or "anon"
    title = body_text.strip().split("\n", 1)[0][:120] or f"Inbound from @{sender}"
    description = (
        f"_Filed by @{bot.bot_username} (ContextBot intake)._\n\n"
        f"**From:** @{sender} (Telegram user_id={message['from']['id']})\n"
        f"**Context:** {bot.context_label} (`{bot.context_id}`)\n"
        f"**Sent:** {datetime.fromtimestamp(message['date'], AEST).isoformat()}\n\n"
        f"---\n\n{body_text}\n"
    )
    result = linear_tools.save_issue(
        team=bot.linear_team_key,
        title=title,
        project=bot.linear_project_id,
        description=description,
        labels=["contextbot-intake", f"context:{bot.context_id}"],
        priority=3,
        dry_run=dry_run,
    )
    return result.get("identifier") or result.get("id")


# ── Authorization ───────────────────────────────────────────────────────────
def _is_authorized(bot: Bot, from_user_id: int) -> bool:
    """Whitelist by from_user_id. Empty list = open (default for portfolio bots)."""
    if not bot.authorized_chat_ids:
        return True
    return from_user_id in bot.authorized_chat_ids


# ── Main loop ───────────────────────────────────────────────────────────────
def _process_update(bot: Bot, update: dict, *, dry_run: bool) -> tuple[int, str | None]:
    """Returns (1 if filed else 0, linear_issue_id or None)."""
    message = update.get("message")
    if not message or not message.get("text"):
        return 0, None
    if not _is_authorized(bot, message["from"]["id"]):
        log.info("unauth: %s rejected user_id=%s", bot.bot_username, message["from"]["id"])
        return 0, None
    body_text = message["text"]
    wiki_path = None
    linear_issue = None
    if not dry_run:
        wiki_path = _append_to_wiki(bot, message, body_text)
        linear_issue = _file_to_linear(bot, message, body_text, dry_run=False)
    is_new = _record_message(
        bot=bot, update=update, message=message, body_text=body_text,
        linear_issue=linear_issue, wiki_path=wiki_path,
    ) if not dry_run else True
    if is_new and not dry_run and bot.auto_reply_enabled and bot.greeting_template:
        reply = bot.greeting_template
        if linear_issue:
            reply = f"{reply}\n\nFiled as {linear_issue}."
        _send_reply(bot, message["chat"]["id"], reply)
    return (1 if is_new else 0), linear_issue


def tick(*, dry_run: bool = False) -> dict:
    """Run one full intake cycle across every intake-enabled bot."""
    bots = load_registry()
    polled = 0
    filed = 0
    errors: list[str] = []
    for bot in bots:
        try:
            updates = poll_bot(bot)
            polled += 1
            if not updates:
                continue
            highest = bot.long_poll_offset
            for update in updates:
                try:
                    n, _ = _process_update(bot, update, dry_run=dry_run)
                    filed += n
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{bot.bot_username}:update_{update['update_id']}: {e}")
                    log.exception("processing update failed")
                highest = max(highest, update["update_id"] + 1)
            if highest != bot.long_poll_offset and not dry_run:
                _update_offset(bot.id, highest)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{bot.bot_username}:poll: {e}")
            log.exception("bot poll failed")
    return {"bots_polled": polled, "messages_filed": filed,
            "errors": errors, "dry_run": dry_run}


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    import sys
    dry = "--dry-run" in sys.argv
    result = tick(dry_run=dry)
    print(json.dumps(result, indent=2, default=str))
