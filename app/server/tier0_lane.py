"""tier0_lane.py — UNI-2212: the Tier-0 "gathering" lane.

High-volume, low-stakes gathering work (web-research fan-out, source
summarisation, classification, dedup, intent routing, structured extraction,
light file triage) is routed here to take load OFF the Claude Max plans —
"workhorses GATHER, SOTA SHIPS" (blueprint §7 / tier0-model-routing-openrouter.md).

This module is a pure resolver + capacity tracker; it picks an ordered
fallback chain of (provider, model_id) lanes. Runtime chain-walk-on-failure
and live per-slug smoke-testing land in a follow-up slice.

Ordered lane policy (most-preferred first):
  1. Free OpenRouter slugs   — while the account's free pool has headroom.
  2. Paid OpenRouter spill   — DeepSeek (cheap JSON/tools) → Kimi (long-horizon).
  3. Local Ollama overflow   — unlimited, and the ONLY lane for confidential data.

Hard privacy gate (blueprint §7 Finding 6): free-tier + Kimi may train on
inputs, so confidential / client / proprietary data NEVER touches them — it
routes to the local lane only. Callers pass ``confidential=True`` for such work.

Capacity facts (live-verified 2026-06-30): OpenRouter governs capacity
PER-ACCOUNT globally — our two keys share ONE pool. Free cap is 1,000 RPD
(after a one-time $10 credit; 50/day without) and a 20 RPM burst ceiling.
We track both and drop the free slugs from the chain once either is hit.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("app.server.tier0_lane")

Lane = tuple[str, str]  # (provider, model_id)


# ── Lane defaults — all env-overridable (comma-separated for the chains) ─────

# Top-3 free slugs to wire first (tier0-model-routing-openrouter.md §model-selection).
# NEVER pin a single :free slug — free variants churn in/out; always a chain.
DEFAULT_TIER0_FREE_CHAIN = (
    "openai/gpt-oss-120b:free",                  # default gathering brain
    "qwen/qwen3-next-80b-a3b-instruct:free",     # 262K long-context extraction
    "openai/gpt-oss-20b:free",                   # fast classify/dedup/route
)

# Paid spill when the free pool is exhausted (founder-sanctioned credits):
# DeepSeek first (best cheap JSON+tools), Kimi for long-horizon tool chains.
DEFAULT_TIER0_PAID_SPILL = (
    "deepseek/deepseek-v3.2",
    "moonshotai/kimi-k2.6",
)

# Local overflow + the ONLY confidential lane (today = the existing Ollama tag).
DEFAULT_TIER0_LOCAL_MODEL = "gemma4:latest"

# Capacity ceilings — one global OpenRouter account pool (keys do NOT stack).
DEFAULT_TIER0_RPD_CAP = 1000
DEFAULT_TIER0_RPM_CAP = 20

_LEDGER_PATH = Path(
    os.environ.get("HERMES_ROOT", str(Path.home() / ".hermes"))
) / "openrouter-tier0-ledger.json"


# ── Env helpers ──────────────────────────────────────────────────────────────


def _env_chain(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    items = tuple(s.strip() for s in raw.split(",") if s.strip())
    return items or default


def _free_chain() -> tuple[str, ...]:
    return _env_chain("TAO_TIER0_FREE_CHAIN", DEFAULT_TIER0_FREE_CHAIN)


def _paid_spill() -> tuple[str, ...]:
    return _env_chain("TAO_TIER0_PAID_SPILL", DEFAULT_TIER0_PAID_SPILL)


def _local_model() -> str:
    return (os.environ.get("TAO_TIER0_LOCAL_MODEL") or DEFAULT_TIER0_LOCAL_MODEL).strip()


def _rpd_cap() -> int:
    try:
        return int(os.environ.get("TAO_TIER0_RPD_CAP") or DEFAULT_TIER0_RPD_CAP)
    except ValueError:
        return DEFAULT_TIER0_RPD_CAP


def _rpm_cap() -> int:
    try:
        return int(os.environ.get("TAO_TIER0_RPM_CAP") or DEFAULT_TIER0_RPM_CAP)
    except ValueError:
        return DEFAULT_TIER0_RPM_CAP


# ── Capacity ledger (RPD / RPM) — atomic, copies research_provider pattern ───


def _day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _minute_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _load_ledger() -> dict[str, Any]:
    if not _LEDGER_PATH.exists():
        return {"version": 1, "rpd": {}, "rpm": {}}
    try:
        data = json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("rpd", {})
            data.setdefault("rpm", {})
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"version": 1, "rpd": {}, "rpm": {}}


def _save_ledger(ledger: dict[str, Any]) -> None:
    try:
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _LEDGER_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(_LEDGER_PATH))
    except OSError as exc:
        log.warning("tier0_lane: could not persist capacity ledger: %s", exc)


def _prune(ledger: dict[str, Any]) -> None:
    """Keep only today's RPD bucket and the current-minute RPM bucket so the
    ledger file stays small (it is rewritten on every request)."""
    today, minute = _day_key(), _minute_key()
    ledger["rpd"] = {k: v for k, v in ledger.get("rpd", {}).items() if k == today}
    ledger["rpm"] = {k: v for k, v in ledger.get("rpm", {}).items() if k == minute}


def free_capacity_available() -> bool:
    """True while the global free pool has BOTH daily and per-minute headroom."""
    ledger = _load_ledger()
    rpd = int(ledger.get("rpd", {}).get(_day_key(), 0))
    rpm = int(ledger.get("rpm", {}).get(_minute_key(), 0))
    return rpd < _rpd_cap() and rpm < _rpm_cap()


def record_free_request() -> None:
    """Count one free-slug request against the RPD + RPM ledger. Fires an
    edge-triggered alert the first time either ceiling is reached."""
    ledger = _load_ledger()
    _prune(ledger)
    today, minute = _day_key(), _minute_key()
    ledger["rpd"][today] = int(ledger["rpd"].get(today, 0)) + 1
    ledger["rpm"][minute] = int(ledger["rpm"].get(minute, 0)) + 1
    _save_ledger(ledger)

    rpd, rpm = ledger["rpd"][today], ledger["rpm"][minute]
    if rpd >= _rpd_cap():
        _alert_exhausted("rpd", rpd, _rpd_cap())
    elif rpm >= _rpm_cap():
        _alert_exhausted("rpm", rpm, _rpm_cap())


def _alert_exhausted(kind: str, used: int, cap: int) -> None:
    """Edge-triggered Telegram alert — fires once per state change, not per
    cycle (reuses telegram_alerts dedup_key; fail-closed behind its env flag)."""
    try:
        from swarm import telegram_alerts  # noqa: PLC0415
        telegram_alerts.send(
            f"Tier-0 OpenRouter free pool exhausted ({kind.upper()} {used}/{cap}) "
            f"— spilling to paid/local lane.",
            severity="high",
            bot_name="Tier0",
            dedup_key=f"tier0_free_{kind}_exhausted",
        )
    except Exception as exc:  # noqa: BLE001 — alerting must never break routing
        log.debug("tier0_lane: exhaustion alert failed: %s", exc)


# ── Chain resolver (pure) ────────────────────────────────────────────────────


def resolve_tier0_chain(
    *, confidential: bool = False, free_available: bool | None = None,
) -> list[Lane]:
    """Ordered (provider, model_id) lanes to try, most-preferred first.

    Args:
        confidential: when True, the privacy gate forces LOCAL-ONLY — free
            slugs and Kimi may train on inputs, so client/proprietary data
            never reaches them.
        free_available: override the live capacity probe (mainly for tests).
            When None, ``free_capacity_available()`` decides whether the free
            slugs are included.

    Returns:
        A non-empty list ending in the local Ollama lane (always reachable as
        the final overflow). Confidential → ``[("ollama", local)]`` only.
    """
    local: Lane = ("ollama", _local_model())
    if confidential:
        return [local]

    if free_available is None:
        free_available = free_capacity_available()

    chain: list[Lane] = []
    if free_available:
        chain.extend(("openrouter", slug) for slug in _free_chain())
    chain.extend(("openrouter", slug) for slug in _paid_spill())
    chain.append(local)
    return chain


def select_tier0_lane(*, confidential: bool = False) -> Lane:
    """The single most-preferred lane right now (head of the resolved chain).
    Used by provider_router's tier mapping; callers needing failover walk the
    full ``resolve_tier0_chain`` instead."""
    return resolve_tier0_chain(confidential=confidential)[0]


__all__ = [
    "Lane",
    "DEFAULT_TIER0_FREE_CHAIN",
    "DEFAULT_TIER0_PAID_SPILL",
    "DEFAULT_TIER0_LOCAL_MODEL",
    "DEFAULT_TIER0_RPD_CAP",
    "DEFAULT_TIER0_RPM_CAP",
    "free_capacity_available",
    "record_free_request",
    "resolve_tier0_chain",
    "select_tier0_lane",
]
