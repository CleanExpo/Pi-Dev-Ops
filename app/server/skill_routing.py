"""Skill context for a brief, chosen by src.tao.skill_router behind SKILL_ROUTER=off|shadow|on.

off     today's intent table only.
shadow  (default) the router decides and logs what it would load, on a background thread so the
        brief never waits; today's context is still used.
on      the router's pick is the context: one skill body under a token budget, or nothing.

Live Jev only with TYPESAFE_API_KEY in this process, a 3 s timeout and a daily dollar cap
(SKILL_ROUTER_DAILY_CAP_USD, default 1.0) reserved in a ledger before each call. Any Jev
problem is a logged lexical fallback, and any router error falls back to today's context.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Callable
from urllib import request

log = logging.getLogger(__name__)
_CATALOGUE: list | None = None
LEDGER = Path(os.environ.get("SKILL_ROUTER_LEDGER", ".harness/skill-router-ledger.sqlite"))


class CapReached(RuntimeError):
    """The daily Jev spend cap is used up; route without Jev."""


def mode() -> str:
    value = os.environ.get("SKILL_ROUTER", "shadow").strip().lower()
    return value if value in ("off", "shadow", "on") else "shadow"


def live_jev() -> Callable[[dict], dict] | None:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        return None
    from scripts.mission_control_jev_shadow import evaluate, finish_call, reserve_call

    cap = float(os.environ.get("SKILL_ROUTER_DAILY_CAP_USD", "1.0"))

    def call(payload: dict) -> dict:
        call_id = reserve_call(LEDGER, 20_000, cap)
        if call_id is None:
            raise CapReached(f"daily Jev cap ${cap} reached")
        try:
            result = evaluate(payload, key, opener=lambda req, timeout: request.urlopen(req, timeout=3))
        except Exception:
            finish_call(LEDGER, call_id, "error")
            raise
        finish_call(LEDGER, call_id, "answered", result.get("usage", {}).get("input_tokens"))
        return result

    return call


def _decide(raw_brief: str):
    global _CATALOGUE
    from src.tao import skill_router as sr
    from src.tao.skills import load_all_skills

    skills = load_all_skills()
    if _CATALOGUE is None:
        _CATALOGUE = sr.build_catalogue(skills)
    return sr.route(raw_brief, catalogue=_CATALOGUE, skills=skills, jev=live_jev())


def legacy_context(intent: str, max_chars: int = 4000) -> str:
    """Today's path (moved from brief.py): the intent table's skills, 800 chars each, 4000 in all."""
    try:
        from src.tao.skills import skills_for_intent
        skills = skills_for_intent(intent)
        if not skills:
            return ""
        parts = []
        total = 0
        for s in skills:
            chunk = f"### Skill: {s['name']}\n{s['body'][:800]}\n"
            if total + len(chunk) > max_chars:
                break
            parts.append(chunk)
            total += len(chunk)
        if parts:
            return "--- RELEVANT SKILLS ---\n" + "\n".join(parts) + "--- END SKILLS ---\n\n"
    except Exception:
        pass
    return ""


def _decide_and_log(raw_brief: str, intent: str, current: str, today: str):
    try:
        d = _decide(raw_brief)
    except Exception as exc:
        log.warning("skill_router error, using intent table: %s", type(exc).__name__)
        return None
    log.info("skill_router %s", json.dumps({
        "mode": current, "intent": intent, "picked": d.skills, "source": d.source, "reason": d.reason,
        "confidence": d.confidence, "tokens": d.tokens, "legacy_tokens": len(today) // 4,
        "request_sha": hashlib.sha256(raw_brief.encode()).hexdigest()[:12],
    }))
    return d


# Shadow only observes, so it must never delay a brief: it runs on one background thread.
# While one observation is in flight, later briefs skip theirs rather than queue up Jev calls.
_SHADOW_BUSY = threading.Lock()
_shadow_thread: threading.Thread | None = None


def _shadow(raw_brief: str, intent: str, today: str) -> None:
    global _shadow_thread
    if not _SHADOW_BUSY.acquire(blocking=False):
        log.info("skill_router %s", json.dumps({"mode": "shadow", "source": "shadow_skipped_busy"}))
        return

    def run():
        try:
            _decide_and_log(raw_brief, intent, "shadow", today)
        finally:
            _SHADOW_BUSY.release()

    _shadow_thread = threading.Thread(target=run, name="skill-router-shadow", daemon=True)
    _shadow_thread.start()


def wait_for_shadow(timeout: float = 10.0) -> None:
    """For tests: block until the in-flight shadow observation has logged."""
    if _shadow_thread is not None:
        _shadow_thread.join(timeout)


def skill_context(raw_brief: str, intent: str) -> str:
    today = legacy_context(intent)
    current = mode()
    if current == "off":
        return today
    if current == "shadow":
        _shadow(raw_brief, intent, today)
        return today
    d = _decide_and_log(raw_brief, intent, current, today)
    if d is None:
        return today
    if not d.skills:
        return ""
    return f"--- RELEVANT SKILL ---\n### Skill: {d.skills[0]}\n{d.bodies[0]}\n--- END SKILL ---\n\n"
