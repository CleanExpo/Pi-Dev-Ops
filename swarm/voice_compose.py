"""swarm/voice_compose.py — RA-1866 (Wave 4 B3): Voice variant for the 6-pager.

Takes a Pi-CEO daily 6-pager (as text) and produces a voice-friendly
version, optionally synthesising it via ElevenLabs TTS into an MP3 the
CoS Telegram bot can attach.

Two-stage pipeline:
1. ``voice_friendly_text(brief)`` — pure text transform: strip emoji,
   normalise currency / percentage / abbreviations, replace section
   numbering with spoken transitions ("Section 1 of 6: CFO daily"),
   collapse bullet markers. No external calls.
2. ``synthesise_voice(text, out_path)`` — POSTs to ElevenLabs if
   ``ELEVENLABS_API_KEY`` is in env; otherwise returns None (caller
   falls back to text-only delivery).

The composer never crashes the cycle — every external-effect step
returns None on error and logs a warning; CoS continues with text-only.

Public API:
  voice_friendly_text(brief)             -> str
  compose_voice_variant(brief, out_dir)  -> tuple[str, str | None]
                                            (text, audio_path_or_None)
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from pathlib import Path

log = logging.getLogger("swarm.voice_compose")

ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs default "Rachel"
HTTP_TIMEOUT_S = 30.0


# ── Text transforms ─────────────────────────────────────────────────────────


_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001F9FF"   # symbols & pictographs (broad block)
    "\U0001F600-\U0001F64F"   # emoticons
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F1E0-\U0001F1FF"   # flags
    "\u2600-\u27BF"           # misc symbols + dingbats
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    """Remove emoji + variation selectors that screen readers mis-pronounce."""
    text = _EMOJI_PATTERN.sub(" ", text)
    text = "".join(
        ch for ch in text if unicodedata.category(ch) != "Cf"
    )  # zero-width / variation selectors
    return text


def _normalise_currency(text: str) -> str:
    """`$1,250.00` → `one thousand two hundred fifty dollars` (rough)."""
    def _replace(match: re.Match) -> str:
        raw = match.group(0)
        digits = re.sub(r"[^\d.]", "", raw)
        try:
            n = float(digits)
        except ValueError:
            return raw
        if n.is_integer():
            return f"{int(n):,} dollars"
        return f"{n:,.2f} dollars"
    return re.sub(r"\$[\d,]+(?:\.\d+)?", _replace, text)


def _normalise_percentage(text: str) -> str:
    """`12.5%` → `12.5 percent`. `99.99%` → `99.99 percent`."""
    return re.sub(r"(\d+(?:\.\d+)?)%", r"\1 percent", text)


def _normalise_abbreviations(text: str) -> str:
    """Replace acronyms voice-listeners commonly mis-hear."""
    swaps = {
        "MRR": "M R R monthly recurring revenue",
        "ARR": "A R R annual recurring revenue",
        "NRR": "N R R net retention",
        "GRR": "G R R gross retention",
        "FCR": "first contact resolution",
        "NPS": "N P S",
        "CPA": "C P A cost per acquisition",
        "LTV:CAC": "L T V to C A C",
        "CFR": "change failure rate",
        "MTTR": "mean time to recover",
        "DORA": "D O R A",
        "p99": "p ninety-nine",
        "PR": "pull request",
        "CFO": "C F O",
        "CMO": "C M O",
        "CTO": "C T O",
        "CS": "customer success",
        "GM": "gross margin",
    }
    for k, v in swaps.items():
        text = re.sub(rf"\b{re.escape(k)}\b", v, text)
    return text


_SECTION_NUMBERS = re.compile(r"^([1-6])\.\s+", flags=re.MULTILINE)


def _spoken_section_transitions(text: str) -> str:
    """`1. ` at start of line → "Section 1 of 6: "."""
    def _r(match: re.Match) -> str:
        n = match.group(1)
        return f"Section {n} of 6: "
    return _SECTION_NUMBERS.sub(_r, text)


def _strip_bullets(text: str) -> str:
    """Collapse markdown bullets / dividers into clean prose lines."""
    text = re.sub(r"^[-*•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*—+\s*$", "", text, flags=re.MULTILINE)
    return text


def voice_friendly_text(brief: str) -> str:
    """Transform a 6-pager into prose suitable for TTS narration.

    Order: emoji-strip → currency → percentage → abbreviations → section
    numbering → bullet flatten → collapse repeated newlines.
    """
    out = _strip_emoji(brief)
    out = _normalise_currency(out)
    out = _normalise_percentage(out)
    out = _normalise_abbreviations(out)
    out = _spoken_section_transitions(out)
    out = _strip_bullets(out)
    out = re.sub(r"\n{2,}", "\n\n", out)
    return out.strip()


# ── ElevenLabs synthesis ────────────────────────────────────────────────────


def synthesise_voice(text: str, *, out_path: Path,
                      voice_id: str | None = None,
                      api_key: str | None = None) -> Path | None:
    """POST to ElevenLabs TTS. Returns out_path on success, None on failure.

    httpx is imported lazily so callers in environments without httpx still
    get a clean None rather than ImportError.
    """
    api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        log.info("voice_compose: ELEVENLABS_API_KEY missing — text-only fallback")
        return None

    voice_id = voice_id or os.environ.get(
        "ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID
    )

    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("voice_compose: httpx import failed (%s) — text-only", exc)
        return None

    url = f"{ELEVENLABS_API_BASE}/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    body = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.85},
    }

    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_S) as client:
            r = client.post(url, headers=headers, json=body)
            r.raise_for_status()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(r.content)
            log.info("voice_compose: TTS wrote %d bytes to %s",
                     len(r.content), out_path)
            return out_path
    except Exception as exc:  # noqa: BLE001
        log.warning("voice_compose: ElevenLabs call failed (%s)", exc)
        return None


def compose_voice_variant(
    brief: str, *,
    out_dir: Path,
    filename_stem: str = "six-pager",
) -> tuple[str, Path | None]:
    """Produce (voice_friendly_text, audio_path_or_None) from a 6-pager.

    Caller (CoS bot daily-fire) attaches the audio_path if non-None,
    otherwise sends the voice_friendly_text as-is.
    """
    spoken = voice_friendly_text(brief)
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = out_dir / f"{filename_stem}.mp3"
    written = synthesise_voice(spoken, out_path=audio_path)
    return spoken, written


# ── Margot reply voice variant ──────────────────────────────────────────────


# Default cap — anything longer than this becomes a 60s+ voice clip,
# which is awkward for conversational interface. Founder can override
# via MARGOT_VOICE_REPLY_MAX_CHARS env.
MARGOT_VOICE_MAX_CHARS_DEFAULT = 800


def margot_reply_friendly_text(reply: str) -> str:
    """Lighter version of voice_friendly_text for Margot's conversational
    replies. The reply is already prose (not a structured 6-pager), so
    we skip section-transition rewriting and bullet flattening; only
    emoji-strip + abbreviation expansion + currency/percentage are useful.
    """
    out = _strip_emoji(reply)
    out = _normalise_currency(out)
    out = _normalise_percentage(out)
    out = _normalise_abbreviations(out)
    # Collapse multiple blank lines (no section headers in conversation)
    out = re.sub(r"\n{2,}", "\n\n", out)
    return out.strip()


def compose_margot_voice_reply(
    reply_text: str, *,
    out_dir: Path,
    filename_stem: str,
    max_chars: int | None = None,
) -> tuple[str, Path | None]:
    """Produce (voice_friendly_text, audio_path_or_None) for a Margot
    conversational reply.

    Returns (voice_text, None) when:
      - ELEVENLABS_API_KEY missing
      - reply exceeds max_chars (default 800; voice would be too long)
      - httpx unavailable
      - TTS call fails

    The caller's job: if audio_path is not None, send voice + text
    together; otherwise send text only.
    """
    cap = max_chars or int(
        os.environ.get(
            "MARGOT_VOICE_REPLY_MAX_CHARS",
            MARGOT_VOICE_MAX_CHARS_DEFAULT,
        )
    )

    spoken = margot_reply_friendly_text(reply_text)
    if len(spoken) > cap:
        log.info(
            "margot voice: reply %d chars > cap %d — text-only",
            len(spoken), cap,
        )
        return spoken, None

    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = out_dir / f"{filename_stem}.mp3"
    written = synthesise_voice(spoken, out_path=audio_path)
    return spoken, written


__all__ = [
    "voice_friendly_text",
    "margot_reply_friendly_text",
    "synthesise_voice",
    "compose_voice_variant",
    "compose_margot_voice_reply",
    "MARGOT_VOICE_MAX_CHARS_DEFAULT",
]
