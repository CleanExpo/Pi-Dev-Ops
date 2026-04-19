"""Phone companion routes (RA-1457 S-slice).

Two surfaces the user controls from their phone:

  1. Authority gates — Claude Code's PreToolUse hook POSTs a gate request for
     any destructive tool call. Backend pushes a Telegram card with
     [Approve] / [Deny] buttons, returns a gate_id. Mac hook polls
     /status until terminal or timeout.

  2. "Now Working" live card — one pinned message per session that edits
     in place with the current project/branch/last-tool/last-file.

Endpoints (all gated by TAO_PASSWORD via require_auth mirror):

  POST /api/phone/gate                  create gate + push card
  GET  /api/phone/gate/{gid}/status     poll (pending|approved|denied|expired)
  POST /api/phone/gate/{gid}/resolve    bot-internal, called from callback
  POST /api/phone/progress              edit-in-place progress card
  POST /api/phone/session               start/stop session card

State is in-memory only — on Railway restart, pending gates expire and
progress cards are re-created on the next ping. That's the correct failure
mode for an S-slice.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import require_auth

log = logging.getLogger("pi-ceo.phone")
router = APIRouter(prefix="/api/phone", tags=["phone"])


# ── Config ──────────────────────────────────────────────────────────────────
_TG_API = "https://api.telegram.org"


def _bot_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise HTTPException(502, "TELEGRAM_BOT_TOKEN not configured on backend")
    return token


def _chat_id() -> str:
    """Resolve target chat ID from PHONE_COMPANION_CHAT_ID or first ALLOWED_USERS."""
    explicit = os.environ.get("PHONE_COMPANION_CHAT_ID", "").strip()
    if explicit:
        return explicit
    allowed = os.environ.get("ALLOWED_USERS", "").strip()
    if not allowed:
        raise HTTPException(
            502,
            "PHONE_COMPANION_CHAT_ID or ALLOWED_USERS must be set on backend",
        )
    first = allowed.split(",")[0].strip()
    if not first:
        raise HTTPException(502, "ALLOWED_USERS is empty")
    return first


# ── In-memory state ─────────────────────────────────────────────────────────
# Gate lifecycle: pending -> approved | denied | expired
_gates: dict[str, dict[str, Any]] = {}
_gate_dedupe: dict[str, tuple[str, float]] = {}  # hash -> (gate_id, expires_at)
_sessions: dict[str, dict[str, Any]] = {}  # session_id -> {message_id, last_payload_hash, last_sent_at}
_lock = threading.Lock()

_GATE_TTL_DEFAULT = 60.0
_DEDUPE_WINDOW = 5.0
_PROGRESS_THROTTLE = 2.0  # minimum seconds between edits of same card


# ── Telegram HTTP helpers ───────────────────────────────────────────────────
def _tg_call(method: str, payload: dict) -> dict:
    """POST to Telegram API. Raises HTTPException on transport or API error."""
    url = f"{_TG_API}/bot{_bot_token()}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode(errors="ignore") if exc.fp else ""
        raise HTTPException(502, f"Telegram {method} HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(502, f"Telegram {method} transport error: {exc}") from exc
    if not body.get("ok"):
        raise HTTPException(502, f"Telegram {method} returned not-ok: {body}")
    return body.get("result", {})


def _gate_card_html(
    tool_name: str, tool_input_summary: str, reason: str, state: str, resolver: str | None = None
) -> str:
    """Notion-style HTML card under 2 kB."""
    # Redact: never include file contents. tool_input_summary is caller's job
    # to truncate; we just escape.
    def esc(s: str) -> str:
        return (
            str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:400]
        )

    state_line = {
        "pending": "⏳ <i>Waiting for your tap</i>",
        "approved": f"✅ <b>Approved</b>{(' by ' + resolver) if resolver else ''}",
        "denied": f"🚫 <b>Denied</b>{(' by ' + resolver) if resolver else ''}",
        "expired": "⌛ <b>Expired</b> — hook defaulted to Deny",
    }.get(state, state)

    lines = [
        "🛡️ <b>Authority Prompt</b>",
        "",
        f"<b>Tool:</b> <code>{esc(tool_name)}</code>",
        f"<b>Why:</b> {esc(reason)}",
        "",
        f"<pre>{esc(tool_input_summary)}</pre>",
        "",
        state_line,
    ]
    return "\n".join(lines)


def _progress_card_html(
    project: str,
    branch: str,
    current_task: str,
    last_tool: str,
    last_file: str,
    elapsed_s: int,
    ended: bool = False,
    summary: str | None = None,
) -> str:
    def esc(s: str) -> str:
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:300]

    mm, ss = divmod(max(int(elapsed_s), 0), 60)
    elapsed = f"{mm}m {ss:02d}s"

    if ended:
        return "\n".join(
            [
                "✅ <b>Session ended</b>",
                "",
                f"<b>Project:</b> <code>{esc(project)}</code>",
                f"<b>Branch:</b> <code>{esc(branch)}</code>",
                f"<b>Ran for:</b> {elapsed}",
                "",
                f"<i>{esc(summary or 'done')}</i>",
            ]
        )

    return "\n".join(
        [
            "🟢 <b>Now Working</b>",
            "",
            f"<b>Project:</b> <code>{esc(project)}</code>",
            f"<b>Branch:</b> <code>{esc(branch)}</code>",
            f"<b>Task:</b> {esc(current_task)}",
            f"<b>Last tool:</b> <code>{esc(last_tool)}</code>",
            f"<b>Last file:</b> <code>{esc(last_file)}</code>",
            "",
            f"<i>elapsed {elapsed} · updated just now</i>",
        ]
    )


# ── Gate model + endpoints ──────────────────────────────────────────────────
class GateRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    tool_name: str = Field(..., min_length=1, max_length=128)
    tool_input_summary: str = Field("", max_length=500)
    reason: str = Field("", max_length=300)
    timeout_s: float | None = Field(None, ge=5, le=600)


def _gate_dedupe_hash(session_id: str, tool_name: str, tool_input_summary: str) -> str:
    h = hashlib.sha256()
    h.update(session_id.encode())
    h.update(b"\0")
    h.update(tool_name.encode())
    h.update(b"\0")
    h.update(tool_input_summary.encode())
    return h.hexdigest()


def _sweep_expired() -> None:
    """Mark pending gates past their expiry as expired. Prune dedupe cache."""
    now = time.time()
    with _lock:
        for gid, g in list(_gates.items()):
            if g["status"] == "pending" and g["expires_at"] <= now:
                g["status"] = "expired"
                # Best-effort card update — don't raise if Telegram's unreachable
                mid = g.get("message_id")
                if mid:
                    try:
                        _tg_call(
                            "editMessageText",
                            {
                                "chat_id": g["chat_id"],
                                "message_id": mid,
                                "text": _gate_card_html(
                                    g["tool_name"],
                                    g["tool_input_summary"],
                                    g["reason"],
                                    "expired",
                                ),
                                "parse_mode": "HTML",
                                "reply_markup": {"inline_keyboard": []},
                            },
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.warning("gate expire edit failed gid=%s: %s", gid, exc)
        stale = [k for k, (_gid, exp) in _gate_dedupe.items() if exp <= now]
        for k in stale:
            del _gate_dedupe[k]


@router.post("/gate", dependencies=[Depends(require_auth)])
async def create_gate(body: GateRequest) -> dict:
    _sweep_expired()
    timeout_s = float(body.timeout_s or _GATE_TTL_DEFAULT)

    dhash = _gate_dedupe_hash(body.session_id, body.tool_name, body.tool_input_summary)
    now = time.time()
    with _lock:
        existing = _gate_dedupe.get(dhash)
        if existing and existing[1] > now:
            gid = existing[0]
            if gid in _gates:
                return {"gate_id": gid, "deduped": True}

        gate_id = uuid.uuid4().hex[:16]
        _gates[gate_id] = {
            "gate_id": gate_id,
            "session_id": body.session_id,
            "tool_name": body.tool_name,
            "tool_input_summary": body.tool_input_summary,
            "reason": body.reason,
            "status": "pending",
            "created_at": now,
            "expires_at": now + timeout_s,
            "resolved_at": None,
            "resolved_by": None,
            "chat_id": _chat_id(),
            "message_id": None,
        }
        _gate_dedupe[dhash] = (gate_id, now + _DEDUPE_WINDOW)

    # Push card (outside lock — Telegram call is slow)
    result = _tg_call(
        "sendMessage",
        {
            "chat_id": _gates[gate_id]["chat_id"],
            "text": _gate_card_html(
                body.tool_name, body.tool_input_summary, body.reason, "pending"
            ),
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✓ Approve", "callback_data": f"approve:{gate_id}"},
                        {"text": "✗ Deny", "callback_data": f"deny:{gate_id}"},
                    ]
                ]
            },
        },
    )
    with _lock:
        _gates[gate_id]["message_id"] = result.get("message_id")
    return {"gate_id": gate_id, "message_id": result.get("message_id")}


@router.get("/gate/{gate_id}/status", dependencies=[Depends(require_auth)])
async def gate_status(gate_id: str) -> dict:
    _sweep_expired()
    with _lock:
        g = _gates.get(gate_id)
        if not g:
            raise HTTPException(404, "gate not found")
        return {
            "status": g["status"],
            "reason": g.get("resolved_by"),
        }


class ResolveBody(BaseModel):
    status: str = Field(..., pattern="^(approved|denied)$")
    by_user_id: str | int | None = None


@router.post("/gate/{gate_id}/resolve", dependencies=[Depends(require_auth)])
async def resolve_gate(gate_id: str, body: ResolveBody) -> dict:
    now = time.time()
    with _lock:
        g = _gates.get(gate_id)
        if not g:
            raise HTTPException(404, "gate not found")
        if g["status"] != "pending":
            return {"status": g["status"], "already": True}
        g["status"] = body.status
        g["resolved_at"] = now
        g["resolved_by"] = str(body.by_user_id) if body.by_user_id is not None else None
        mid = g.get("message_id")
        chat_id = g["chat_id"]
        card_args = (g["tool_name"], g["tool_input_summary"], g["reason"], body.status, g["resolved_by"])

    if mid:
        try:
            _tg_call(
                "editMessageText",
                {
                    "chat_id": chat_id,
                    "message_id": mid,
                    "text": _gate_card_html(*card_args),
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": []},
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("gate resolve edit failed gid=%s: %s", gate_id, exc)
    return {"status": body.status}


# ── Progress model + endpoints ──────────────────────────────────────────────
class ProgressBody(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    project: str = Field("", max_length=120)
    branch: str = Field("", max_length=120)
    current_task: str = Field("", max_length=200)
    last_tool: str = Field("", max_length=80)
    last_file: str = Field("", max_length=200)
    elapsed_s: int = Field(0, ge=0, le=60 * 60 * 24)


def _progress_payload_hash(body: ProgressBody) -> str:
    h = hashlib.sha256()
    for v in (body.project, body.branch, body.current_task, body.last_tool, body.last_file):
        h.update(str(v).encode())
        h.update(b"\0")
    # Elapsed changes constantly — quantise to 15 s so identical snapshots dedupe
    h.update(str(int(body.elapsed_s) // 15).encode())
    return h.hexdigest()


@router.post("/progress", dependencies=[Depends(require_auth)])
async def progress(body: ProgressBody) -> dict:
    payload_hash = _progress_payload_hash(body)
    chat_id = _chat_id()
    now = time.time()

    with _lock:
        sess = _sessions.get(body.session_id)
        if sess:
            if sess.get("last_payload_hash") == payload_hash:
                return {"status": "unchanged", "message_id": sess.get("message_id")}
            if now - sess.get("last_sent_at", 0) < _PROGRESS_THROTTLE:
                return {"status": "throttled", "message_id": sess.get("message_id")}

    text = _progress_card_html(
        body.project,
        body.branch,
        body.current_task,
        body.last_tool,
        body.last_file,
        body.elapsed_s,
    )

    if sess and sess.get("message_id"):
        try:
            _tg_call(
                "editMessageText",
                {
                    "chat_id": chat_id,
                    "message_id": sess["message_id"],
                    "text": text,
                    "parse_mode": "HTML",
                },
            )
            with _lock:
                sess["last_payload_hash"] = payload_hash
                sess["last_sent_at"] = now
            return {"status": "edited", "message_id": sess["message_id"]}
        except HTTPException as exc:
            # "message is not modified" — harmless. Any other 400 means the card
            # was deleted; fall through to re-send.
            log.info(
                "progress edit failed session=%s: %s — re-creating card",
                body.session_id,
                exc.detail,
            )

    # Create + pin
    result = _tg_call(
        "sendMessage",
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
    )
    mid = result.get("message_id")
    try:
        _tg_call(
            "pinChatMessage",
            {"chat_id": chat_id, "message_id": mid, "disable_notification": True},
        )
    except Exception as exc:  # noqa: BLE001
        # Private chats often reject pin for bots — that's fine, the message
        # still exists and will be edited in place. Don't fail the request.
        log.info("pinChatMessage failed (non-fatal): %s", exc)

    with _lock:
        _sessions[body.session_id] = {
            "message_id": mid,
            "last_payload_hash": payload_hash,
            "last_sent_at": now,
            "started_at": now if not sess else sess.get("started_at", now),
        }
    return {"status": "created", "message_id": mid}


class SessionBody(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    action: str = Field(..., pattern="^(start|stop)$")
    project: str = Field("", max_length=120)
    branch: str = Field("", max_length=120)
    summary: str = Field("", max_length=300)


@router.post("/session", dependencies=[Depends(require_auth)])
async def session_action(body: SessionBody) -> dict:
    chat_id = _chat_id()
    now = time.time()

    if body.action == "start":
        text = _progress_card_html(
            body.project, body.branch, "starting…", "-", "-", 0
        )
        result = _tg_call(
            "sendMessage",
            {"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )
        mid = result.get("message_id")
        try:
            _tg_call(
                "pinChatMessage",
                {"chat_id": chat_id, "message_id": mid, "disable_notification": True},
            )
        except Exception as exc:  # noqa: BLE001
            log.info("pinChatMessage failed (non-fatal): %s", exc)
        with _lock:
            _sessions[body.session_id] = {
                "message_id": mid,
                "last_payload_hash": None,
                "last_sent_at": now,
                "started_at": now,
            }
        return {"status": "started", "message_id": mid}

    # stop
    with _lock:
        sess = _sessions.pop(body.session_id, None)
    if not sess or not sess.get("message_id"):
        return {"status": "no-session"}
    elapsed = int(now - sess.get("started_at", now))
    text = _progress_card_html(
        body.project or "-",
        body.branch or "-",
        "",
        "",
        "",
        elapsed,
        ended=True,
        summary=body.summary or "done",
    )
    try:
        _tg_call(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": sess["message_id"],
                "text": text,
                "parse_mode": "HTML",
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("session stop edit failed: %s", exc)
    try:
        _tg_call(
            "unpinChatMessage",
            {"chat_id": chat_id, "message_id": sess["message_id"]},
        )
    except Exception as exc:  # noqa: BLE001
        log.info("unpin failed (non-fatal): %s", exc)
    return {"status": "stopped", "message_id": sess["message_id"]}
