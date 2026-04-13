"""
session_evaluator.py — Evaluator logic for Pi-CEO build sessions.

Extracted from sessions.py (RA-890). Contains all score parsing, confidence
extraction, alert dispatching, and the three evaluator runners:

  - _parse_evaluator_dimensions()  — parse 4 dimension scores from eval output
  - _extract_eval_score()          — parse OVERALL: <n>/10
  - _extract_eval_confidence()     — parse CONFIDENCE: <pct>%
  - _send_low_confidence_alert()   — fire-and-forget Telegram alert (RA-674)
  - _get_claude_md()               — lazy-load CLAUDE.md for prompt caching (RA-655)
  - _run_eval_with_cache()         — single cached direct-API eval (RA-655)
  - _run_parallel_eval_cached()    — parallel sonnet+haiku cached eval (RA-655)
  - _run_single_eval()             — single SDK or subprocess eval pass
  - _run_parallel_eval()           — parallel sonnet+haiku + Opus escalation

Import graph:
  session_evaluator  →  session_sdk  (for _write_sdk_metric, _run_claude_via_sdk)
  session_evaluator  →  session_model (for em, BuildSession)
  session_evaluator  →  config

Public API (re-exported by sessions.py for backward compatibility):
  All nine functions above.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.request
from typing import Optional

from . import config
from .session_model import em
from .session_sdk import _write_sdk_metric, _run_claude_via_sdk

_log = logging.getLogger("pi-ceo.session_evaluator")

# ── Prompt caching (RA-655) ───────────────────────────────────────────────────

_claude_md_cache: Optional[str] = None


def _get_claude_md() -> str:
    """Lazy-load CLAUDE.md content for cached system prompt (RA-655)."""
    global _claude_md_cache
    if _claude_md_cache is None:
        try:
            path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "CLAUDE.md")
            )
            with open(path, encoding="utf-8") as f:
                _claude_md_cache = f.read()
        except Exception:
            _claude_md_cache = ""
    return _claude_md_cache


# ── Score / confidence parsers ─────────────────────────────────────────────────

def _parse_evaluator_dimensions(eval_text: str) -> dict:
    """Parse all 4 evaluator dimension scores from output text.
    Returns {dimension_name: (score, reason)}."""
    dimensions = {}
    for line in eval_text.split("\n"):
        line_upper = line.strip().upper()
        for dim in ("COMPLETENESS", "CORRECTNESS", "CONCISENESS", "FORMAT"):
            if line_upper.startswith(dim + ":"):
                try:
                    rest = line.split(":", 1)[1].strip()
                    score_str = rest.split("/")[0].strip()
                    reason = rest.split("\u2014", 1)[1].strip() if "\u2014" in rest else rest
                    dimensions[dim.lower()] = (float(score_str), reason[:200])
                except (ValueError, IndexError):
                    pass
    return dimensions


def _extract_eval_score(text: str) -> Optional[float]:
    """Parse the OVERALL: <score>/10 line from evaluator output."""
    for line in text.split("\n"):
        if line.upper().startswith("OVERALL:"):
            try:
                return float(line.split(":")[1].strip().split("/")[0].strip())
            except (ValueError, IndexError):
                pass
    return None


def _extract_eval_confidence(text: str) -> Optional[float]:
    """RA-674 — Parse CONFIDENCE: <percent>% line from evaluator output.

    Returns a float in [0, 100] or None if the line is absent / unparseable.
    """
    for line in text.split("\n"):
        if line.upper().startswith("CONFIDENCE:"):
            try:
                rest = line.split(":", 1)[1].strip()
                pct_str = rest.split("%")[0].strip()
                val = float(pct_str)
                return max(0.0, min(100.0, val))
            except (ValueError, IndexError):
                pass
    return None


# ── Alert helpers ──────────────────────────────────────────────────────────────

def _send_low_confidence_alert(session, score: float, confidence: float) -> None:
    """RA-674 — Fire-and-forget Telegram alert when an evaluator decision is low-confidence.

    Triggers when score ≥ threshold but confidence < EVAL_FLAG_CONFIDENCE.  The build
    ships (the score gate passed), but the operator is notified to review manually.
    """
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_ALERT_CHAT_ID
    if not token or not chat_id:
        return
    repo = (getattr(session, "repo_url", "") or "").rstrip("/").split("/")[-1] or "unknown"
    msg = (
        f"⚠️ *Evaluator: Low-Confidence Gate Decision*\n\n"
        f"Session: `{session.id}`\n"
        f"Repo: `{repo}`\n"
        f"Score: *{score:.1f}/10* (PASS — above threshold)\n"
        f"Confidence: *{confidence:.0f}%* (below {int(config.EVAL_FLAG_CONFIDENCE)}% flag threshold)\n\n"
        f"Build shipped but evaluator certainty is low. Manual review recommended."
    )
    payload = json.dumps({
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8):
            pass
        _log.info(
            "Low-confidence alert sent: session=%s score=%.1f confidence=%.0f%%",
            session.id, score, confidence,
        )
    except Exception as exc:
        _log.warning("Low-confidence Telegram alert failed (non-fatal): %s", exc)


# ── Cached evaluator (RA-655) ──────────────────────────────────────────────────

async def _run_eval_with_cache(
    *,
    brief_context: str,
    diff_out: str,
    diff_context: str,
    model: str,
    threshold: int,
    timeout: int = 120,
    session_id: str = "",
) -> tuple[Optional[float], str]:
    """RA-655 — Evaluator via direct Anthropic API with prompt caching.

    System blocks (ephemeral cache):
      1. CLAUDE.md — project context, ~1200 tokens, reused across all eval rounds
      2. Static grading criteria — same for every eval in the same build

    User message (dynamic):
      Brief + diff output

    Returns (score_or_None, text). Returns (None, "") on any error so caller
    can fall back to the Agent SDK path.
    """
    try:
        import anthropic as _anthropic  # noqa: PLC0415
    except ImportError:
        return None, ""

    api_key = config.ANTHROPIC_API_KEY
    if not api_key:
        return None, ""

    _MODEL_IDS = {
        "opus": "claude-opus-4-6",
        "sonnet": "claude-sonnet-4-6",
        "haiku": "claude-haiku-4-5-20251001",
    }
    full_model = _MODEL_IDS.get(model, model)

    eval_criteria = (
        "You are a senior code reviewer evaluating AI-generated changes. "
        "Be rigorous — your job is to catch every gap and flaw.\n\n"
        "Grade on 4 dimensions (1-10). Scoring guide:\n"
        "  10 = production-ready, exceeds expectations\n"
        "   9 = complete and correct, minor style preferences only\n"
        "   8 = solid work, 1-2 small gaps or nits\n"
        "   7 = acceptable but missing something meaningful\n"
        "  \u22646 = clear deficiency that must be fixed\n\n"
        "DIMENSION CRITERIA:\n"
        "1. COMPLETENESS \u2014 Does the diff address EVERY requirement in the brief? "
        "List any unmet requirements. Partial = \u22646.\n"
        "2. CORRECTNESS \u2014 Any bugs, logic errors, type issues, null refs, security "
        "vulnerabilities, or broken tests? One confirmed bug = \u22646.\n"
        "3. CONCISENESS \u2014 Any dead code, debug prints, TODO stubs, or over-engineered "
        "abstractions? Tight, purposeful code = 9-10.\n"
        "4. FORMAT \u2014 Does it match the project's existing conventions exactly? "
        "Style violations or inconsistent naming = \u22646.\n\n"
        "OUTPUT FORMAT: Respond with exactly 4 dimension lines, the overall, then a confidence line:\n"
        "COMPLETENESS: <score>/10 \u2014 <reason>\n"
        "CORRECTNESS: <score>/10 \u2014 <reason>\n"
        "CONCISENESS: <score>/10 \u2014 <reason>\n"
        "FORMAT: <score>/10 \u2014 <reason>\n"
        f"OVERALL: <average>/10 \u2014 PASS or FAIL (threshold: {threshold}/10)\n"
        "CONFIDENCE: <0-100>% \u2014 <how certain are you? consider: diff clarity, "
        "requirements ambiguity, borderline score, incomplete context. "
        "100% = unambiguous; 50% = borderline; <60% = genuinely uncertain>"
    )

    system_blocks: list[dict] = []
    claude_md = _get_claude_md()
    if claude_md:
        system_blocks.append({
            "type": "text",
            "text": claude_md,
            "cache_control": {"type": "ephemeral"},
        })
    system_blocks.append({
        "type": "text",
        "text": eval_criteria,
        "cache_control": {"type": "ephemeral"},
    })

    user_content = (
        "ORIGINAL BRIEF (what was asked for):\n" + brief_context + "\n\n"
        "DIFF SUMMARY:\n" + (diff_out or "(empty)") + "\n\n"
        "DIFF DETAIL (truncated to 8000 chars):\n" + diff_context
    )

    t0 = time.monotonic()
    try:
        client = _anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=full_model,
            max_tokens=512,
            system=system_blocks,
            messages=[{"role": "user", "content": user_content}],
            timeout=timeout,
        )
        text = message.content[0].text if message.content else ""
        usage = message.usage
        _log.info(
            "eval-cache model=%s input=%d cache_write=%d cache_read=%d output=%d latency=%.1fs",
            model,
            getattr(usage, "input_tokens", 0),
            getattr(usage, "cache_creation_input_tokens", 0),
            getattr(usage, "cache_read_input_tokens", 0),
            getattr(usage, "output_tokens", 0),
            time.monotonic() - t0,
        )
        _write_sdk_metric(
            session_id=session_id, phase=f"evaluator_cached_{model}",
            model=model, success=True,
            latency_s=time.monotonic() - t0, output_len=len(text),
        )
        return _extract_eval_score(text), text
    except Exception as exc:
        _log.warning("eval-cache model=%s failed: %s — will fall back", model, exc)
        _write_sdk_metric(
            session_id=session_id, phase=f"evaluator_cached_{model}",
            model=model, success=False,
            latency_s=time.monotonic() - t0, output_len=0, error=str(exc),
        )
        return None, ""


async def _run_parallel_eval_cached(
    session,
    brief_context: str,
    diff_out: str,
    diff_context: str,
    threshold: int,
    sid: str = "",
) -> tuple[Optional[float], str, str, str]:
    """RA-655 — Parallel evaluator using cached direct API calls.

    Same return type as _run_parallel_eval: (score, text, model_label, consensus_detail).
    Returns ("", "", "", "cache-all-failed") tuple with None score if both evals fail,
    so caller can fall back to the Agent SDK path.
    """
    em(session, "tool", "  $ anthropic.messages (cached) sonnet + haiku [parallel]")
    kwargs = dict(
        brief_context=brief_context,
        diff_out=diff_out,
        diff_context=diff_context,
        threshold=threshold,
        session_id=sid,
    )
    (s_score, s_text), (h_score, h_text) = await asyncio.gather(
        _run_eval_with_cache(model="sonnet", **kwargs),
        _run_eval_with_cache(model="haiku", **kwargs),
    )
    if s_score is None and h_score is None:
        return None, "", "", "cache-all-failed"

    # Same consensus logic as _run_parallel_eval
    if s_score is None:
        return h_score, h_text, "haiku(cached)", "sonnet-failed"
    if h_score is None:
        return s_score, s_text, "sonnet(cached)", "haiku-failed"

    delta = abs(s_score - h_score)
    consensus = f"sonnet={s_score:.1f} haiku={h_score:.1f} delta={delta:.1f}"
    if delta <= 2:
        return (s_score + h_score) / 2, s_text, "sonnet+haiku(cached)", consensus

    em(session, "agent", f"  Evaluator delta={delta:.1f} > 2 — escalating to Opus (cached)")
    o_score, o_text = await _run_eval_with_cache(model="opus", timeout=180, **kwargs)
    if o_score is None:
        return (s_score + h_score) / 2, s_text, "sonnet+haiku(cached)", f"{consensus} opus-failed"
    weighted = o_score * 0.6 + s_score * 0.3 + h_score * 0.1
    return weighted, o_text, "opus+sonnet+haiku(cached)", f"{consensus} opus={o_score:.1f}"


# ── SDK / subprocess evaluator runners ────────────────────────────────────────

async def _run_single_eval(
    workspace: str,
    eval_spec: str,
    model: str,
    timeout: int = 120,
    session_id: str = "",
) -> tuple[Optional[float], str]:
    """Run one evaluator pass. Returns (score_or_None, full_output_text).

    When TAO_USE_AGENT_SDK=1, tries the SDK path first (text-only response).
    Falls back to subprocess on SDK error.
    """
    # ── SDK path ─────────────────────────────────────────────────────────────
    if config.USE_AGENT_SDK:
        rc, sdk_text, _ = await _run_claude_via_sdk(
            eval_spec, model, workspace, timeout=timeout,
            session_id=session_id, phase="evaluator",
        )
        if rc == 0 and sdk_text.strip():
            return _extract_eval_score(sdk_text), sdk_text
        # RA-576: SDK required — do not fall back to subprocess evaluator.
        _log.warning("SDK evaluator failed rc=%d — returning None (no subprocess fallback) [RA-576]", rc)
        return None, ""

    # ── Subprocess path — only reached when USE_AGENT_SDK=0 ──────────────
    cmd = [config.CLAUDE_CMD, *config.CLAUDE_EXTRA_FLAGS, "-p", eval_spec,
           "--model", model, "--output-format", "text"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=workspace,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        text = out.decode("utf-8", errors="replace").strip()
    except (asyncio.TimeoutError, Exception):
        return None, ""
    return _extract_eval_score(text), text


async def _run_parallel_eval(session, eval_spec: str) -> tuple[Optional[float], str, str, str]:
    """Run Sonnet + Haiku in parallel; escalate to Opus when |delta| > 2.

    Returns (final_score, primary_eval_text, evaluator_model_label, consensus_detail).
    Weighted average on escalation: Opus 60%, Sonnet 30%, Haiku 10%.
    """
    em(session, "tool", "  $ claude --model sonnet (eval-1) | claude --model haiku (eval-2) [parallel]")
    sid = getattr(session, "id", "")
    (s_score, s_text), (h_score, h_text) = await asyncio.gather(
        _run_single_eval(session.workspace, eval_spec, "sonnet", session_id=sid),
        _run_single_eval(session.workspace, eval_spec, "haiku", session_id=sid),
    )
    if s_score is None and h_score is None:
        return None, "", "sonnet+haiku", "both evals failed"
    if s_score is None:
        return h_score, h_text, "haiku", "sonnet-failed"
    if h_score is None:
        return s_score, s_text, "sonnet", "haiku-failed"
    delta = abs(s_score - h_score)
    consensus = f"sonnet={s_score:.1f} haiku={h_score:.1f} delta={delta:.1f}"
    if delta <= 2:
        return (s_score + h_score) / 2, s_text, "sonnet+haiku", consensus
    em(session, "agent", f"  Evaluator delta={delta:.1f} > 2 — escalating to Opus")
    o_score, o_text = await _run_single_eval(session.workspace, eval_spec, "opus", timeout=180, session_id=sid)
    if o_score is None:
        return (s_score + h_score) / 2, s_text, "sonnet+haiku", f"{consensus} opus-failed"
    weighted = o_score * 0.6 + s_score * 0.3 + h_score * 0.1
    return weighted, o_text, "opus-escalated", f"{consensus} opus={o_score:.1f} weighted={weighted:.1f}"
