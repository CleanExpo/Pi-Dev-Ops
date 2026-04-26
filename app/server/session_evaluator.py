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
from .session_model import em, _sessions
from .session_sdk import _write_sdk_metric, _run_claude_via_sdk

_log = logging.getLogger("pi-ceo.session_evaluator")


# ── Budget tracking (RA-1682) ─────────────────────────────────────────────────
def _record_evaluator_tokens(
    session_id: str, model: str, input_tokens: int, output_tokens: int
) -> None:
    """Record evaluator token usage on the session's BudgetTracker.

    RA-1682 — `session.budget` was instantiated in session_phases._phase_plan
    (line 1447) but never received a single `.record()` call, so the tracker
    always reported `used=0` regardless of real spend. This helper closes the
    gap on the evaluator hot path: every direct-API eval round contributes
    its actual usage, scoped by model name (sonnet / haiku / opus).

    Quietly no-ops when:
      - session_id is empty (eg. one-off probe / standalone test invocation)
      - the session has been GC'd between request and response
      - `session.budget` is None (only happens for sessions that bypassed
        the plan phase entirely — uncommon, but graceful is correct)
    """
    if not session_id:
        return
    session = _sessions.get(session_id)
    if session is None:
        return
    budget = getattr(session, "budget", None)
    if budget is None:
        return
    try:
        budget.record(model, int(input_tokens) + int(output_tokens))
    except Exception as exc:  # noqa: BLE001
        # Budget recording must never break the evaluator. Log once + move on.
        _log.warning("budget.record(%s) failed: %s", model, exc)

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
    """Parse evaluator dimension scores from output text.

    Returns {dimension_name: (score, reason)}.

    Dimensions: completeness, correctness, conciseness, format, and
    karpathy (5th axis — surgical/simple/goal-verified/assumption-surfaced).
    Karpathy is a *soft* axis: it is returned here for lesson capture but
    callers intentionally do not gate merge on it alone (see session_phases
    lesson-append loop and pass/fail logic).
    """
    dimensions = {}
    for line in eval_text.split("\n"):
        line_upper = line.strip().upper()
        for dim in ("COMPLETENESS", "CORRECTNESS", "CONCISENESS", "FORMAT", "KARPATHY"):
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

    try:
        from tenacity import (  # noqa: PLC0415
            retry,
            stop_after_attempt,
            wait_random_exponential,
            retry_if_exception,
            before_sleep_log,
        )
        _HAS_TENACITY = True
    except ImportError:
        _HAS_TENACITY = False

    api_key = config.ANTHROPIC_API_KEY
    if not api_key:
        return None, ""

    _MODEL_IDS = {
        "opus": "claude-opus-4-7",
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
        "Style violations or inconsistent naming = \u22646.\n"
        "5. KARPATHY ADHERENCE \u2014 Score the four Karpathy principles together "
        "(CLAUDE.md lines 184\u2013246):\n"
        "   \u2022 Surgical: every changed line traces to the brief\n"
        "   \u2022 Simple: minimum code, no speculative abstractions\n"
        "   \u2022 Goal-verified: tests/checks defined before implementation\n"
        "   \u2022 Assumption-surfaced: assumptions stated upfront, not silently chosen\n"
        "   10 = all four honoured; \u22645 if any principle is violated. "
        "Soft axis: reported for learning, not a merge blocker on its own.\n\n"
        "OUTPUT FORMAT: Respond with exactly 5 dimension lines, the overall, then a confidence line:\n"
        "COMPLETENESS: <score>/10 \u2014 <reason>\n"
        "CORRECTNESS: <score>/10 \u2014 <reason>\n"
        "CONCISENESS: <score>/10 \u2014 <reason>\n"
        "FORMAT: <score>/10 \u2014 <reason>\n"
        "KARPATHY: <score>/10 \u2014 <reason>\n"
        f"OVERALL: <average of first 4>/10 \u2014 PASS or FAIL (threshold: {threshold}/10)\n"
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
        client = _anthropic.Anthropic(api_key=api_key, max_retries=0)

        # RA-925: count_tokens dynamic budget guard — prevent silent truncation
        desired_output = 512
        safe_max_tokens = desired_output
        try:
            tc = client.messages.count_tokens(
                model=full_model,
                system=system_blocks,
                messages=[{"role": "user", "content": user_content}],
            )
            safe_max_tokens = min(desired_output, 200_000 - tc.input_tokens - 500)
            _log.debug("eval count_tokens: input=%d safe_max=%d", tc.input_tokens, safe_max_tokens)
        except Exception as _ct_exc:
            _log.debug("count_tokens unavailable (%s), using desired_output=%d", _ct_exc, desired_output)

        def _create_with_retry():
            if _HAS_TENACITY:
                from anthropic import RateLimitError, APITimeoutError, APIStatusError  # noqa: PLC0415

                def _is_transient(exc):
                    if isinstance(exc, APIStatusError):
                        return exc.status_code in (429, 500, 502, 503, 529)
                    return isinstance(exc, (RateLimitError, APITimeoutError))

                @retry(
                    retry=retry_if_exception(_is_transient),
                    wait=wait_random_exponential(multiplier=2, min=4, max=60),
                    stop=stop_after_attempt(4),
                    before_sleep=before_sleep_log(_log, logging.WARNING),
                )
                def _inner():
                    return client.messages.create(
                        model=full_model,
                        max_tokens=max(64, safe_max_tokens),
                        system=system_blocks,
                        messages=[{"role": "user", "content": user_content}],
                        timeout=timeout,
                    )
                return _inner()
            else:
                return client.messages.create(
                    model=full_model,
                    max_tokens=max(64, safe_max_tokens),
                    system=system_blocks,
                    messages=[{"role": "user", "content": user_content}],
                    timeout=timeout,
                )

        message = _create_with_retry()
        text = message.content[0].text if message.content else ""
        usage = message.usage
        _input_tokens = getattr(usage, "input_tokens", 0)
        _output_tokens = getattr(usage, "output_tokens", 0)
        _log.info(
            "eval-cache model=%s input=%d cache_write=%d cache_read=%d output=%d latency=%.1fs",
            model,
            _input_tokens,
            getattr(usage, "cache_creation_input_tokens", 0),
            getattr(usage, "cache_read_input_tokens", 0),
            _output_tokens,
            time.monotonic() - t0,
        )
        # RA-1682: feed the session's BudgetTracker. Without this the tracker
        # is dead weight — instantiated but `used` stays 0 forever.
        _record_evaluator_tokens(session_id, model, _input_tokens, _output_tokens)
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
    # RA-1099: evaluator role cannot use Opus; average sonnet+haiku regardless of delta.
    return (s_score + h_score) / 2, s_text, "sonnet+haiku(cached)", consensus


# ── SDK / subprocess evaluator runners ────────────────────────────────────────

async def _run_single_eval(
    workspace: str,
    eval_spec: str,
    model: str,
    timeout: int = 120,
    session_id: str = "",
) -> tuple[Optional[float], str]:
    """Run one evaluator pass via the Agent SDK.

    Returns (score_or_None, full_output_text). RA-1094B: SDK-only mandate —
    the subprocess fallback was removed.
    """
    rc, sdk_text, _ = await _run_claude_via_sdk(
        eval_spec, model, workspace, timeout=timeout,
        session_id=session_id, phase="evaluator",
    )
    if rc == 0 and sdk_text.strip():
        return _extract_eval_score(sdk_text), sdk_text
    _log.warning("SDK evaluator failed rc=%d", rc)
    return None, ""


async def _run_persona_review(session, workspace_path: str) -> list[dict]:
    """RA-1027 — Run 4 review personas in parallel and return structured JSON findings.

    Each persona runs a Haiku SDK call against the brief + a compact diff/file listing.
    Results are merged, fingerprint-deduplicated (confidence boosted on consensus),
    filtered (confidence < 0.55 dropped), and sorted high → medium → low.

    Returns [] when the API key is missing, all persona calls fail, or workspace has no diff.
    """
    try:
        import anthropic as _anthropic  # noqa: PLC0415
    except ImportError:
        _log.debug("persona review: anthropic not installed — skipping")
        return []

    api_key = config.ANTHROPIC_API_KEY
    if not api_key:
        _log.debug("persona review: ANTHROPIC_API_KEY missing — skipping")
        return []

    _HAIKU = "claude-haiku-4-5-20251001"
    _SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

    _PERSONAS: list[tuple[str, str]] = [
        (
            "correctness",
            "You review code for logical errors, off-by-one errors, wrong assumptions, and runtime "
            "exceptions. Focus on whether the implementation actually does what the brief requires. "
            "Be specific: name the file, approximate line, and describe the bug clearly.",
        ),
        (
            "testing",
            "You review code for test coverage. Check whether happy paths, edge cases, and error "
            "paths are tested. Flag untested code paths and missing assertions. Be specific: name "
            "the file and the missing scenario.",
        ),
        (
            "scope",
            "You review code for scope creep. Check whether the implementation adds code not "
            "required by the brief, modifies files outside the stated scope, or introduces "
            "unnecessary abstractions. Flag anything that goes beyond the stated requirements.",
        ),
        (
            "standards",
            "You review code for project standards. Check commit message format, naming "
            "conventions, import ordering, and whether the code matches the style of the "
            "surrounding codebase. Flag deviations from established patterns.",
        ),
    ]

    # ── Gather diff context (compact, under 4000 chars total) ────────────────
    try:
        diff_stat_proc = await asyncio.create_subprocess_exec(
            "git", "diff", "HEAD~1", "--stat",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=workspace_path,
        )
        stat_out, _ = await asyncio.wait_for(diff_stat_proc.communicate(), timeout=10)
        diff_stat = stat_out.decode("utf-8", errors="replace").strip()
    except Exception as _e:
        _log.debug("persona review: git diff --stat failed: %s", _e)
        diff_stat = ""

    # Read up to 3 most-changed files (by line count in stat output)
    changed_files: list[str] = []
    try:
        for line in diff_stat.splitlines():
            # stat lines: "  path/to/file.py | 42 +++..."
            if "|" in line and not line.strip().startswith("git diff"):
                parts = line.split("|")
                if len(parts) >= 2:
                    fname = parts[0].strip()
                    if fname:
                        changed_files.append(fname)
        changed_files = changed_files[:3]
    except Exception:
        changed_files = []

    file_snippets: list[str] = []
    total_chars = len(diff_stat)
    for fname in changed_files:
        if total_chars >= 3800:
            break
        try:
            fpath = os.path.join(workspace_path, fname)
            with open(fpath, encoding="utf-8", errors="replace") as fh:
                content = fh.read(800)
            snippet = f"### {fname}\n```\n{content}\n```"
            file_snippets.append(snippet)
            total_chars += len(snippet)
        except Exception:
            pass

    brief_text = getattr(session, "_brief_context_for_persona", "") or ""
    diff_context = (
        f"DIFF STAT:\n{diff_stat}\n\n"
        + ("\n\n".join(file_snippets) if file_snippets else "")
    )[:4000]

    _JSON_INSTRUCTION = (
        "\n\nReturn ONLY a JSON array. No prose, no markdown fences, no explanation.\n"
        "Format: [{\"file\": \"path/to/file.py\", \"line\": 42, \"issue\": \"...\", "
        "\"severity\": \"high|medium|low\", \"confidence\": 0.0}]\n"
        "Return [] if you find no issues."
    )

    # ── Per-persona Haiku call ────────────────────────────────────────────────
    async def _call_persona(name: str, system_prompt: str) -> tuple[str, list[dict]]:
        t0 = time.monotonic()
        user_msg = (
            (f"BRIEF:\n{brief_text}\n\n" if brief_text else "")
            + diff_context
            + _JSON_INSTRUCTION
        )
        try:
            client = _anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)
            message = await client.messages.create(
                model=_HAIKU,
                max_tokens=512,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
                timeout=60,
            )
            raw = message.content[0].text if message.content else "[]"
            _log.debug("persona=%s latency=%.1fs raw=%s", name, time.monotonic() - t0, raw[:120])
            findings: list[dict] = json.loads(raw)
            if not isinstance(findings, list):
                findings = []
            return name, findings
        except json.JSONDecodeError as jex:
            _log.warning("persona=%s JSON parse failed: %s — returning []", name, jex)
            return name, []
        except Exception as exc:
            _log.warning("persona=%s call failed: %s — returning []", name, exc)
            return name, []

    # ── Run all 4 in parallel ─────────────────────────────────────────────────
    results: list[tuple[str, list[dict]]] = list(
        await asyncio.gather(*[_call_persona(name, prompt) for name, prompt in _PERSONAS])
    )

    # ── Merge + fingerprint boost ─────────────────────────────────────────────
    fingerprint_count: dict[tuple, int] = {}
    all_findings: list[dict] = []

    for persona_name, findings in results:
        for f in findings:
            if not isinstance(f, dict):
                continue
            # Normalise required fields
            f.setdefault("file", "unknown")
            f.setdefault("line", 0)
            f.setdefault("issue", "")
            sev = str(f.get("severity", "low")).lower()
            if sev not in _SEVERITY_ORDER:
                sev = "low"
            f["severity"] = sev
            try:
                conf = float(f.get("confidence", 0.7))
                conf = max(0.0, min(1.0, conf))
            except (TypeError, ValueError):
                conf = 0.7
            f["confidence"] = conf
            f["persona"] = persona_name

            fp = (f["file"], sev, f["issue"][:40])
            fingerprint_count[fp] = fingerprint_count.get(fp, 0) + 1
            all_findings.append(f)

    # Apply confidence boost for consensus (2+ personas flagged same fingerprint)
    for f in all_findings:
        fp = (f["file"], f["severity"], f["issue"][:40])
        if fingerprint_count.get(fp, 0) >= 2:
            f["confidence"] = min(1.0, f["confidence"] + 0.15)

    # Filter low-confidence findings
    filtered = [f for f in all_findings if f["confidence"] >= 0.55]

    # Sort: high → medium → low
    filtered.sort(key=lambda f: _SEVERITY_ORDER.get(f["severity"], 2))

    _log.info(
        "persona review: %d raw findings → %d after filter (session=%s)",
        len(all_findings), len(filtered), getattr(session, "id", ""),
    )
    return filtered


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
    # RA-1099: evaluator role is not in OPUS_ALLOWED_ROLES, so the prior
    # delta>2 escalation to Opus violated model policy. Average sonnet+haiku
    # regardless of delta; the consensus field still records the disagreement.
    return (s_score + h_score) / 2, s_text, "sonnet+haiku", consensus
