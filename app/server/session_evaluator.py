"""
session_evaluator.py — Evaluator logic for Pi-CEO build sessions.

Extracted from sessions.py (RA-890). Contains all score parsing, confidence
extraction, alert dispatching, and the three evaluator runners:

  - _parse_evaluator_dimensions()  — parse 4 dimension scores from eval output
  - _extract_eval_score()          — parse OVERALL: <n>/10
  - _extract_eval_confidence()     — parse CONFIDENCE: <pct>%
  - _send_low_confidence_alert()   — fire-and-forget Telegram alert (RA-674)
  - _get_claude_md()               — lazy-load CLAUDE.md for prompt caching (RA-655)
  - _run_eval_with_cache()         — provider-routed eval pass
  - _run_parallel_eval_cached()    — parallel provider-routed eval passes
  - _run_single_eval()             — single provider-routed eval pass
  - _run_parallel_eval()           — parallel provider-routed consensus eval

Import graph:
  session_evaluator  →  session_sdk  (for _write_sdk_metric)
  session_evaluator  →  provider_router (for configured model/provider routing)
  session_evaluator  →  session_model (for em, BuildSession)
  session_evaluator  →  config

Public API (re-exported by sessions.py for backward compatibility):
  All nine functions above.
"""

from __future__ import annotations

from .evaluation_prompt import _evaluation_criteria
import asyncio
import json
import logging
import math
import os
import time
import urllib.request
from typing import Optional

from . import config
from .session_model import em, _sessions
from .session_sdk import _write_sdk_metric
from .provider_router import run_via_provider, run_via_provider_with_evidence
from .provider_policy import independent_identity

_log = logging.getLogger("pi-ceo.session_evaluator")


