"""swarm/inbox/botfather_minter.py — autonomous BotFather mint pipeline.

Mints the 8 ContextBots deferred by the 2026-05-14 BotFather rate-limit
(see `~/2nd Brain/2nd Brain/Wiki/incident-botfather-rate-limit-2026-05-14.md`).
Designed to be invoked once by LaunchAgent `ai.pidev.botfather-minter` at
Fri 15 May 2026 13:20 AEST (03:20 UTC) — the moment the 23h BotFather
rate-limit clears — but is safe to re-run: every mint is idempotent against
the queue's `status` field, and successful mints are registered into
`public.context_bots`.

Pipeline per queue line (status="pending"):

1. Open a USER Telegram session via Telethon (MTProto, NOT the Bot API —
   bots can't talk to bots, so we drive Phill's user account).
2. Send `/newbot` to @BotFather (chat id 93372553), then the display name,
   then the username. Parse the reply for the token.
3. On success: insert into `public.context_bots` via PostgREST using the
   same `_sb_request` pattern as `intake_router.py`. Mark queue line
   `status="minted"` + token + minted_at.
4. On username-taken: mark `status="failed"` with reason, continue.
5. On rate-limit ("Too many attempts. Please try again in N seconds."):
   parse N, sleep N+5, retry. Cap cumulative wait at 30 min — if exceeded,
   persist `rate_limited_until` to the queue header file and return early
   so the LaunchAgent can resume on the next fire.

Persistence:
  Queue file: `.harness/swarm/botfather_queue.jsonl` (one JSON per line).
  Each write rewrites the whole file atomically (write to tempfile in the
  same dir, then `os.replace`) so a SIGKILL mid-write cannot corrupt it.
  An optional companion `botfather_queue.state.json` records cross-run
  state (e.g. last rate-limit clearance time).

Dry-run:
  `mint_queue(dry_run=True)` prints what WOULD be sent without touching
  Telegram or Supabase. The queue's persisted status is also untouched.

------------------------------------------------------------------------
Telethon setup (one-time, run by Phill before the LaunchAgent fires):

  1. Visit https://my.telegram.org → "API development tools" → create app.
     Record API_ID (int) and API_HASH (32-char hex).
  2. Add to `~/.hermes/.env`:
        TELEGRAM_API_ID=<int>
        TELEGRAM_API_HASH=<hex>
        TELEGRAM_PHONE=+61<rest of number>
  3. Install Telethon into the pyenv 3.13.13 env (NOT global):
        /Users/phill-mac/.pyenv/versions/3.13.13/bin/pip install telethon
  4. First-time login (creates the session file):
        cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
        /Users/phill-mac/.pyenv/versions/3.13.13/bin/python -c \\
          "from swarm.inbox.botfather_minter import _login; _login()"
     Telethon will prompt for the SMS code + 2FA password (if set).
     Session is cached at `~/.hermes/sessions/botfather_minter.session`.
  5. Verify the queue file matches the 8 bots you want minted:
        cat .harness/swarm/botfather_queue.jsonl
  6. Arm the LaunchAgent:
        launchctl load ~/Library/LaunchAgents/ai.pidev.botfather-minter.plist
  7. After Fri 15 May 13:20 AEST mint run, unload to prevent monthly
     recurrence (LaunchAgent uses StartCalendarInterval Day=15 Month=5):
        launchctl unload ~/Library/LaunchAgents/ai.pidev.botfather-minter.plist

Public API:
    mint_queue(*, dry_run: bool = False, queue_path: Path | None = None,
               max_wait_seconds: int = 1800) -> dict
        Drains the pending queue. Returns:
        {minted: int, skipped: int, errors: list[str],
         rate_limited_until: str | None, dry_run: bool}
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.inbox.botfather_minter")

AEST = timezone(timedelta(hours=10))
DEFAULT_TIMEOUT = 20
BOTFATHER_USERNAME = "BotFather"
BOTFATHER_CHAT_ID = 93372553  # static; documented in module brief
DEFAULT_QUEUE_PATH = Path(__file__).resolve().parents[2] / ".harness" / "swarm" / "botfather_queue.jsonl"
DEFAULT_STATE_PATH = DEFAULT_QUEUE_PATH.with_suffix(".state.json")
SESSION_PATH = Path(os.environ.get(
    "BOTFATHER_MINTER_SESSION",
    str(Path.home() / ".hermes" / "sessions" / "botfather_minter.session"),
))
MAX_WAIT_SECONDS_DEFAULT = 1800  # 30 min cap; cron resumes after
INTER_MINT_SLEEP = float(os.environ.get("BOTFATHER_INTER_MINT_SLEEP", "8"))
REPLY_POLL_TIMEOUT = float(os.environ.get("BOTFATHER_REPLY_TIMEOUT", "30"))
REPLY_POLL_INTERVAL = 0.5

# BotFather text-fragment patterns. The wording can drift; keep these loose.
# `_RE_RATE_LIMIT` matches the trigger ("too many attempts" anywhere in the
# message) — `_RE_RATE_LIMIT_QTY` separately extracts the numeric duration so
# we never confuse "matched the phrase" with "no number found".
_RE_RATE_LIMIT = re.compile(
    r"too many attempts|flood|please try again",
    re.IGNORECASE,
)
_RE_RATE_LIMIT_QTY = re.compile(
    r"(\d+)\s*(seconds?|minutes?|hours?|s\b|m\b|h\b)",
    re.IGNORECASE,
)
_RE_USERNAME_TAKEN = re.compile(
    r"(sorry, this username is already taken|that username is taken|i'm afraid this name is already taken)",
    re.IGNORECASE,
)
_RE_TOKEN = re.compile(r"\b(\d{6,12}:[A-Za-z0-9_-]{30,})\b")
_RE_INVALID = re.compile(
    r"(sorry, the username must end in.*bot|usernames must.*letters|invalid)",
    re.IGNORECASE,
)


# ── Supabase access (mirrors intake_router._sb_request exactly) ─────────────
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


# ── Queue persistence ───────────────────────────────────────────────────────
def load_queue(path: Path = DEFAULT_QUEUE_PATH) -> list[dict]:
    """Load JSONL queue. Skips malformed lines, logs each."""
    if not path.exists():
        return []
    out: list[dict] = []
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            log.warning("queue line %d malformed (skipped): %s", i, e)
    return out


def _atomic_write_queue(items: list[dict], path: Path) -> None:
    """Rewrite the queue file atomically — write tempfile in same dir, then replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".botfather_queue.", suffix=".jsonl", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            for item in items:
                f.write(json.dumps(item, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        # Best-effort cleanup of the tempfile if replace() didn't happen.
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _update_queue_line(items: list[dict], context_id: str, updates: dict,
                       path: Path) -> list[dict]:
    """Apply `updates` to the queue line matching `context_id`, persist atomically."""
    for it in items:
        if it.get("context_id") == context_id:
            it.update(updates)
            break
    _atomic_write_queue(items, path)
    return items


def _write_state(state: dict, path: Path = DEFAULT_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".botfather_state.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(state, default=str, indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


# ── Telethon shim ───────────────────────────────────────────────────────────
def _import_telethon():
    """Import Telethon lazily so tests don't require it. Raises a clear error
    pointing at the install command if missing."""
    try:
        from telethon.sync import TelegramClient  # type: ignore[import-not-found]
        return TelegramClient
    except ImportError as e:
        raise RuntimeError(
            "telethon not installed. Run: "
            "/Users/phill-mac/.pyenv/versions/3.13.13/bin/pip install telethon"
        ) from e


def _login() -> None:  # pragma: no cover — interactive one-shot
    """One-time interactive login. Caches `.session` for headless future runs."""
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    phone = os.environ["TELEGRAM_PHONE"]
    TelegramClient = _import_telethon()
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    client.start(phone=phone)
    print(f"Session cached at {SESSION_PATH}")
    client.disconnect()


def _open_client():
    """Open Telethon client against the cached session. No interactive prompt."""
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    TelegramClient = _import_telethon()
    if not SESSION_PATH.exists():
        raise RuntimeError(
            f"No cached session at {SESSION_PATH}. Run "
            "`python -c 'from swarm.inbox.botfather_minter import _login; _login()'` "
            "interactively first."
        )
    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    client.connect()
    if not client.is_user_authorized():
        client.disconnect()
        raise RuntimeError(
            "Cached session is unauthorized. Re-run _login() to refresh."
        )
    return client


# ── BotFather conversation ──────────────────────────────────────────────────
def _wait_for_reply(client, after_ts: float, *, timeout: float = REPLY_POLL_TIMEOUT) -> str:
    """Poll BotFather's chat for a NEW message strictly after `after_ts`. Returns
    the message text. Raises TimeoutError if nothing arrives within `timeout`."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # iter_messages returns newest-first; limit=1 is the most recent.
        for msg in client.iter_messages(BOTFATHER_USERNAME, limit=3):
            if msg.date is None:
                continue
            if msg.date.timestamp() > after_ts and msg.text:
                return msg.text
        time.sleep(REPLY_POLL_INTERVAL)
    raise TimeoutError(f"no BotFather reply within {timeout}s")


def _parse_rate_limit_seconds(text: str) -> int | None:
    """Return seconds to wait if BotFather replied with a rate-limit, else None."""
    if not _RE_RATE_LIMIT.search(text):
        return None
    qty_match = _RE_RATE_LIMIT_QTY.search(text)
    if not qty_match:
        # Phrase matched but no number — assume 60s as a conservative fallback.
        return 60
    qty = int(qty_match.group(1))
    unit = qty_match.group(2).lower()
    if unit.startswith("h"):
        return qty * 3600
    if unit.startswith("m"):
        return qty * 60
    return qty


def _send(client, text: str) -> float:
    """Send a message to BotFather and return the timestamp it was sent at."""
    sent_at = time.time()
    client.send_message(BOTFATHER_USERNAME, text)
    return sent_at


def _mint_one(client, line: dict) -> tuple[str, str | None, str | None]:
    """Mint one bot via BotFather.

    Returns (status, token, reason) where:
        status ∈ {"minted", "rate_limited:<seconds>", "username_taken",
                  "invalid", "error:<short>"}
        token  is the bot token on success, else None
        reason is a human-readable detail on failure paths, else None
    """
    display = line["display_name"]
    username = line["bot_username"].lstrip("@")

    # Step 1 — /newbot
    after = _send(client, "/newbot")
    reply = _wait_for_reply(client, after)
    wait_s = _parse_rate_limit_seconds(reply)
    if wait_s is not None:
        return f"rate_limited:{wait_s}", None, reply.strip()[:200]

    # Step 2 — display name
    after = _send(client, display)
    reply = _wait_for_reply(client, after)
    wait_s = _parse_rate_limit_seconds(reply)
    if wait_s is not None:
        return f"rate_limited:{wait_s}", None, reply.strip()[:200]

    # Step 3 — username
    after = _send(client, username)
    reply = _wait_for_reply(client, after)
    wait_s = _parse_rate_limit_seconds(reply)
    if wait_s is not None:
        return f"rate_limited:{wait_s}", None, reply.strip()[:200]
    if _RE_USERNAME_TAKEN.search(reply):
        return "username_taken", None, reply.strip()[:200]
    if _RE_INVALID.search(reply) and not _RE_TOKEN.search(reply):
        return "invalid", None, reply.strip()[:200]
    tok = _RE_TOKEN.search(reply)
    if tok:
        return "minted", tok.group(1), None
    return "error:unparsed", None, reply.strip()[:200]


# ── Greeting templates (matches existing context_bots rows) ─────────────────
def _default_greeting(line: dict) -> str:
    if line.get("kind") == "client":
        return (
            f"Thanks — message received and filed under "
            f"{line['display_name']}. Phill will be across this shortly."
        )
    return (
        f"Filed to {line['display_name']} context. The swarm will pick this up."
    )


# ── Supabase insert ─────────────────────────────────────────────────────────
def _insert_context_bot(line: dict, token: str) -> None:
    """Insert the minted bot into public.context_bots."""
    payload = {
        "bot_username": line["bot_username"].lstrip("@"),
        "bot_token": token,
        "kind": line["kind"],
        "brand": line["brand"],
        "context_id": line["context_id"],
        "context_label": line["display_name"],
        "linear_team_key": line.get("linear_team_key"),
        "linear_project_id": line.get("linear_project_id"),
        "wiki_section": line.get("wiki_section"),
        "greeting_template": line.get("greeting_template") or _default_greeting(line),
        "auto_reply_enabled": bool(line.get("auto_reply_enabled", True)),
        "intake_enabled": bool(line.get("intake_enabled", True)),
        "authorized_chat_ids": line.get("authorized_chat_ids", []),
        "metadata": {
            "client_email": line.get("client_email"),
            "minted_by": "botfather_minter",
            "minted_at": datetime.now(AEST).isoformat(),
        },
        "client_email": line.get("client_email"),
        "client_display_name": line.get("client_display_name"),
        "provision_status": "live",
        "provisioned_at": datetime.now(AEST).isoformat(),
    }
    _sb_request(
        "POST", "/context_bots",
        body=payload,
        extra_headers={"Prefer": "return=minimal"},
    )


# ── Main loop ───────────────────────────────────────────────────────────────
def mint_queue(*, dry_run: bool = False,
               queue_path: Path | None = None,
               max_wait_seconds: int = MAX_WAIT_SECONDS_DEFAULT) -> dict:
    """Drain pending queue lines. Returns a summary dict."""
    path = queue_path or DEFAULT_QUEUE_PATH
    items = load_queue(path)
    pending = [it for it in items if it.get("status") == "pending"]
    if not pending:
        return {"minted": 0, "skipped": 0, "errors": [],
                "rate_limited_until": None, "dry_run": dry_run,
                "pending": 0}

    minted = 0
    skipped = 0
    errors: list[str] = []
    rate_limited_until: str | None = None
    total_wait = 0.0

    client = None
    if not dry_run:
        try:
            client = _open_client()
        except Exception as e:  # noqa: BLE001
            errors.append(f"open_client: {e}")
            return {"minted": 0, "skipped": 0, "errors": errors,
                    "rate_limited_until": None, "dry_run": dry_run,
                    "pending": len(pending)}

    try:
        for line in list(pending):
            # Re-read in case prior iteration mutated status
            if line.get("status") != "pending":
                skipped += 1
                continue
            ctx = line["context_id"]
            uname = line["bot_username"]

            if dry_run:
                log.info("dry_run: would mint %s (context_id=%s)", uname, ctx)
                print(f"[dry-run] /newbot → '{line['display_name']}' → {uname}")
                continue

            # Retry inline on rate-limit; cap cumulative wait.
            while True:
                try:
                    status, token, reason = _mint_one(client, line)
                except TimeoutError as e:
                    errors.append(f"{uname}: reply-timeout: {e}")
                    items = _update_queue_line(
                        items, ctx,
                        {"status": "failed", "reason": f"timeout: {e}"},
                        path,
                    )
                    break
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{uname}: {e}")
                    items = _update_queue_line(
                        items, ctx,
                        {"status": "failed", "reason": str(e)[:200]},
                        path,
                    )
                    log.exception("mint failed unexpectedly for %s", uname)
                    break

                if status == "minted":
                    try:
                        _insert_context_bot(line, token)
                    except Exception as e:  # noqa: BLE001
                        errors.append(f"{uname}: supabase-insert: {e}")
                        items = _update_queue_line(
                            items, ctx,
                            {"status": "failed", "token": token,
                             "reason": f"supabase-insert: {str(e)[:200]}"},
                            path,
                        )
                        log.exception("supabase insert failed for %s", uname)
                        break
                    items = _update_queue_line(
                        items, ctx,
                        {"status": "minted", "token": token,
                         "minted_at": datetime.now(AEST).isoformat(),
                         "reason": None},
                        path,
                    )
                    minted += 1
                    log.info("minted %s (context_id=%s)", uname, ctx)
                    time.sleep(INTER_MINT_SLEEP)  # courtesy gap to dodge fresh rate-limit
                    break

                if status.startswith("rate_limited:"):
                    secs = int(status.split(":", 1)[1])
                    # Cap so we never exceed the budget. Pad +5s for safety.
                    if total_wait + secs + 5 > max_wait_seconds:
                        rate_limited_until = (
                            datetime.now(AEST) + timedelta(seconds=secs)
                        ).isoformat()
                        _write_state(
                            {"rate_limited_until": rate_limited_until,
                             "reason": reason,
                             "last_attempted_username": uname},
                        )
                        log.warning(
                            "rate-limit %ss exceeds %ss budget; returning early "
                            "(LaunchAgent will resume).", secs, max_wait_seconds,
                        )
                        # Don't mark this line failed — keep it pending for the
                        # next run.
                        return {"minted": minted, "skipped": skipped,
                                "errors": errors,
                                "rate_limited_until": rate_limited_until,
                                "dry_run": dry_run,
                                "pending": len([i for i in items if i.get("status") == "pending"])}
                    log.warning(
                        "rate-limited for %ss on %s; sleeping then retrying",
                        secs, uname,
                    )
                    time.sleep(secs + 5)
                    total_wait += secs + 5
                    continue  # retry the same line

                if status == "username_taken":
                    items = _update_queue_line(
                        items, ctx,
                        {"status": "failed",
                         "reason": f"username_taken: {reason}"},
                        path,
                    )
                    errors.append(f"{uname}: username taken")
                    log.warning("username taken for %s", uname)
                    break

                if status == "invalid":
                    items = _update_queue_line(
                        items, ctx,
                        {"status": "failed",
                         "reason": f"invalid: {reason}"},
                        path,
                    )
                    errors.append(f"{uname}: invalid: {reason}")
                    break

                # "error:unparsed" or anything else
                items = _update_queue_line(
                    items, ctx,
                    {"status": "failed",
                     "reason": f"{status}: {reason}"},
                    path,
                )
                errors.append(f"{uname}: {status}: {reason}")
                break
    finally:
        if client is not None:
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    return {
        "minted": minted,
        "skipped": skipped,
        "errors": errors,
        "rate_limited_until": rate_limited_until,
        "dry_run": dry_run,
        "pending": len([i for i in items if i.get("status") == "pending"]),
    }


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    import sys
    dry = "--dry-run" in sys.argv
    print(json.dumps(mint_queue(dry_run=dry), indent=2, default=str))
