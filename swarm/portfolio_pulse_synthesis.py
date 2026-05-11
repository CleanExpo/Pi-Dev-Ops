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
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .portfolio_pulse import PulseResult

log = logging.getLogger("swarm.portfolio_pulse.synthesis")

SYNTHESIS_ROLE = "portfolio.synthesis"
MAX_WORDS = 400
TIMEOUT_S = 90

# RA-1985 sprinkle #3 — second deterministic extraction pass for BOARD-TRIGGERs.
# The first synthesis pass is creative; this is structured-extraction only.
_EXTRACT_MODEL = "claude-haiku-4-5-20251001"
_EXTRACT_MAX_TOKENS = 600
_AUTONOMY_LOG = (
    Path(__file__).resolve().parents[1] / ".harness" / "autonomy.jsonl"
)

_EXTRACT_PROMPT = (
    "Read the daily portfolio synthesis and per-project digests. List every cross-cutting "
    "risk or strategic decision that scores >=6/10 on board-worthiness. Output JSON array: "
    "[{{\"score\": int, \"topic\": str, \"one_line_rationale\": str, \"primary_project\": str}}]. "
    "Return [] if none.\n\n"
    "## First-pass synthesis\n\n{synthesis}\n\n"
    "## Per-project digests\n\n{digests}"
)


def _log_sprinkle_event(event: dict) -> None:
    """Append a structured sprinkle event to .harness/autonomy.jsonl. Never raises."""
    try:
        entry = {**event, "ts": datetime.now(timezone.utc).isoformat()}
        _AUTONOMY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_AUTONOMY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:  # noqa: BLE001
        pass

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


# ── Second-pass BOARD-TRIGGER extraction (RA-1985 sprinkle #3) ───────────────


def _format_triggers(items: list[dict]) -> str:
    """Render extracted triggers as BOARD-TRIGGER sentinels matching margot_bot grammar."""
    lines: list[str] = []
    for item in items:
        try:
            score = int(item.get("score", 0))
            topic = str(item.get("topic", "")).strip()
            rationale = str(item.get("one_line_rationale", "")).strip()
            if score < 6 or not topic or not rationale:
                continue
            topic = topic.replace('"', "'")
            rationale = rationale.replace("\n", " ").strip()
            lines.append(
                f'[BOARD-TRIGGER score={score} topic="{topic}"]{rationale}[/BOARD-TRIGGER]'
            )
        except (TypeError, ValueError):
            continue
    return "\n".join(lines)


def _extract_board_triggers(
    synthesis: str, per_project_pulses: dict[str, "PulseResult"],
) -> str:
    """Second deterministic Haiku pass — extract BOARD-TRIGGER candidates.

    Returns extra newline-joined BOARD-TRIGGER sentinel lines (or "") on any
    failure. Caller falls back to the first-pass synthesis output.
    """
    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return ""
        from anthropic import Anthropic  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        _log_sprinkle_event({
            "sprinkle": "portfolio_pulse_extract",
            "outcome": "sdk_unavailable",
            "error": str(exc),
        })
        return ""

    digests = "\n\n".join(
        _digest_pulse(p) for _pid, p in sorted(per_project_pulses.items())
    )
    digests = digests[:8000]
    prompt = _EXTRACT_PROMPT.format(
        synthesis=synthesis[:4000].replace("{", "{{").replace("}", "}}"),
        digests=digests.replace("{", "{{").replace("}", "}}"),
    )

    try:
        client = Anthropic(api_key=api_key, max_retries=0)
        resp = client.messages.create(
            model=_EXTRACT_MODEL,
            max_tokens=_EXTRACT_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            timeout=30,
        )
        raw = "".join(
            getattr(block, "text", "")
            for block in (resp.content or [])
            if getattr(block, "type", None) == "text"
        ).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        items = json.loads(raw)
        if not isinstance(items, list):
            _log_sprinkle_event({
                "sprinkle": "portfolio_pulse_extract", "outcome": "bad_shape",
            })
            return ""
        rendered = _format_triggers(items)
        _log_sprinkle_event({
            "sprinkle": "portfolio_pulse_extract", "outcome": "ok",
            "candidates": len(items),
            "emitted": rendered.count("[BOARD-TRIGGER"),
        })
        return rendered
    except Exception as exc:  # noqa: BLE001
        log.warning("portfolio_pulse_extract: %s — keeping first-pass output", exc)
        _log_sprinkle_event({
            "sprinkle": "portfolio_pulse_extract", "outcome": "call_failed",
            "error": type(exc).__name__,
        })
        return ""


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

    body = _truncate_to_word_cap(text.strip())

    # RA-1985 sprinkle #3 — deterministic second pass to surface BOARD-TRIGGER
    # candidates the creative first pass missed (audit: misses ~3-4/week).
    # Any failure keeps first-pass output as-is.
    extra_triggers = _extract_board_triggers(body, per_project_pulses)
    if extra_triggers:
        body = f"{body}\n\n{extra_triggers}"

    return body


__all__ = [
    "synthesize",
    "SYNTHESIS_ROLE",
    "MAX_WORDS",
]
