"""
model_policy.py — RA-1099 — single source of truth for which model an agent runs on.

Policy (set by user 2026-04-17):
    Opus 4.7 → ONLY Senior PM (planner) + Senior Orchestrator
    Sonnet 4.6 / Haiku 4.5 → all other agents

Everything that selects a model MUST go through `select_model(role, requested)`.
The function:
  1. Reads the role's configured short name (opus/sonnet/haiku) from
     .harness/config.yaml `agents` section.
  2. If `requested` is set (e.g. caller explicitly passes "haiku"), respects it
     — but ONLY if it doesn't violate the opus-allowed-roles policy.
  3. If the role tries to use opus but is not in OPUS_ALLOWED_ROLES,
     auto-downshifts to sonnet AND emits a structured violation record so the
     drift can be caught in CI / monitoring.

Why this lives outside config.py:
- config.py is loaded extremely early (before logging is configured in some
  paths). Putting policy here lets us emit JSON violation records and keep
  config.py dependency-free.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from app.server import config

_log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
HARNESS_CONFIG_PATH = Path(__file__).resolve().parents[2] / ".harness" / "config.yaml"
VIOLATIONS_PATH     = Path(__file__).resolve().parents[2] / ".harness" / "model-policy-violations.jsonl"


# ── Cached harness config ──────────────────────────────────────────────────
_harness_cache: Optional[dict] = None


def _load_harness() -> dict:
    """Load and cache .harness/config.yaml. Cache is process-wide; restart to refresh."""
    global _harness_cache
    if _harness_cache is None:
        try:
            with HARNESS_CONFIG_PATH.open() as f:
                _harness_cache = yaml.safe_load(f) or {}
        except Exception as exc:
            _log.warning("model_policy: failed to load %s: %s", HARNESS_CONFIG_PATH, exc)
            _harness_cache = {}
    return _harness_cache


# ── Policy enforcement ──────────────────────────────────────────────────────
def _record_violation(role: str, requested: str, granted: str, reason: str) -> None:
    """Append a JSON line to the violations log so monitoring can alert.

    Format: {"ts","role","requested","granted","reason","caller"}
    Fire-and-forget — never raises (a logging failure must not break a build).
    """
    try:
        VIOLATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts":        datetime.now(timezone.utc).isoformat(),
            "role":      role,
            "requested": requested,
            "granted":   granted,
            "reason":    reason,
            "caller":    sys._getframe(2).f_code.co_qualname if hasattr(sys, "_getframe") else "?",
        }
        with VIOLATIONS_PATH.open("a") as f:
            f.write(json.dumps(record) + "\n")
        _log.warning("model_policy: violation role=%s requested=%s granted=%s — %s",
                     role, requested, granted, reason)
    except Exception as exc:
        _log.error("model_policy: failed to record violation (non-fatal): %s", exc)


def select_model(role: str, requested: Optional[str] = None) -> str:
    """Return the short model name (opus/sonnet/haiku) the given role should use.

    Args:
        role: One of "planner", "orchestrator", "generator", "evaluator", "board",
              "monitor", or any custom role declared under `agents:` in config.yaml.
              Unknown roles default to "sonnet".
        requested: Optional override (e.g. caller explicitly wants "haiku" for a
              cheap classification task). Honoured only if it doesn't violate the
              opus-allowed-roles policy.

    Returns:
        Short model name. Always one of ALLOWED_MODELS.
    """
    if requested is not None and requested not in config.ALLOWED_MODELS:
        _log.warning("model_policy: requested=%s not in ALLOWED_MODELS — ignoring", requested)
        requested = None

    # Read role's configured model from harness
    agent_cfg = (_load_harness().get("agents") or {}).get(role, {})
    role_default = agent_cfg.get("model", "sonnet") if isinstance(agent_cfg, dict) else "sonnet"

    # Caller's explicit request takes precedence over config
    chosen = requested or role_default

    # Policy gate: opus is only allowed for OPUS_ALLOWED_ROLES
    if chosen == "opus" and role not in config.OPUS_ALLOWED_ROLES:
        _record_violation(
            role=role,
            requested=chosen,
            granted="sonnet",
            reason=f"opus reserved for roles {sorted(config.OPUS_ALLOWED_ROLES)}",
        )
        return "sonnet"

    return chosen


def assert_model_allowed(role: str, model_id_or_short: str) -> None:
    """Raise ValueError if a long model ID violates the policy.

    Use at API boundaries where a model_id may have leaked through that
    bypasses select_model(). Example: pipeline.py passes a raw model_id to the
    SDK — assert here before the call hits the wire.
    """
    short = model_id_or_short
    # Map long-form IDs back to short names
    for s, lid in config.MODEL_SHORT_TO_ID.items():
        if model_id_or_short == lid:
            short = s
            break
    if short == "opus" and role not in config.OPUS_ALLOWED_ROLES:
        _record_violation(role=role, requested=model_id_or_short, granted="REJECTED",
                          reason="assert_model_allowed: opus violation")
        raise ValueError(
            f"model_policy violation: role={role} cannot use opus "
            f"(allowed roles: {sorted(config.OPUS_ALLOWED_ROLES)})"
        )


def resolve_to_id(short_or_id: str) -> str:
    """Map short name (opus/sonnet/haiku) to long Anthropic model ID.

    Pass-through for already-long IDs. Use at the SDK boundary.
    """
    return config.MODEL_SHORT_TO_ID.get(short_or_id, short_or_id)
