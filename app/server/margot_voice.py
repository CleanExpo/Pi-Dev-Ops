"""Margot ElevenLabs voice SSOT.

Every Margot-owned TTS surface (Telegram voice replies, 6-pager audio,
portfolio pulse, future CRM widget) must resolve voice IDs through
``resolve_margot_voice_id()`` only.

**Do not use ``ELEVENLABS_VOICE_ID`` or ``SYNTHEX_ELEVENLABS_VOICE_ID`` for
Margot** — those env vars belong to other agents (e.g. Synthex Remotion).
Margot's locked voice is ``p43fx6U8afP2xoq1Ai9f`` (override via
``MARGOT_ELEVENLABS_VOICE_ID`` for staging only).

Canonical ID: ``.harness/margot/assets/margot_identity.json`` →
``packages/brand-config`` ``MARGOT_ELEVENLABS_VOICE_ID``.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IDENTITY_PATH = _REPO_ROOT / ".harness" / "margot" / "assets" / "margot_identity.json"

# Locked ElevenLabs voice for Margot (founder-approved 2026-07-02).
_CANONICAL_VOICE_ID = "p43fx6U8afP2xoq1Ai9f"


@lru_cache(maxsize=1)
def _voice_id_from_identity_json() -> str | None:
    try:
        data = json.loads(_IDENTITY_PATH.read_text(encoding="utf-8"))
        elevenlabs = data.get("elevenlabs") or {}
        voice_id = (elevenlabs.get("voice_id") or "").strip()
        return voice_id or None
    except Exception:
        return None


def resolve_margot_voice_id() -> str:
    """Return Margot's ElevenLabs voice ID for all Margot-owned surfaces."""
    override = (
        os.environ.get("MARGOT_ELEVENLABS_VOICE_ID", "").strip()
        or os.environ.get("MARGOT_VOICE_ID", "").strip()
    )
    if override:
        return override
    return _voice_id_from_identity_json() or _CANONICAL_VOICE_ID


__all__ = ["resolve_margot_voice_id", "_CANONICAL_VOICE_ID"]