# ── Budget tracking (RA-1682) ─────────────────────────────────────────────────
def _record_evaluator_tokens(
    session_id: str, model: str, input_tokens: int, output_tokens: int
) -> None:
    """Record evaluator token usage on the session's BudgetTracker.

    RA-1682 — `session.budget` was instantiated in session_phases._phase_plan
    (line 1447) but never received a single `.record()` call, so the tracker
    always reported `used=0` regardless of real spend. This helper closes the
    gap on the evaluator hot path: provider-routed eval rounds can contribute
    usage when token counts are available, scoped by evaluator label.

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
                score = float(line.split(":")[1].strip().split("/")[0].strip())
                return score if math.isfinite(score) and 0 <= score <= 10 else None
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
                return val if math.isfinite(val) and 0 <= val <= 100 else None
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
    evidence: Optional[list] = None,
) -> tuple[Optional[float], str]:
    """Run one evaluator pass through the configured provider router.

    This function used to call Anthropic's Messages API directly for prompt
    caching. After the OpenRouter/Kimi production switch, Anthropic-first calls
    are a liability: they fail before the configured provider gets a chance to
    run. Keep the public function name for backward compatibility, but route the
    prompt through ``provider_router.run_via_provider(role="evaluator")`` so
    Railway env overrides decide the actual provider/model.
    """
    eval_criteria = _evaluation_criteria(threshold)

    claude_md = _get_claude_md()
    prompt = (
        ("PROJECT CONTEXT (CLAUDE.md):\n" + claude_md + "\n\n" if claude_md else "")
        + "EVALUATION CRITERIA:\n"
        + eval_criteria
        + "\n\nORIGINAL BRIEF (what was asked for):\n"
        + brief_context
        + "\n\nDIFF SUMMARY:\n"
        + (diff_out or "(empty)")
        + "\n\nCANDIDATE DIFF:\n"
        + diff_context
    )

    t0 = time.monotonic()
    try:
        execution = await run_via_provider_with_evidence(
            prompt,
            role="evaluator_secondary" if model == "haiku" else "evaluator",
            task_class=f"cached-{model}",
            timeout_s=timeout,
            session_id=session_id,
        )
        rc, text, cost, error = execution.rc, execution.text, execution.cost_usd, execution.error
        if evidence is not None:
            evidence.append({**execution.provenance, "rc": rc, "score": _extract_eval_score(text) if rc == 0 else None})
        success = rc == 0 and bool((text or "").strip())
        _log.info(
            "eval-provider role_label=%s rc=%s cost=%s latency=%.1fs",
            model,
            rc,
            cost if cost is not None else "unverified",
            time.monotonic() - t0,
        )
        _write_sdk_metric(
            session_id=session_id, phase=f"evaluator_provider_{model}",
            model=execution.provenance.get("actual_model") or "unverified", success=success,
            latency_s=time.monotonic() - t0, output_len=len(text or ""),
            error=error or "" if not success else "",
        )
        if not success:
            _log.warning("eval-provider model=%s failed: %s", model, error or f"rc={rc}")
            return None, ""
        return _extract_eval_score(text), text
    except Exception as exc:
        _log.warning("eval-provider model=%s raised: %s — will fall back", model, exc)
        _write_sdk_metric(
            session_id=session_id, phase=f"evaluator_provider_{model}",
            model=model, success=False,
            latency_s=time.monotonic() - t0, output_len=0, error=str(exc),
        )
        return None, ""


def _insufficient_confidence(texts):
    return any(
        (confidence := _extract_eval_confidence(text)) is None
        or confidence < config.EVAL_FLAG_CONFIDENCE for text in texts
    )


async def _run_parallel_eval_cached(
    session,
    brief_context: str,
    diff_out: str,
    diff_context: str,
    threshold: int,
    sid: str = "",
) -> tuple[Optional[float], str, str, str]:
    """Require two independently identified reviewers; missing evidence blocks consensus."""
    em(session, "tool", "  Independent required evaluator roles [parallel]")
    primary_evidence: list[dict] = []
    secondary_evidence: list[dict] = []
    kwargs = dict(
        brief_context=brief_context,
        diff_out=diff_out,
        diff_context=diff_context,
        threshold=threshold,
        session_id=sid,
    )
    (s_score, s_text), (h_score, h_text) = await asyncio.gather(
        _run_eval_with_cache(model="sonnet", evidence=primary_evidence, **kwargs),
        _run_eval_with_cache(model="haiku", evidence=secondary_evidence, **kwargs),
    )
    session.audit_evidence = [
        {**item, "candidate_sha": getattr(session, "candidate_sha", "")}
        for item in primary_evidence + secondary_evidence
    ]
    label = "+".join(f"{item.get('provider', 'unknown')}:{item.get('actual_model') or 'unverified'}" for item in session.audit_evidence) or "unverified"
    if s_score is None or h_score is None:
        return None, s_text + "\n" + h_text, label, "required reviewer failed"
    if len(primary_evidence) != 1 or len(secondary_evidence) != 1 or not independent_identity(primary_evidence[0], secondary_evidence[0]):
        return None, s_text + "\n" + h_text, label, "independent model identity not verified"
    if _insufficient_confidence((s_text, h_text)):
        return None, s_text + "\n" + h_text, label, "required reviewer confidence insufficient"
    delta = abs(s_score - h_score)
    consensus = f"primary={s_score:.1f} secondary={h_score:.1f} delta={delta:.1f}"
    if delta > 2 or (s_score >= threshold) != (h_score >= threshold):
        return None, s_text + "\n" + h_text, label, "reviewer disagreement: " + consensus
    lower_text = s_text if s_score <= h_score else h_text
    return min(s_score, h_score), lower_text, label, consensus


# ── SDK / subprocess evaluator runners ────────────────────────────────────────

async def _run_single_eval(
    workspace: str,
    eval_spec: str,
    model: str,
    timeout: int = 120,
    session_id: str = "",
) -> tuple[Optional[float], str]:
    """Run one evaluator pass through the configured provider router.

    ``model`` remains a consensus label (historically sonnet/haiku). The actual
    provider/model is selected by Railway env through ``provider_router`` so the
    evaluator honours OpenRouter/Kimi overrides instead of hard-wiring Anthropic.
    """
    rc, text, _cost, error = await run_via_provider(
        eval_spec,
        role="evaluator",
        task_class=f"single-{model}",
        timeout_s=timeout,
        workspace=workspace,
        session_id=session_id,
    )
    if rc == 0 and text.strip():
        return _extract_eval_score(text), text
    _log.warning("provider evaluator failed model_label=%s rc=%d error=%s", model, rc, error)
    return None, ""


async def _run_persona_review(session, workspace_path: str) -> list[dict]:
    """RA-1027 — Run 4 review personas in parallel and return structured JSON findings.

    Each persona runs a Haiku SDK call against the brief + a compact diff/file listing.
    Results are merged, fingerprint-deduplicated (confidence boosted on consensus),
    filtered (confidence < 0.55 dropped), and sorted high → medium → low.

    Returns [] when the API key is missing, all persona calls fail, or workspace has no diff.
    """
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
            prompt = (
                "PERSONA SYSTEM INSTRUCTIONS:\n"
                + system_prompt
                + "\n\nUSER REVIEW CONTEXT:\n"
                + user_msg
            )
            rc, raw, _cost, error = await run_via_provider(
                prompt,
                role="evaluator",
                task_class=f"persona-{name}",
                timeout_s=60,
                workspace=workspace_path,
                session_id=getattr(session, "id", ""),
            )
            if rc != 0 or not (raw or "").strip():
                _log.warning(
                    "persona=%s provider call failed rc=%s error=%s — returning []",
                    name,
                    rc,
                    error,
                )
                return name, []
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
    """Compatibility entry point using the same mandatory evidence contract."""
    return await _run_parallel_eval_cached(
        session, eval_spec, "", "", threshold=config.EVALUATOR_THRESHOLD,
        sid=getattr(session, "id", ""),
    )
