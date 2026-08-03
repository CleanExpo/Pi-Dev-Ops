"""Margot ElevenLabs voice SSOT.

Every Margot-owned TTS surface (Telegram voice replies, 6-pager audio,
portfolio pulse, future CRM widget) must resolve voice IDs through
``resolve_margot_voice_id()`` only.

**Do not use ``ELEVENLABS_VOICE_ID`` or ``SYNTHEX_ELEVENLABS_VOICE_ID`` for
Margot** — those env vars belong to other agents (e.g. Synthex Remotion).
Margot's locked voice is ``p43fx6U8afP2xoq1Ai9f`` (override via
``MARGOT_ELEVENLABS_VOICE_ID`` for staging only).

Canonical ID: ``config/harness/margot/assets/margot_identity.json`` →
``packages/brand-config`` ``MARGOT_ELEVENLABS_VOICE_ID``.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from app.server import config_loader

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IDENTITY_PATH = config_loader.MARGOT_IDENTITY_JSON

# Locked ElevenLabs voice for Margot (founder-approved 2026-07-02).
_CANONICAL_VOICE_ID = "p43fx6U8afP2xoq1Ai9f"


@lru_cache(maxsize=1)
def _voice_id_from_identity_json() -> str | None:
    """Resolve the locked ElevenLabs voice id. Raises if the identity file is absent.

    WAS: a bare `except: return None`. A None voice id falls through to whatever default
    the caller uses, so synthesising in the WRONG VOICE was silent. An external resource
    identifier is never defaulted - see config_loader.margot_identity().
    """
    data = config_loader.margot_identity()
    elevenlabs = data.get("elevenlabs") or {}
    return (elevenlabs.get("voice_id") or "").strip() or None


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
