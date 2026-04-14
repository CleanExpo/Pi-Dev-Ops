"""Webhook routes: GitHub, Linear, morning-intel, Telegram (RA-937)."""
import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import require_rate_limit
from ..sessions import create_session
from ..supabase_log import mark_alert_acked
from ..webhook import (
    verify_github_signature,
    verify_linear_signature,
    parse_github_event,
    parse_linear_event,
    linear_issue_to_brief,
)
from .. import config
from .sessions import _find_active_session_for_repo

log = logging.getLogger("pi-ceo.main")

router = APIRouter()


def _telegram_send(token: str, chat_id: int | str, text: str) -> None:
    """Fire-and-forget helper — sends a message via Telegram Bot API."""
    import urllib.request as _ur
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req = _ur.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with _ur.urlopen(req, timeout=8):
            pass
    except Exception as exc:
        log.warning("Telegram reply failed: %s", exc)


@router.post("/api/webhook", dependencies=[Depends(require_rate_limit)])
async def webhook(request: Request):
    raw_body = await request.body()
    gh_event = request.headers.get("x-github-event", "")
    gh_sig = request.headers.get("x-hub-signature-256", "")
    linear_sig = request.headers.get("linear-signature", "")

    if gh_event and gh_sig:
        # GitHub webhook
        if not config.WEBHOOK_SECRET:
            raise HTTPException(500, "Webhook secret not configured")
        if not verify_github_signature(raw_body, gh_sig, config.WEBHOOK_SECRET):
            raise HTTPException(401, "Invalid signature")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid JSON")
        event = parse_github_event(gh_event, payload)
        if not event:
            return {"skipped": True, "reason": f"Unsupported event: {gh_event}"}
        repo_url = event["repo_url"]
        existing_id = _find_active_session_for_repo(repo_url)
        if existing_id:
            log.info("Skipping duplicate webhook for %s — session %s already active", repo_url, existing_id)
            return {"skipped": True, "reason": f"session {existing_id} already active", "session_id": existing_id}
        brief = f"Triggered by GitHub {event['event']} on {event.get('ref', 'unknown')}. Analyze changes, run tests if present, commit fixes."
        try:
            session = await create_session(repo_url, brief, config.EVALUATOR_MODEL)
        except RuntimeError as e:
            raise HTTPException(429, str(e))
        return {"triggered": True, "session_id": session.id, "repo": repo_url, "event": event["event"]}

    elif linear_sig:
        # Linear webhook
        if not config.LINEAR_WEBHOOK_SECRET:
            raise HTTPException(500, "Linear webhook secret not configured")
        if not verify_linear_signature(raw_body, linear_sig, config.LINEAR_WEBHOOK_SECRET):
            raise HTTPException(401, "Invalid signature")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid JSON")
        event = parse_linear_event(payload)
        if not event:
            return {"skipped": True, "reason": "Not an issue-started event"}
        if not event.get("repo_url"):
            return {"skipped": True, "reason": "No repo URL found in issue (add repo:<url> label)"}
        repo_url = event["repo_url"]
        existing_id = _find_active_session_for_repo(repo_url)
        if existing_id:
            log.info("Skipping duplicate webhook for %s — session %s already active", repo_url, existing_id)
            return {"skipped": True, "reason": f"session {existing_id} already active", "session_id": existing_id}
        brief = linear_issue_to_brief(event)
        linear_issue_id = event.get("issue_id") or None
        try:
            session = await create_session(
                repo_url, brief, config.EVALUATOR_MODEL,
                linear_issue_id=linear_issue_id,
                autonomy_triggered=True,  # RA-888: webhook sessions are autonomous
            )
        except RuntimeError as e:
            raise HTTPException(429, str(e))
        return {
            "triggered": True,
            "session_id": session.id,
            "source": "linear",
            "event": event.get("event", "issue_started"),
            "title": event["title"],
            "linear_issue_id": linear_issue_id,
        }

    else:
        raise HTTPException(400, "Missing webhook signature header (x-hub-signature-256 or Linear-Signature)")


# ── RA-845: Morning AI platform intelligence webhook ──────────────────────────

@router.post("/api/webhook/morning-intel", dependencies=[Depends(require_rate_limit)])
async def morning_intel_webhook(request: Request):
    """
    RA-845 — Receive daily AI platform intelligence from n8n (11:45 AM AEST).

    Payload:
      {
        "date": "2026-04-14",           # optional, defaults to today UTC
        "anthropic": "...",             # Anthropic updates summary
        "openai": "...",                # OpenAI updates summary
        "xai": "...",                   # xAI/Grok updates summary
        "flags": ["🔴 CRITICAL: ...", "🟢 ADOPT: ..."]
      }

    Writes to .harness/morning-intel/YYYY-MM-DD.json (atomic write).
    Board meeting build_board_system_prompt() reads it at run time.
    Protected by X-Pi-CEO-Secret header == TAO_WEBHOOK_SECRET.
    """
    import hmac as _hmac
    from datetime import datetime, timezone

    secret_header = request.headers.get("x-pi-ceo-secret", "")
    if config.WEBHOOK_SECRET:
        if not secret_header:
            raise HTTPException(401, "X-Pi-CEO-Secret header required")
        if not _hmac.compare_digest(secret_header, config.WEBHOOK_SECRET):
            raise HTTPException(401, "Invalid secret")

    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")

    date_str = payload.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    intel_dir = Path(config.DATA_DIR).parent.parent / ".harness" / "morning-intel"
    intel_dir.mkdir(parents=True, exist_ok=True)

    intel_file = intel_dir / f"{date_str}.json"
    tmp = intel_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, intel_file)

    flags: list = payload.get("flags") or []
    critical_count = sum(1 for f in flags if "🔴" in str(f) or "CRITICAL" in str(f).upper())
    log.info(
        "Morning intel stored: date=%s flags=%d critical=%d path=%s",
        date_str, len(flags), critical_count, intel_file,
    )

    return {"ok": True, "date": date_str, "flags": len(flags), "critical": critical_count}


# ── RA-657: Telegram /ack_alert webhook ───────────────────────────────────────

@router.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    RA-657 — Receive Telegram bot updates.
    Handles /ack_alert <key> to silence the escalation watchdog.
    Secured via X-Telegram-Bot-Api-Secret-Token (set when registering webhook).
    """
    token = config.TELEGRAM_BOT_TOKEN
    expected_secret = config.TELEGRAM_WEBHOOK_SECRET
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if expected_secret and secret != expected_secret:
        raise HTTPException(401, "Invalid Telegram webhook secret")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    message = data.get("message", {})
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")

    if text.startswith("/ack_alert"):
        parts = text.split(None, 1)
        alert_key = parts[1].strip() if len(parts) > 1 else ""
        if not alert_key:
            if token and chat_id:
                _telegram_send(token, chat_id, "⚠️ Usage: `/ack_alert <alert_key>`")
            return {"ok": True}
        try:
            mark_alert_acked(alert_key)
            log.info("Alert acked via Telegram: key=%s chat=%s", alert_key, chat_id)
        except Exception as exc:
            log.error("mark_alert_acked failed: %s", exc)
            if token and chat_id:
                _telegram_send(token, chat_id, f"❌ Failed to ack `{alert_key}`: {exc}")
            return {"ok": True}
        if token and chat_id:
            _telegram_send(token, chat_id, f"✅ Alert `{alert_key}` acknowledged — re-paging stopped.")

    return {"ok": True}
