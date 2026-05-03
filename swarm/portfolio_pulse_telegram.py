"""swarm/portfolio_pulse_telegram.py — RA-1893 (child of RA-1409).

Telegram delivery layer for the daily Portfolio Pulse. Splits the rendered
pulse markdown into Telegram-sized chunks (<= 4096 chars), sends each
chunk via the existing ``swarm.telegram_alerts.send`` helper as the
"Margot" bot, and optionally attaches a voice variant of the
cross-portfolio synthesis section.

Public API:
  deliver_to_telegram(pulse_md, *, voice=True, chat_id=None) -> dict

Resilience contract:
  * No chat id available -> {"sent": False, "error": "no_chat_id"}; never raises.
  * Per-chunk send failure -> recorded into errors list; partial delivery
    is still considered partially sent.
  * Voice infra missing -> logged once, skipped, text continues.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.portfolio_pulse_telegram")

TELEGRAM_HARD_LIMIT = 4096
# Leave headroom for the AGENT OUTPUT prefix that telegram_alerts.send
# prepends. The prefix is ~120 chars for Margot at info severity; cap
# message body at 3800 to stay well under 4096 after prefixing.
CHUNK_BUDGET = 3800

SYNTHESIS_HEADING = "## Cross-portfolio synthesis"


# -- Chunking ----------------------------------------------------------------


def _split_at_section_boundaries(md: str, budget: int) -> list[str]:
    """Greedy split that prefers H2 section boundaries.

    The pulse is a sequence of `## ` blocks. Pack whole sections into
    chunks until adding the next section would exceed budget; then start
    a new chunk. Sections larger than budget fall through to char-level
    split inside ``_chunk``.
    """
    if not md:
        return []
    # Anchor split on lines that begin with "## " — keep the heading
    # attached to its block.
    lines = md.split("\n")
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("## ") and current:
            blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))

    chunks: list[str] = []
    buf = ""
    for block in blocks:
        # Block itself larger than budget — char-split it standalone.
        if len(block) > budget:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(_char_split(block, budget))
            continue
        candidate = f"{buf}\n\n{block}".strip() if buf else block
        if len(candidate) > budget:
            chunks.append(buf)
            buf = block
        else:
            buf = candidate
    if buf:
        chunks.append(buf)
    return chunks


def _char_split(text: str, budget: int) -> list[str]:
    """Hard char-level split for blocks that exceed budget."""
    return [text[i : i + budget] for i in range(0, len(text), budget)]


def _chunk(md: str, budget: int = CHUNK_BUDGET) -> list[str]:
    """Public chunker — section-aware with char-level fallback."""
    if not md:
        return []
    if len(md) <= budget:
        return [md]
    return _split_at_section_boundaries(md, budget)


# -- Synthesis extraction ----------------------------------------------------


def _extract_synthesis(md: str) -> str | None:
    """Return the cross-portfolio synthesis section body, or None.

    The synthesis section is identified by ``SYNTHESIS_HEADING`` and
    runs until the next ``## `` heading or end of document.
    """
    idx = md.find(SYNTHESIS_HEADING)
    if idx == -1:
        return None
    rest = md[idx + len(SYNTHESIS_HEADING) :]
    next_h2 = rest.find("\n## ")
    body = rest if next_h2 == -1 else rest[:next_h2]
    return body.strip() or None


# -- Voice composition -------------------------------------------------------


def _voice_enabled() -> bool:
    return os.environ.get("MARGOT_VOICE_REPLY_ENABLED", "0") == "1"


def _maybe_compose_synthesis_voice(
    synthesis_text: str, *, repo_root: Path | None = None,
) -> Path | None:
    """Compose voice variant of the synthesis section, or None on miss.

    Failures are non-fatal: missing module / missing key / TTS error all
    return None and the text-only path proceeds.
    """
    if not synthesis_text:
        return None
    try:
        import sys as _sys  # noqa: PLC0415
        voice_compose = _sys.modules.get("swarm.voice_compose")
        if voice_compose is None:
            from . import voice_compose  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.info("pulse voice: voice_compose unavailable (%s)", exc)
        return None
    rr = repo_root or Path.cwd()
    out_dir = rr / ".harness/portfolio-pulse/voice"
    try:
        _, audio_path = voice_compose.compose_margot_voice_reply(
            synthesis_text,
            out_dir=out_dir,
            filename_stem="pulse-synthesis",
        )
    except Exception as exc:  # noqa: BLE001
        log.info("pulse voice: compose raised (%s)", exc)
        return None
    return audio_path


# -- Telegram send -----------------------------------------------------------


def _send_chunk(
    text: str, *, chat_id: str, audio_path: Path | None = None,
) -> tuple[bool, str | None]:
    """Send a single chunk via telegram_alerts.send.

    Tries audio_path kwarg if supplied; falls back to plain text on
    TypeError. Returns (ok, error_str_or_None).
    """
    try:
        import sys as _sys  # noqa: PLC0415
        telegram_alerts = _sys.modules.get("swarm.telegram_alerts")
        if telegram_alerts is None:
            from . import telegram_alerts  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return False, f"telegram_alerts_unavailable: {exc}"

    sender = getattr(telegram_alerts, "send", None)
    if not callable(sender):
        return False, "no_send_fn"

    kwargs: dict[str, Any] = {
        "severity": "info",
        "bot_name": "Margot",
        "chat_id": chat_id,
    }
    if audio_path is not None:
        kwargs["audio_path"] = str(audio_path)

    try:
        ok = sender(text, **kwargs)
    except TypeError:
        try:
            ok = sender(text, severity="info", bot_name="Margot")
        except Exception as exc:  # noqa: BLE001
            return False, f"send_fallback_failed: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"send_failed: {exc}"

    if ok is False:
        return False, "send_returned_false"
    return True, None


# -- Public API --------------------------------------------------------------


def deliver_to_telegram(
    pulse_md: str,
    *,
    voice: bool = True,
    chat_id: str | None = None,
    repo_root: Path | None = None,
) -> dict:
    """Split the pulse into Telegram-sized chunks and send via Margot bot.

    Args:
        pulse_md: Rendered markdown of the daily pulse (or aggregated multi-
            project pulse plus synthesis section).
        voice: If True and ``MARGOT_VOICE_REPLY_ENABLED=1``, attach a voice
            variant of the cross-portfolio synthesis section ONLY (not the
            per-project detail).
        chat_id: Telegram chat id. When None, falls back to env
            ``MARGOT_DM_CHAT_ID``. If both missing, returns a dict with
            ``sent=False`` and ``error="no_chat_id"`` (does NOT raise).
        repo_root: Used to anchor the voice output dir; defaults to CWD.

    Returns:
        ``{"sent": bool, "chunks": int, "voice_attached": bool,
            "errors": [{"chunk_idx": int, "error": str}, ...]}``
    """
    target_chat = chat_id or (os.environ.get("MARGOT_DM_CHAT_ID") or "").strip()
    if not target_chat:
        return {
            "sent": False,
            "chunks": 0,
            "voice_attached": False,
            "errors": [],
            "error": "no_chat_id",
        }

    chunks = _chunk(pulse_md)
    if not chunks:
        return {
            "sent": False,
            "chunks": 0,
            "voice_attached": False,
            "errors": [],
            "error": "empty_pulse",
        }

    # Voice variant — only when caller opts in AND the env flag is set.
    audio_path: Path | None = None
    if voice and _voice_enabled():
        synthesis = _extract_synthesis(pulse_md)
        if synthesis:
            audio_path = _maybe_compose_synthesis_voice(
                synthesis, repo_root=repo_root,
            )

    voice_attached = False
    errors: list[dict[str, Any]] = []
    successes = 0
    last_idx = len(chunks) - 1
    for idx, chunk in enumerate(chunks):
        # Attach the voice file with the LAST chunk, so the audio appears
        # after all the text content.
        attach = audio_path if idx == last_idx else None
        ok, err = _send_chunk(chunk, chat_id=target_chat, audio_path=attach)
        if ok:
            successes += 1
            if attach is not None:
                voice_attached = True
        else:
            errors.append({"chunk_idx": idx, "error": err or "unknown"})

    sent = successes == len(chunks)
    return {
        "sent": sent,
        "chunks": len(chunks),
        "voice_attached": voice_attached,
        "errors": errors,
    }


__all__ = [
    "deliver_to_telegram",
    "TELEGRAM_HARD_LIMIT",
    "CHUNK_BUDGET",
    "SYNTHESIS_HEADING",
]
