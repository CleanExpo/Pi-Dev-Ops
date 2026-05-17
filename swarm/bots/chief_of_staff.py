"""
swarm/bots/chief_of_staff.py — RA-1839: Chief of Staff swarm bot.

Polls Telegram for non-/ack messages, classifies via intent_router,
fans out to specialist roles. Drafts go through draft_review HITL gate.
Wired into orchestrator.run() after scribe.run_cycle() (ed60618).

HITL gaps closed (30d3ec5):
  Gap 1: _poll_telegram POSTs allowed_updates=["message","message_reaction"]
          and calls draft_review.mark_reaction() on 👍/❌/⏳ reactions.
  Gap 2: fix_project handler in _route() — Wave-3 draft for health monitor dispatch.
  Gap 3: classify_llm() in intent_router — Ollama Layer 2 fallback when regex unknown.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from .. import config
from ..telegram_alerts import send

log = logging.getLogger("swarm.cos")


def _poll_telegram(state_offset: int) -> tuple[list[dict], int]:
    """Pull Telegram updates after `state_offset`. Returns (messages, new_offset).

    /panic and /resume are processed inline here BEFORE the kill-switch
    gate so they remain reachable even when the swarm is halted.
    """
    from .. import kill_switch as _kill_switch  # local import to avoid cycles

    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return [], state_offset
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    body = json.dumps({
        "offset": state_offset + 1,
        "timeout": 0,
        "limit": 20,
        "allowed_updates": ["message", "message_reaction"],
    }).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        log.debug("CoS Telegram poll error: %s", exc)
        return [], state_offset

    messages: list[dict] = []
    new_offset = state_offset
    for u in data.get("result", []):
        uid = u.get("update_id", 0)
        if uid > new_offset:
            new_offset = uid

        # ── message_reaction — HITL draft approval via 👍/❌/⏳ ─────────────────
        reaction = u.get("message_reaction")
        if reaction:
            msg_id = str(reaction.get("message_id", ""))
            chat_id_r = str((reaction.get("chat") or {}).get("id", ""))
            if chat_id_r == str(chat_id) and msg_id:
                from .. import draft_review as _dr  # noqa: PLC0415
                for r in reaction.get("new_reaction", []):
                    emoji_str = r.get("emoji", "")
                    if emoji_str in ("👍", "❌", "⏳"):
                        _dr.mark_reaction(review_message_id=msg_id, emoji=emoji_str)
                        log.info("CoS: reaction %s on msg %s", emoji_str, msg_id)
            continue

        msg = u.get("message")
        if not msg:
            continue
        text = (msg.get("text") or "").strip()
        msg_chat = str(msg.get("chat", {}).get("id", ""))

        # Only process messages from the configured chat_id
        if msg_chat != str(chat_id):
            continue

        # ── /panic, /resume, /resume-confirm — kill-switch handlers ─────────
        # Run BEFORE the /ack-skip so they fire even on a halted swarm.
        lower = text.lower()
        if lower.startswith("/panic"):
            reason = text[len("/panic"):].strip() or "operator-initiated"
            _kill_switch.trigger("telegram_panic", reason=reason)
            continue
        if lower.startswith("/resume-confirm"):
            reason = text[len("/resume-confirm"):].strip() or "manual recovery"
            _kill_switch.resume("telegram_resume_confirm",
                                reason=reason, confirmed=True)
            continue
        if lower.startswith("/resume"):
            reason = text[len("/resume"):].strip()
            _kill_switch.resume("telegram_resume", reason=reason)
            continue

        # Skip /ack and /turbopack — those go to the orchestrator's listener
        if lower.startswith(("/ack", "/turbopack")):
            continue

        messages.append(msg)
    return messages, new_offset


def _route(intent_payload: dict[str, Any]) -> dict[str, Any]:
    """Route a classified intent to the right specialist. Returns action dict."""
    from .. import draft_review

    intent = intent_payload["intent"]
    fields = intent_payload.get("fields", {})

    if intent == "margot":
        # Wave 5.1 — Margot personal-assistant turn. Direct send (no
        # draft_review HITL — Margot talking to the founder, not
        # outbound to others). Async-runs the full margot turn pipeline.
        try:
            from . import margot as margot_bot_wrapper  # noqa: PLC0415
            return margot_bot_wrapper.handle_telegram_intent(intent_payload)
        except Exception as exc:  # noqa: BLE001
            return {"action": "failed", "reason": f"margot route failed: {exc}"}

    if intent == "research":
        # Wave 2: dispatch to Margot via mcp__margot__deep_research / _max
        # In shadow mode, just log and surface a draft summarising what would happen.
        draft = (
            f"📚 RESEARCH intent\n"
            f"Topic: {fields.get('topic', '?')}\n"
            f"Time-budget: {fields.get('time_budget', '?')}\n"
            f"Use-corpus: {fields.get('use_corpus', '?')}\n"
            f"\n(Wave 2: would dispatch to Margot deep_research / _max here.)"
        )
        return draft_review.post_draft(
            draft_text=draft,
            destination_chat_id=str(intent_payload.get("originating_chat_id") or ""),
            drafted_by_role="CoS",
            originating_intent_id=intent_payload.get("originating_message_id"),
        )

    if intent == "ticket":
        draft = (
            f"📝 TICKET intent\n"
            f"Team-hint: {fields.get('team_hint') or '(unset)'}\n"
            f"Title-hint: {fields.get('title_hint') or '(unset)'}\n"
            f"\n(Wave 2: would call mcp.linear.save_issue here.)"
        )
        return draft_review.post_draft(
            draft_text=draft,
            destination_chat_id=str(intent_payload.get("originating_chat_id") or ""),
            drafted_by_role="CoS",
            originating_intent_id=intent_payload.get("originating_message_id"),
        )

    if intent == "reply":
        # Reply intent needs research + drafting. In shadow mode, just queue.
        draft = (
            f"💬 REPLY intent — draft pending research/composition\n"
            f"Body hint: {fields.get('body_hint') or '(unset)'}"
        )
        return draft_review.post_draft(
            draft_text=draft,
            destination_chat_id=str(intent_payload.get("originating_chat_id") or ""),
            drafted_by_role="CoS",
            originating_intent_id=intent_payload.get("originating_message_id"),
        )

    if intent == "reminder":
        draft = (
            f"⏰ REMINDER intent\n"
            f"When: {fields.get('when') or '(unparsed)'}\n"
            f"What: {fields.get('what') or '(unset)'}\n"
            f"\n(Wave 2: would call calendar-watcher / cron-scheduler here.)"
        )
        return draft_review.post_draft(
            draft_text=draft,
            destination_chat_id=str(intent_payload.get("originating_chat_id") or ""),
            drafted_by_role="CoS",
            originating_intent_id=intent_payload.get("originating_message_id"),
        )

    if intent == "flow":
        draft = (
            f"🔀 FLOW intent — multi-step request detected\n"
            f"Raw text: {fields.get('raw_steps_text', '?')[:200]}\n"
            f"\n(Wave 2: would invoke flow_engine.execute_flow here.)"
        )
        return draft_review.post_draft(
            draft_text=draft,
            destination_chat_id=str(intent_payload.get("originating_chat_id") or ""),
            drafted_by_role="CoS",
            originating_intent_id=intent_payload.get("originating_message_id"),
        )

    if intent == "fix_project":
        project = fields.get("project_hint", "all")
        draft = (
            f"🔧 FIX_PROJECT intent\n"
            f"Target: {project}\n"
            f"Raw: {fields.get('raw_text', '?')[:200]}\n"
            f"\n(Wave 3: health monitor + fix orchestrator for '{project}')"
        )
        return draft_review.post_draft(
            draft_text=draft,
            destination_chat_id=str(intent_payload.get("originating_chat_id") or ""),
            drafted_by_role="CoS",
            originating_intent_id=intent_payload.get("originating_message_id"),
        )

    return {"draft_id": None, "status": "no_action",
            "reason": f"unknown intent (confidence={intent_payload.get('confidence')})"}


def run_cycle(unacked_count: int) -> dict[str, Any]:
    """One CoS cycle: poll Telegram, classify, route, return summary."""
    from .. import intent_router, draft_review

    if not config.SWARM_ENABLED:
        return {"skipped": "kill-switch off"}

    # Sweep expired drafts every cycle (cheap)
    expired = draft_review.expire_overdue()

    state_file = config.SWARM_LOG_DIR / "cos_offset.json"
    offset = 0
    if state_file.exists():
        try:
            offset = int(json.loads(state_file.read_text()).get("offset", 0))
        except Exception:
            pass

    messages, new_offset = _poll_telegram(offset)
    if new_offset != offset:
        # Atomic write — if the process crashes mid-write, the OLD offset
        # is preserved (vs. naive write_text which truncates on crash and
        # leaves the file empty, replaying the entire poll on next cycle).
        # Per [[board-deliberation-code-patterns-2026-05-15]] PR2.
        from .._atomic import atomic_write_json
        atomic_write_json(state_file, {"offset": new_offset}, indent=None)

    handled = 0
    for msg in messages:
        text = (msg.get("text") or "").strip()
        intent = intent_router.classify(
            text,
            chat_id=str(msg.get("chat", {}).get("id", "")),
            message_id=str(msg.get("message_id", "")),
        )
        # Layer 2 LLM fallback when regex can't classify
        if intent["intent"] == "unknown":
            intent = intent_router.classify_llm(text, intent)
        log.info("CoS classified intent=%s confidence=%.2f",
                intent["intent"], intent.get("confidence", 0))
        result = _route(intent)
        handled += 1
        if config.SHADOW_MODE:
            send(
                f"CoS shadow: intent={intent['intent']} → draft "
                f"{result.get('draft_id') or 'none'}",
                severity="info",
                bot_name="CoS",
            )

    return {
        "unacked": unacked_count,
        "messages_handled": handled,
        "drafts_expired": expired,
        "new_offset": new_offset,
    }


__all__ = ["run_cycle"]
