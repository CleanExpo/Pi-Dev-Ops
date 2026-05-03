"""swarm/portfolio_pulse_synthesis.py — RA-1892 (child of RA-1409).

Cross-portfolio synthesis section — the 10x layer of the daily Portfolio
Pulse. After the foundation (RA-1888) renders one section per project,
this module fires ONE top-tier LLM call against the union of pulse data
and produces a 200-400 word executive summary covering cross-cutting
risks, wins, and strategic flags.

Optionally emits a [BOARD-TRIGGER score=N topic="..."]content[/BOARD-TRIGGER]
sentinel using the same grammar as margot_bot, so downstream parsers can
queue board deliberations on findings that score >=7/10.

Design:
  * Sync facade ``synthesize(per_project_pulses)`` — runs the async
    provider call inside an event loop. Foundation calls are sync.
  * All HTTP/LLM errors swallowed; on failure returns a deterministic
    fallback "(synthesis unavailable: <reason>)" markdown body.
  * Provider routing via ``app.server.provider_router.run_via_provider``
    with role ``portfolio.synthesis`` (registered as "top" tier).
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .portfolio_pulse import PulseResult

log = logging.getLogger("swarm.portfolio_pulse.synthesis")

SYNTHESIS_ROLE = "portfolio.synthesis"
MAX_WORDS = 400
TIMEOUT_S = 90

_SYSTEM_PROMPT = (
    "You are the chief-of-staff synthesising a daily portfolio pulse for "
    "Phill McGurk. Read the per-project briefings below and produce a "
    "200-400 word executive summary that opens with 'Across the portfolio "
    "today,' and covers cross-cutting risks, wins, and strategic flags. "
    "If any finding scores >=7/10 in importance, emit a "
    "[BOARD-TRIGGER score=N topic=\"<short topic>\"]<one-line rationale>"
    "[/BOARD-TRIGGER] sentinel after the summary. Be direct, no filler."
)


# ── Per-project digest builder ──────────────────────────────────────────────


def _digest_pulse(pulse: "PulseResult") -> str:
    """Compress one project's PulseResult into a few lines for the prompt."""
    lines = [f"### {pulse.project_id} ({pulse.date})"]
    if pulse.error:
        lines.append(f"(top-level error: {pulse.error})")
    for section in pulse.sections:
        # Trim each section body so a 7-project portfolio fits comfortably
        # under the model's effective context budget.
        body = (section.body_md or "").strip()
        if len(body) > 600:
            body = body[:600] + " …"
        lines.append(f"- **{section.name}:** {body}")
        if section.error:
            lines.append(f"  (section error: {section.error})")
    return "\n".join(lines)


def _build_prompt(per_project_pulses: dict[str, "PulseResult"]) -> str:
    """Build the synthesis prompt — system framing + per-project digests."""
    digests = [
        _digest_pulse(p) for _pid, p in sorted(per_project_pulses.items())
    ]
    return (
        f"{_SYSTEM_PROMPT}\n\n"
        "## Per-project pulses\n\n"
        + "\n\n".join(digests)
        + "\n\nSynthesis:"
    )


# ── Word-cap enforcement ────────────────────────────────────────────────────


def _truncate_to_word_cap(text: str, max_words: int = MAX_WORDS) -> str:
    """Hard cap on word count. Preserves trailing BOARD-TRIGGER sentinels."""
    words = text.split()
    if len(words) <= max_words:
        return text
    log.info(
        "portfolio_pulse_synthesis: truncated synthesis %d → %d words",
        len(words), max_words,
    )
    return " ".join(words[:max_words]).rstrip() + " …"


# ── LLM call ────────────────────────────────────────────────────────────────


def _call_llm(prompt: str) -> tuple[str, str | None]:
    """Fire the synthesis call via provider_router. Returns (text, error)."""
    try:
        from app.server.provider_router import run_via_provider  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return "", f"provider_router_unavailable: {exc}"

    async def _fire() -> tuple[int, str, float, str | None]:
        return await run_via_provider(
            prompt=prompt,
            role=SYNTHESIS_ROLE,
            timeout_s=TIMEOUT_S,
            session_id="portfolio-pulse-synthesis",
            thinking="adaptive",
        )

    try:
        # If we are already inside an event loop (rare for the daily pulse
        # cron, but possible from tests), use asyncio.run_coroutine_threadsafe
        # is overkill; instead fall back to a fresh loop in a thread.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            rc, text, _cost, error = asyncio.run(_fire())
        else:
            # Already in a loop — run in a worker thread with its own loop.
            import threading  # noqa: PLC0415
            result: dict[str, object] = {}

            def _runner() -> None:
                try:
                    result["value"] = asyncio.run(_fire())
                except Exception as exc:  # noqa: BLE001
                    result["error"] = str(exc)

            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            t.join(timeout=TIMEOUT_S + 30)
            if "error" in result:
                return "", f"thread_runner_failed: {result['error']}"
            if "value" not in result:
                return "", "thread_runner_timeout"
            rc, text, _cost, error = result["value"]  # type: ignore[misc]
    except Exception as exc:  # noqa: BLE001
        return "", f"synthesis_call_raised: {exc}"

    if rc != 0 or error:
        return "", error or f"rc={rc}"
    return text or "", None


# ── Public API ──────────────────────────────────────────────────────────────


def synthesize(per_project_pulses: dict[str, "PulseResult"]) -> str:
    """Build the cross-portfolio synthesis markdown section.

    Args:
        per_project_pulses: mapping of project_id → PulseResult, as
            produced by ``portfolio_pulse.run_all_projects()``.

    Returns:
        Markdown body (≤400 words) with the executive summary. On any
        LLM/HTTP failure returns a deterministic fallback body.
    """
    if not per_project_pulses:
        return "_(synthesis unavailable: no per-project pulses provided)_"

    prompt = _build_prompt(per_project_pulses)
    text, error = _call_llm(prompt)

    if error or not text.strip():
        return f"_(synthesis unavailable: {error or 'empty_response'})_"

    return _truncate_to_word_cap(text.strip())


__all__ = [
    "synthesize",
    "SYNTHESIS_ROLE",
    "MAX_WORDS",
]
