import asyncio
import datetime
import json
import os
import shutil
import time
import uuid
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional
from . import config
from . import persistence
from .brief import classify_intent, build_structured_brief
from .lessons import append_lesson, load_lessons
from .supabase_log import log_gate_check

_log = logging.getLogger("pi-ceo.sessions")

# ── Prompt caching (RA-655) ───────────────────────────────────────────────────

_claude_md_cache: Optional[str] = None

# ── Incident history RAG (RA-660) ────────────────────────────────────────────

def _build_incident_context(repo_url: str = "", n: int = 10) -> str:
    """Return a formatted block of recent lessons to prepend to the generator prompt.

    Prioritises warn-severity entries and those whose source matches the current repo.
    Returns empty string when lessons.jsonl doesn't exist or has no entries.
    """
    try:
        all_lessons = load_lessons(limit=50)
    except Exception:
        return ""
    if not all_lessons:
        return ""
    # Prefer entries from the same repo, then most-recent warn entries
    repo_slug = repo_url.rstrip("/").split("/")[-1].lower() if repo_url else ""
    def _rank(e: dict) -> int:
        same_repo = repo_slug and repo_slug in e.get("source", "").lower()
        is_warn = e.get("severity") == "warn"
        return (2 if same_repo else 0) + (1 if is_warn else 0)
    ranked = sorted(all_lessons, key=_rank, reverse=True)[:n]
    # Restore chronological order within the selection
    ranked.sort(key=lambda e: e.get("ts", ""))
    lines = []
    for e in ranked:
        sev = e.get("severity", "info").upper()
        src = e.get("source", "")
        cat = e.get("category", "")
        lesson = e.get("lesson", "")
        lines.append(f"[{sev}] {src}/{cat}: {lesson}")
    return (
        "\n## PRIOR BUILD LESSONS (avoid repeating these mistakes)\n"
        + "\n".join(lines)
        + "\n"
    )


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

# ── SDK metrics ────────────────────────────────────────────────────────────────
_SDK_METRICS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", ".harness", "agent-sdk-metrics"
)


def _write_sdk_metric(
    *,
    session_id: str,
    phase: str,
    model: str,
    success: bool,
    latency_s: float,
    output_len: int,
    error: Optional[str] = None,
) -> None:
    """Append one SDK invocation row to today's JSONL metrics file.

    Non-blocking by design: any I/O error is silently swallowed so metrics
    failures never affect the build pipeline.
    """
    try:
        os.makedirs(_SDK_METRICS_DIR, exist_ok=True)
        today = datetime.date.today().isoformat()
        path = os.path.join(_SDK_METRICS_DIR, f"{today}.jsonl")
        row = json.dumps({
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "session_id": session_id,
            "phase": phase,
            "model": model,
            "sdk_enabled": True,
            "success": success,
            "latency_s": round(latency_s, 3),
            "output_len": output_len,
            "error": error,
        })
        with open(path, "a", encoding="utf-8") as f:
            f.write(row + "\n")
    except Exception:
        pass  # metrics must never break the pipeline

# TAO engine — loaded after brief.py sets up sys.path (project root injected there)
try:
    from src.tao.budget.tracker import BudgetTracker
    from src.tao.tiers.config import load_config as _load_tao_config
    _TAO_AVAILABLE = True
except ImportError:
    _TAO_AVAILABLE = False

def _load_harness_config():
    """Load .harness/config.yaml via TAO TierConfig. Returns dict or None."""
    if not _TAO_AVAILABLE:
        return None
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", ".harness", "config.yaml")
    cfg_path = os.path.abspath(cfg_path)
    try:
        return _load_tao_config(cfg_path) if os.path.isfile(cfg_path) else None
    except Exception:
        return None

_HARNESS_CONFIG = _load_harness_config()


def _send_scope_violation_alert(session, modified_files: list[str], max_files: int) -> None:
    """RA-676 — Fire-and-forget Telegram alert when scope contract is exceeded."""
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_ALERT_CHAT_ID
    if not token or not chat_id:
        return
    repo = (getattr(session, "repo_url", "") or "").rstrip("/").split("/")[-1] or "unknown"
    file_list = "\n".join(f"  • `{f}`" for f in modified_files[:15])
    tail = f"\n  _(+ {len(modified_files) - 15} more)_" if len(modified_files) > 15 else ""
    scope = getattr(session, "scope", None) or {}
    msg = (
        f"🚫 *Scope Contract Violated*\n\n"
        f"Session: `{session.id}`\n"
        f"Repo: `{repo}`\n"
        f"Declared max: *{max_files}* files\n"
        f"Actual: *{len(modified_files)}* files modified\n"
        f"Scope type: `{scope.get('type', 'unspecified')}`\n\n"
        f"Modified files:\n{file_list}{tail}\n\n"
        f"Build held — manual review required."
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
        _log.info("Scope violation alert sent: session=%s files=%d", session.id, len(modified_files))
    except Exception as exc:
        _log.warning("Scope violation Telegram alert failed (non-fatal): %s", exc)


def _check_scope_adherence(
    session,
    modified_files: list[str],
    resolved_intent: str,
) -> bool:
    """RA-676 — Enforce session scope contract. Returns True if scope is violated.

    When a scope contract is set on the session:
      - Counts the files modified by the generator
      - If count > max_files_modified: marks scope_adhered=False, logs lesson,
        fires Telegram alert, sets evaluator_status="scope_violation"
      - If count ≤ max_files_modified: marks scope_adhered=True
    When no scope is declared, returns False without touching session state.
    """
    scope = getattr(session, "scope", None) or {}
    if not scope:
        session.scope_adhered = None
        return False

    max_files = int(scope.get("max_files_modified", 5))
    n = len(modified_files)

    if n <= max_files:
        session.scope_adhered = True
        em(session, "system", f"  Scope: {n}/{max_files} files modified — within contract")
        return False

    # Violation path
    session.scope_adhered = False
    session.evaluator_status = "scope_violation"
    truncated = modified_files[:10]
    overflow  = len(modified_files) - 10
    file_str  = ", ".join(truncated) + (f" (+{overflow} more)" if overflow > 0 else "")
    violation_msg = (
        f"Scope contract violated: {n} files modified "
        f"(max {max_files}, type={scope.get('type', '?')}). Files: {file_str}"
    )
    em(session, "error", f"  {violation_msg}")
    try:
        append_lesson(
            source="evaluator",
            category=resolved_intent,
            lesson=violation_msg,
            severity="warn",
        )
    except Exception:
        pass
    _send_scope_violation_alert(session, modified_files, max_files)
    return True


def _select_model(phase: str, explicit_model: str = "") -> str:
    """Select model for a build phase using harness config.
    phase: 'planner', 'generator', or 'evaluator'.
    Returns short model name (opus/sonnet/haiku)."""
    if explicit_model and explicit_model in config.ALLOWED_MODELS:
        return explicit_model
    if _HARNESS_CONFIG and "agents" in _HARNESS_CONFIG:
        agent_cfg = _HARNESS_CONFIG["agents"].get(phase, {})
        if isinstance(agent_cfg, dict):
            m = agent_cfg.get("model", "")
            if m in config.ALLOWED_MODELS:
                return m
    return "sonnet"


@dataclass
class BuildSession:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    repo_url: str = ""
    workspace: str = ""
    process: Optional[asyncio.subprocess.Process] = None
    started_at: float = 0.0
    status: str = "created"
    output_lines: list = field(default_factory=list)
    error: Optional[str] = None
    evaluator_enabled: bool = True
    evaluator_status: str = "pending"
    evaluator_score: Optional[float] = None
    evaluator_confidence: Optional[float] = None  # RA-674: 0-100% self-reported certainty
    evaluator_model: str = ""       # RA-553: which model(s) produced the score
    evaluator_consensus: str = ""   # RA-553: per-model scores + delta description
    parent_session_id: Optional[str] = None  # RA-464: fan-out parallelism
    budget: Optional[object] = None           # RA-465: BudgetTracker instance
    budget_params: Optional[dict] = None      # RA-677: AUTONOMY_BUDGET computed params
    scope: Optional[dict] = None              # RA-676: session scope contract
    modified_files: list = field(default_factory=list)   # RA-676: git-tracked modified files
    scope_adhered: Optional[bool] = None      # RA-676: None=no scope, True/False=check result
    last_completed_phase: str = ""            # Phase tracking for resume (GROUP D/E)
    retry_count: int = 0                      # Evaluator retry count (GROUP C)
    linear_issue_id: Optional[str] = None    # Linear issue ID for two-way sync

_sessions = {}
def get_session(sid): return _sessions.get(sid)
def list_sessions():
    return [
        {
            "id": s.id,
            "repo": s.repo_url,
            "status": s.status,
            "started": s.started_at,
            "lines": len(s.output_lines),
            "parent": s.parent_session_id,
            "last_phase": s.last_completed_phase,
            "evaluator_score": s.evaluator_score,
            "evaluator_confidence": s.evaluator_confidence,
            "evaluator_model": s.evaluator_model,
            "evaluator_consensus": s.evaluator_consensus,
            "retry_count": s.retry_count,
            "evaluator_status": s.evaluator_status,
            "budget_minutes": (s.budget_params or {}).get("budget_minutes"),
            "scope_adhered": s.scope_adhered,
            "files_modified": len(s.modified_files),
        }
        for s in _sessions.values()
    ]

def restore_sessions():
    """Load persisted sessions from disk on server startup.
    Sessions that were mid-flight (cloning/building) are marked 'interrupted'."""
    count = 0
    for data in persistence.load_all_sessions():
        sid = data.get("id", "")
        if not sid or sid in _sessions:
            continue
        session = BuildSession(
            id=sid,
            repo_url=data.get("repo_url", ""),
            workspace=data.get("workspace", ""),
            started_at=data.get("started_at", 0.0),
            status=data.get("status", "unknown"),
            error=data.get("error"),
            last_completed_phase=data.get("last_completed_phase", ""),
            retry_count=data.get("retry_count", 0),
            linear_issue_id=data.get("linear_issue_id"),
        )
        # Mark anything that was in-flight as interrupted
        if session.status in ("created", "cloning", "building"):
            session.status = "interrupted"
            persistence.save_session(session)
        _sessions[sid] = session
        count += 1
    if count:
        import logging
        logging.getLogger("pi-ceo.sessions").info("Restored %d session(s) from disk.", count)

def em(session, t, d):
    session.output_lines.append({"type":t,"text":d,"ts":time.time()})

async def run_cmd(cwd, *args, timeout=60):
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd)
    out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, out.decode("utf-8",errors="replace"), err.decode("utf-8",errors="replace")

def parse_event(line, session):
    try:
        evt = json.loads(line)
    except Exception:
        if line.strip():
            em(session, "output", line)
        return
    t = evt.get("type","")
    if t == "system":
        m = evt.get("message","")
        if m:
            em(session, "system", f"  {m[:200]}")
    elif t == "assistant":
        msg = evt.get("message",{})
        c = msg.get("content","") if isinstance(msg,dict) else ""
        if isinstance(c, list):
            for b in c:
                if not isinstance(b,dict):
                    continue
                bt = b.get("type","")
                if bt == "text":
                    for ln in b.get("text","").split("\n"):
                        if ln.strip():
                            em(session, "agent", f"  {ln}")
                elif bt == "tool_use":
                    nm = b.get("name","")
                    inp = b.get("input",{})
                    if nm == "Bash":
                        em(session, "tool", f"  $ {inp.get('command','')[:150]}")
                    elif nm in ("Write","Edit"):
                        em(session, "tool", f"  {nm.lower()} {inp.get('file_path','')}")
                    elif nm == "Read":
                        em(session, "tool", f"  read {inp.get('file_path','')}")
                    else:
                        em(session, "tool", f"  {nm}")
    elif t in ("tool_result","result"):
        c = evt.get("content","") or evt.get("result","")
        if isinstance(c,list):
            for b in c:
                if isinstance(b,dict) and b.get("text"):
                    for ln in b["text"].split("\n")[:20]:
                        if ln.strip():
                            em(session, "output", f"    {ln[:200]}")
        elif isinstance(c,str):
            for ln in c.split("\n")[:20]:
                if ln.strip():
                    em(session, "output", f"    {ln[:200]}")
        cost = evt.get("cost_usd")
        if cost:
            em(session, "metric", f"  Cost: ${cost:.4f}")

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


async def _run_claude_via_sdk(
    prompt: str,
    model: str,
    workspace: str,
    timeout: int = 300,
    session_id: str = "",
    phase: str = "",
    thinking: str = "adaptive",
) -> tuple[int, str, float]:
    """Run Claude via agent SDK. Returns (returncode, output_text, cost_usd).

    Uses the same API pattern as board_meeting._run_prompt_via_sdk() (the verified Phase 1
    reference implementation). All standard Claude Code tools (Bash, Edit, Write, etc.) are
    available by default — no allowed_tools restriction so the generator can write files.

    thinking: "adaptive" (default — let Claude decide when to think deeply),
              "enabled" (always think, 8k token budget),
              "disabled" (no extended thinking).

    On any error or import failure, returns (1, "", 0.0) for transparent fallback to subprocess.
    Emits one row to .harness/agent-sdk-metrics/YYYY-MM-DD.jsonl on every invocation.
    """
    try:
        from claude_agent_sdk import (  # noqa: PLC0415
            AssistantMessage,
            ClaudeAgentOptions,
            ClaudeSDKClient,
            ResultMessage,
            TextBlock,
        )
        from claude_agent_sdk.types import (  # noqa: PLC0415
            ThinkingConfigAdaptive,
            ThinkingConfigEnabled,
            ThinkingConfigDisabled,
        )
    except ImportError as exc:
        # RA-576: SDK not installed but USE_AGENT_SDK=1 — deployment misconfiguration.
        # Raise so the operator sees it clearly rather than silently degrading to subprocess.
        _log.error(
            "claude_agent_sdk import failed but USE_AGENT_SDK=1. "
            "Install the package or set USE_AGENT_SDK=0. Error: %s", exc,
        )
        raise RuntimeError(
            "claude_agent_sdk not installed — set USE_AGENT_SDK=0 or run: pip install claude_agent_sdk"
        ) from exc

    # RA-659 — build thinking config
    _thinking_cfg: ThinkingConfigAdaptive | ThinkingConfigEnabled | ThinkingConfigDisabled | None
    if thinking == "adaptive":
        _thinking_cfg = ThinkingConfigAdaptive(type="adaptive")
    elif thinking == "enabled":
        _thinking_cfg = ThinkingConfigEnabled(type="enabled", budget_tokens=8000)
    else:
        _thinking_cfg = ThinkingConfigDisabled(type="disabled")

    t0 = time.monotonic()
    error_msg: Optional[str] = None
    output_text = ""
    try:
        # cwd=workspace so Claude edits files in the right directory.
        # No allowed_tools restriction — generator needs Bash + Edit + Write.
        options = ClaudeAgentOptions(cwd=workspace, model=model, thinking=_thinking_cfg)
        client = ClaudeSDKClient(options)
        text_parts: list[str] = []
        try:
            await client.connect()
            await client.query(prompt)
            async for msg in client.receive_messages():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                elif isinstance(msg, ResultMessage):
                    break
        finally:
            await client.disconnect()
        output_text = "\n".join(text_parts)
        _write_sdk_metric(
            session_id=session_id, phase=phase, model=model,
            success=True, latency_s=time.monotonic() - t0,
            output_len=len(output_text),
        )
        return (0, output_text, 0.0)

    except asyncio.TimeoutError:
        error_msg = f"timeout after {timeout}s"
        _log.warning("SDK generator timed out after %ds", timeout)
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        _log.warning("SDK generator failed: %s (%s)", exc, type(exc).__name__)

    _write_sdk_metric(
        session_id=session_id, phase=phase, model=model,
        success=False, latency_s=time.monotonic() - t0,
        output_len=0, error=error_msg,
    )
    return (1, "", 0.0)


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


_PHASE_ORDER = ["clone", "analyze", "claude_check", "sandbox", "generator", "evaluator", "push"]


def _should_skip(phase: str, resume_from: str) -> bool:
    """Return True if this phase should be skipped (already completed before resume)."""
    if not resume_from:
        return False
    try:
        return _PHASE_ORDER.index(phase) <= _PHASE_ORDER.index(resume_from)
    except ValueError:
        return False


# ── Linear two-way sync helpers ───────────────────────────────────────────────

def _update_linear_state(issue_id: str, state_name: str) -> None:
    """Move a Linear issue to the named workflow state.

    Uses urllib only (no extra dependencies).  Never raises — failures are
    logged and silently swallowed so a Linear outage cannot break a build.

    Algorithm:
      1. Fetch the issue's team ID and current state ID.
      2. List the team's workflow states and find the ID whose name matches
         state_name (case-insensitive).
      3. Call updateIssue mutation with the resolved state ID.
    """
    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        _log.warning("LINEAR_API_KEY not set — cannot update Linear issue %s to '%s'", issue_id, state_name)
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": api_key,
    }

    def _gql(query: str, variables: dict) -> dict:
        payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.linear.app/graphql",
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        # Step 1: get team ID for the issue
        fetch_q = """
query GetIssueTeam($id: String!) {
  issue(id: $id) {
    team { id }
  }
}"""
        result = _gql(fetch_q, {"id": issue_id})
        team_id = (result.get("data") or {}).get("issue", {}).get("team", {}).get("id")
        if not team_id:
            _log.warning("Linear: could not resolve team for issue %s — skipping state update", issue_id)
            return

        # Step 2: find the workflow state ID whose name matches state_name
        states_q = """
query GetTeamStates($teamId: String!) {
  team(id: $teamId) {
    states { nodes { id name type } }
  }
}"""
        result = _gql(states_q, {"teamId": team_id})
        nodes = (result.get("data") or {}).get("team", {}).get("states", {}).get("nodes", [])
        target_id = None
        for node in nodes:
            if node.get("name", "").lower() == state_name.lower():
                target_id = node["id"]
                break
        if not target_id:
            _log.warning(
                "Linear: state '%s' not found in team %s — available: %s",
                state_name, team_id, [n.get("name") for n in nodes],
            )
            return

        # Step 3: update the issue
        mutation = """
mutation UpdateIssueState($id: String!, $stateId: String!) {
  issueUpdate(id: $id, input: { stateId: $stateId }) {
    success
    issue { id title state { name } }
  }
}"""
        result = _gql(mutation, {"id": issue_id, "stateId": target_id})
        success = (result.get("data") or {}).get("issueUpdate", {}).get("success", False)
        if success:
            _log.info("Linear: issue %s moved to '%s'", issue_id, state_name)
        else:
            errors = result.get("errors") or []
            _log.warning("Linear: issueUpdate returned success=false for %s — errors: %s", issue_id, errors)

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        _log.warning("Linear HTTP %s updating issue %s to '%s': %s", exc.code, issue_id, state_name, body)
    except Exception as exc:
        _log.warning("Linear update failed for issue %s to '%s': %s", issue_id, state_name, exc)


def _post_linear_comment(issue_id: str, body: str) -> None:
    """Post a comment to a Linear issue. Never raises — failures are logged and swallowed."""
    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        return
    mutation = """
mutation PostComment($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
  }
}"""
    payload = json.dumps({"query": mutation, "variables": {"issueId": issue_id, "body": body}}).encode()
    req = urllib.request.Request(
        "https://api.linear.app/graphql",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            if not (result.get("data") or {}).get("commentCreate", {}).get("success"):
                _log.warning("Linear: commentCreate returned success=false for issue %s", issue_id)
    except Exception as exc:
        _log.warning("Linear comment failed for issue %s: %s", issue_id, exc)


def _sync_linear_on_completion(session) -> None:
    """RA-665/666 — Post build outcome to Linear on every terminal state.

    Called from run_build() finally block so it fires on success AND all
    early-return failure paths without touching each individual return.
    """
    issue_id = getattr(session, "linear_issue_id", None)
    if not issue_id:
        return
    status = getattr(session, "status", "")
    duration_s = int(time.time() - (session.started_at or time.time()))
    eval_score = getattr(session, "evaluator_score", None)
    eval_status = getattr(session, "evaluator_status", "")

    if status == "complete":
        score_line = f"Evaluator: {eval_score}/10 ({eval_status})\n" if eval_score else ""
        comment = (
            f"Pi CEO build **complete** in {duration_s}s.\n\n"
            f"{score_line}"
            f"Session: `{session.id}`"
        )
        _post_linear_comment(issue_id, comment)
        # Issue already moved to "In Review" during push phase; leave it there
        # so a human can review the PR before marking Done.
    elif status == "failed":
        comment = (
            f"Pi CEO build **failed** after {duration_s}s.\n\n"
            f"Session: `{session.id}` — check Railway logs for details."
        )
        _post_linear_comment(issue_id, comment)
        # Move back to Todo so the issue is visible as needing attention
        _update_linear_state(issue_id, "Todo")
    # killed / other terminal states: no Linear update needed


# ── Phase helpers (RA-529) ────────────────────────────────────────────────────


async def _stream_claude(proc, session):
    """Stream stdout (parsed JSON events) and stderr from a claude subprocess."""
    async def _out(p, s):
        while True:
            line = await p.stdout.readline()
            if not line:
                break
            parse_event(line.decode("utf-8", errors="replace").rstrip(), s)

    async def _err(p, s):
        while True:
            line = await p.stderr.readline()
            if not line:
                break
            t = line.decode("utf-8", errors="replace").rstrip()
            if t and "warn" not in t.lower():
                em(s, "stderr", f"  {t[:200]}")

    await asyncio.gather(_out(proc, session), _err(proc, session))
    await proc.wait()


async def _phase_clone(session, resume_from: str) -> bool:
    if _should_skip("clone", resume_from):
        em(session, "system", "  [SKIP] Clone (already completed)")
        if not session.workspace:
            session.workspace = os.path.join(config.WORKSPACE_ROOT, session.id)
        return True
    em(session, "phase", "[1/5] Cloning repository...")
    session.status = "cloning"
    persistence.save_session(session)
    session.workspace = os.path.join(config.WORKSPACE_ROOT, session.id)
    os.makedirs(session.workspace, exist_ok=True)
    for attempt in range(3):
        try:
            rc, _, stderr = await run_cmd(
                session.workspace, "git", "clone", "--depth", "1",
                session.repo_url, session.workspace, timeout=60,
            )
            if rc == 0:
                em(session, "success", "  Clone complete")
                session.last_completed_phase = "clone"
                persistence.save_session(session)
                return True
            em(session, "error", f"  Clone attempt {attempt + 1}/3 failed: {stderr[:200]}")
        except asyncio.TimeoutError:
            em(session, "error", f"  Clone attempt {attempt + 1}/3 timed out")
        except FileNotFoundError:
            em(session, "error", "  Git not in PATH")
            session.status = "failed"
            persistence.save_session(session)
            return False
        if attempt < 2:
            backoff = 2 * (2 ** attempt)
            em(session, "system", f"  Retrying in {backoff}s...")
            await asyncio.sleep(backoff)
            if os.path.exists(session.workspace):
                shutil.rmtree(session.workspace, ignore_errors=True)
                os.makedirs(session.workspace, exist_ok=True)
    em(session, "error", "  Clone failed after 3 attempts")
    session.status = "failed"
    persistence.save_session(session)
    return False


def _phase_analyze(session, resume_from: str) -> None:
    if _should_skip("analyze", resume_from):
        em(session, "system", "  [SKIP] Analyze (already completed)")
        return
    em(session, "phase", "[2/5] Analyzing workspace...")
    files = [f for f in os.listdir(session.workspace) if not f.startswith(".")]
    em(session, "system", f"  Files: {', '.join(files[:15]) or '(empty)'}")
    session.last_completed_phase = "analyze"
    persistence.save_session(session)


async def _phase_claude_check(session, resume_from: str) -> bool:
    if _should_skip("claude_check", resume_from):
        em(session, "system", "  [SKIP] Claude check (already completed)")
        return True
    em(session, "phase", "[3/5] Checking Claude Code...")
    try:
        rc, out, err = await run_cmd(session.workspace, config.CLAUDE_CMD, "--version", timeout=10)
        if rc == 0:
            em(session, "success", f"  {(out.strip() or err.strip())[:80]}")
            session.last_completed_phase = "claude_check"
            persistence.save_session(session)
            return True
        em(session, "error", "  Claude Code error")
    except FileNotFoundError:
        em(session, "error", "  Claude Code NOT FOUND")
    session.status = "failed"
    persistence.save_session(session)
    return False


async def _phase_sandbox(session, resume_from: str) -> bool:
    if _should_skip("sandbox", resume_from):
        em(session, "system", "  [SKIP] Sandbox (already completed)")
        return True
    em(session, "phase", "[3.5/5] Verifying sandbox...")
    if not session.workspace or not os.path.isdir(session.workspace):
        em(session, "system", "  Sandbox missing — auto-regenerating workspace...")
        session.workspace = os.path.join(config.WORKSPACE_ROOT, session.id)
        os.makedirs(session.workspace, exist_ok=True)
        try:
            proc_reclone = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "1", session.repo_url, session.workspace,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc_reclone.communicate(), timeout=60)
            if proc_reclone.returncode != 0:
                em(session, "error", f"  Sandbox re-clone failed: {stderr.decode()[:200]}")
                session.status = "failed"
                persistence.save_session(session)
                return False
            em(session, "success", "  Sandbox restored via re-clone")
        except Exception as e:
            em(session, "error", f"  Sandbox regeneration error: {e}")
            session.status = "failed"
            persistence.save_session(session)
            return False
    else:
        em(session, "success", f"  Sandbox verified: {session.workspace}")
    session.last_completed_phase = "sandbox"
    persistence.save_session(session)
    return True


async def _phase_generate(session, spec: str, model: str, resume_from: str) -> bool:
    """Run claude CLI; retry once with simplified prompt on failure."""
    em(session, "phase", "[4/5] Running Claude Code (live)...")
    em(session, "system", "")
    session.status = "building"
    persistence.save_session(session)
    use_sdk = config.USE_AGENT_SDK
    # RA-660 — prepend recent institutional memory so generator avoids known pitfalls
    incident_ctx = _build_incident_context(repo_url=getattr(session, "repo_url", ""))
    for attempt in range(2):
        base_spec = spec if attempt == 0 else spec[:4000] + "\n\n[NOTE: Simplified due to previous failure. Focus on core task only.]"
        current_spec = (incident_ctx + base_spec) if incident_ctx else base_spec
        try:
            # Try SDK path first if flag enabled
            if use_sdk:
                em(session, "tool", f"  $ claude --model {model} (via SDK)")
                em(session, "system", "")
                rc, sdk_output, cost = await _run_claude_via_sdk(
                    current_spec, model, session.workspace,
                    session_id=session.id, phase="generator",
                )
                if rc == 0:
                    # SDK succeeded — parse output and emit events
                    for line in sdk_output.split("\n"):
                        if line.strip():
                            parse_event(line, session)
                    em(session, "system", "")
                    em(session, "success", "  Claude Code completed")
                    session.last_completed_phase = "generator"
                    persistence.save_session(session)
                    return True
                else:
                    # RA-576: SDK path required — no subprocess fallback.
                    # Retry with simplified spec on attempt 0; fail on attempt 1.
                    _log.warning("SDK path failed rc=%d (attempt %d/2) — no subprocess fallback", rc, attempt + 1)
                    em(session, "error", f"  SDK failed rc={rc} (attempt {attempt + 1}/2) — no subprocess fallback [RA-576]")
                    if attempt == 0:
                        em(session, "system", "  Retrying with simplified prompt...")
                    continue  # skip subprocess block; proceed to next attempt

            # ── Subprocess path — only reached when USE_AGENT_SDK=0 ──────────
            cmd = [config.CLAUDE_CMD, *config.CLAUDE_EXTRA_FLAGS, "-p", current_spec,
                   "--model", model, "--verbose", "--output-format", "stream-json"]
            em(session, "tool", f"  $ claude --model {model} --verbose --stream-json")
            em(session, "system", "")
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=session.workspace,
            )
            session.process = proc
            await _stream_claude(proc, session)
            em(session, "system", "")
            if proc.returncode == 0:
                em(session, "success", "  Claude Code completed")
                session.last_completed_phase = "generator"
                persistence.save_session(session)
                return True
            em(session, "error", f"  Claude exited code {proc.returncode} (attempt {attempt + 1}/2)")
            if attempt == 0:
                em(session, "system", "  Retrying with simplified prompt...")
        except Exception as e:
            em(session, "error", f"  Error: {e} (attempt {attempt + 1}/2)")
            if attempt > 0:
                break
    em(session, "error", "  Generator failed after 2 attempts")
    session.status = "failed"
    persistence.save_session(session)
    return False


async def _phase_evaluate(session, brief: str, model: str, spec: str, resolved_intent: str) -> int:
    """Run closed-loop evaluator. Returns total_phases (6 if evaluator ran, 5 if skipped)."""
    if not (session.evaluator_enabled and config.EVALUATOR_ENABLED):
        return 5
    total_phases = 6
    # RA-677 — session-level budget params override global config
    _bp = getattr(session, "budget_params", None) or {}
    max_retries = _bp.get("max_retries", config.EVALUATOR_MAX_RETRIES)
    threshold   = _bp.get("eval_threshold", config.EVALUATOR_THRESHOLD)
    if _bp:
        em(session, "system", f"  Budget: {_bp.get('budget_minutes', '?')}min"
           f" → threshold={threshold}/10 retries={max_retries}")
    brief_context = (brief[:2000] + "...") if len(brief) > 2000 else brief
    _EVAL_PROMPT_BASE = (
        "You are a senior code reviewer evaluating AI-generated changes. "
        "Be rigorous — your job is to catch every gap and flaw.\n\n"
        "ORIGINAL BRIEF (what was asked for):\n" + brief_context + "\n\n"
    )
    _EVAL_PROMPT_DIMS = (
        "Grade on 4 dimensions (1-10). Scoring guide:\n"
        "  10 = production-ready, exceeds expectations\n"
        "   9 = complete and correct, minor style preferences only\n"
        "   8 = solid work, 1-2 small gaps or nits\n"
        "   7 = acceptable but missing something meaningful\n"
        "  ≤6 = clear deficiency that must be fixed\n\n"
        "DIMENSION CRITERIA:\n"
        "1. COMPLETENESS \u2014 Does the diff address EVERY requirement in the brief? List any unmet requirements. Partial = ≤6.\n"
        "2. CORRECTNESS \u2014 Any bugs, logic errors, type issues, null refs, security vulnerabilities, or broken tests? One confirmed bug = ≤6.\n"
        "3. CONCISENESS \u2014 Any dead code, debug prints, TODO stubs, or over-engineered abstractions? Tight, purposeful code = 9-10.\n"
        "4. FORMAT \u2014 Does it match the project's existing conventions exactly? Style violations or inconsistent naming = ≤6.\n\n"
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
    # RA-676 — extract modified files and enforce scope contract before eval loop
    try:
        _, _files_out, _ = await run_cmd(
            session.workspace, "git", "diff", "HEAD~1", "--name-only", timeout=10
        )
        session.modified_files = [
            f.strip() for f in (_files_out or "").splitlines() if f.strip()
        ]
    except Exception:
        session.modified_files = []
    if _check_scope_adherence(session, session.modified_files, resolved_intent):
        session.last_completed_phase = "evaluator"
        persistence.save_session(session)
        return total_phases

    for eval_attempt in range(max_retries + 1):
        em(session, "phase", f"[5/{total_phases}] Running Evaluator (attempt {eval_attempt + 1}/{max_retries + 1})...")
        session.status = "evaluating"
        session.evaluator_status = "running"
        session.retry_count = eval_attempt
        persistence.save_session(session)
        try:
            _, diff_out, _ = await run_cmd(session.workspace, "git", "diff", "HEAD~1", "--stat", timeout=10)
            _, diff_full, _ = await run_cmd(session.workspace, "git", "diff", "HEAD~1", timeout=30)
            diff_context = diff_full[:8000] if diff_full else "(no diff available)"
            sid = getattr(session, "id", "")
            # RA-655 — prefer cached direct API path; fall back to Agent SDK on failure
            final_score, eval_text, eval_model, consensus_detail = await _run_parallel_eval_cached(
                session, brief_context, diff_out or "", diff_context, threshold=threshold, sid=sid,
            )
            if eval_model == "":
                # Cached path failed — fall back to Agent SDK path
                _log.info("eval-cache all-failed — falling back to Agent SDK evaluator")
                eval_spec = (
                    _EVAL_PROMPT_BASE
                    + "DIFF SUMMARY:\n" + (diff_out or "(empty)") + "\n\n"
                    + "DIFF DETAIL (truncated to 8000 chars):\n" + diff_context + "\n\n"
                    + _EVAL_PROMPT_DIMS
                )
                final_score, eval_text, eval_model, consensus_detail = await _run_parallel_eval(session, eval_spec)
            session.evaluator_score = final_score
            session.evaluator_model = eval_model
            session.evaluator_consensus = consensus_detail
            # RA-674 — extract and store confidence score
            raw_confidence = _extract_eval_confidence(eval_text)
            session.evaluator_confidence = raw_confidence
            conf_pct = raw_confidence if raw_confidence is not None else 50.0
            for line in eval_text.split("\n"):
                em(session, "agent", f"  {line.strip()[:200]}")
            if session.evaluator_score is None:
                session.evaluator_status = "error"
                em(session, "error", "  Evaluator: could not parse score")
                break
            passed = session.evaluator_score >= threshold
            try:
                dimensions = _parse_evaluator_dimensions(eval_text)
                for dim_name, (score, reason) in dimensions.items():
                    if score < threshold:
                        append_lesson(source="evaluator", category=resolved_intent,
                            lesson=f"{dim_name} scored {score}/10: {reason}",
                            severity="warn" if score < threshold - 1 else "info")
                if not passed:
                    weak = ", ".join(d for d, (s, _) in dimensions.items() if s < threshold)
                    append_lesson(source="evaluator", category=resolved_intent,
                        lesson=f"Build scored {session.evaluator_score}/10 (below {threshold}). Weak: {weak}",
                        severity="warn")
            except Exception:
                pass
            if passed:
                # RA-674 — Three-tier routing based on score + confidence
                if (session.evaluator_score >= config.EVAL_AUTOSHIP_SCORE
                        and conf_pct >= config.EVAL_AUTOSHIP_CONFIDENCE):
                    # Tier 1 — AUTO-SHIP FAST: very high score + high confidence
                    session.evaluator_status = "passed"
                    em(session, "success",
                       f"  Evaluator: {session.evaluator_score:.1f}/10 @ {conf_pct:.0f}%"
                       f" \u2014 AUTO-SHIP FAST")
                elif conf_pct >= config.EVAL_FLAG_CONFIDENCE:
                    # Tier 2 — PASS: meets threshold + adequate confidence
                    session.evaluator_status = "passed"
                    em(session, "success",
                       f"  Evaluator: {session.evaluator_score:.1f}/10 @ {conf_pct:.0f}%"
                       f" \u2014 PASS")
                else:
                    # Tier 3 — LOW CONFIDENCE: passes score gate but operator review needed
                    session.evaluator_status = "passed_low_confidence"
                    em(session, "success",
                       f"  Evaluator: {session.evaluator_score:.1f}/10 @ {conf_pct:.0f}%"
                       f" \u2014 PASS (low confidence \u2014 flagged for review)")
                    _send_low_confidence_alert(session, session.evaluator_score, conf_pct)
                break
            if eval_attempt >= max_retries:
                session.evaluator_status = "warned"
                em(session, "error", f"  Evaluator: {session.evaluator_score}/10 \u2014 BELOW THRESHOLD (exhausted {max_retries + 1} attempts)")
                break
            dimensions = _parse_evaluator_dimensions(eval_text)
            weak_dims = [f"{d}: {s}/10 \u2014 {r}" for d, (s, r) in dimensions.items() if s < threshold]
            retry_brief = (
                spec + "\n\n--- RETRY INSTRUCTIONS ---\n"
                f"Previous attempt scored {session.evaluator_score}/10 (threshold: {threshold}).\n"
                "Issues found:\n" + "\n".join(f"- {w}" for w in weak_dims) + "\n"
                "Fix these specific issues. Do not rewrite everything.\n--- END RETRY ---"
            )
            em(session, "error", f"  Evaluator: {session.evaluator_score}/10 \u2014 RETRYING")
            em(session, "phase", f"[4/{total_phases}] Re-running Claude Code (retry {eval_attempt + 1})...")
            session.status = "building"
            persistence.save_session(session)

            # Try SDK path first if flag enabled (same pattern as _phase_generate)
            use_sdk = config.USE_AGENT_SDK
            retry_success = False
            if use_sdk:
                em(session, "tool", f"  $ claude --model {model} (via SDK, retry)")
                em(session, "system", "")
                rc, sdk_output, cost = await _run_claude_via_sdk(
                    retry_brief, model, session.workspace,
                    session_id=session.id, phase="generator_retry",
                )
                if rc == 0:
                    # SDK succeeded — parse output and emit events
                    for line in sdk_output.split("\n"):
                        if line.strip():
                            parse_event(line, session)
                    em(session, "system", "")
                    em(session, "success", "  Retry generation complete")
                    retry_success = True
                else:
                    # RA-576: SDK retry required — no subprocess fallback.
                    _log.warning("SDK retry failed rc=%d — aborting evaluator retry [RA-576]", rc)
                    em(session, "error", f"  SDK retry failed rc={rc} — no subprocess fallback [RA-576]")
                    break

            # ── Subprocess retry path — only reached when USE_AGENT_SDK=0 ──
            if not use_sdk and not retry_success:
                retry_cmd = [config.CLAUDE_CMD, *config.CLAUDE_EXTRA_FLAGS, "-p", retry_brief,
                             "--model", model, "--verbose", "--output-format", "stream-json"]
                retry_proc = await asyncio.create_subprocess_exec(
                    *retry_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=session.workspace,
                )
                session.process = retry_proc
                await _stream_claude(retry_proc, session)
                await retry_proc.wait()
                if retry_proc.returncode != 0:
                    em(session, "error", "  Retry generation failed")
                    break
                em(session, "success", "  Retry generation complete")
        except asyncio.TimeoutError:
            session.evaluator_status = "timeout"
            em(session, "error", "  Evaluator timed out (120s)")
            break
        except Exception as e:
            session.evaluator_status = "error"
            em(session, "error", f"  Evaluator error: {e}")
            break
    session.last_completed_phase = "evaluator"
    persistence.save_session(session)
    return total_phases


async def _phase_push(session, total_phases: int) -> tuple[list[str], bool]:
    """Commit uncommitted changes, push to GitHub. Returns (all-files, push_ok)."""
    em(session, "phase", f"[{total_phases}/{total_phases}] Pushing to GitHub...")
    af: list[str] = []
    try:
        rc, out, _ = await run_cmd(session.workspace, "git", "status", "--porcelain")
        if out.strip():
            await run_cmd(session.workspace, "git", "add", "-A")
            await run_cmd(session.workspace, "git", "commit", "-m", "feat: Pi CEO build")
        _, out, _ = await run_cmd(session.workspace, "git", "log", "--oneline", "-10")
        commits = [ln.strip() for ln in out.strip().split("\n") if ln.strip()]
        push_ok = False
        if commits:
            for c in commits:
                em(session, "system", f"  {c}")
            em(session, "system", f"  Pushing {len(commits)} commits...")
            push_ok = False
            for push_attempt in range(3):
                rc, _, err = await run_cmd(session.workspace, "git", "push", "origin", "HEAD", timeout=30)
                if rc == 0:
                    push_ok = True
                    em(session, "success", "  Pushed to GitHub!")
                    em(session, "success", "  https://github.com/CleanExpo/Pi-Dev-Ops")
                    break
                err_lower = err.lower()
                if any(s in err_lower for s in ("authentication failed", "could not read username", "permission denied", "403", "401")):
                    em(session, "error", f"  Push auth error (not retrying): {err[:200]}")
                    break
                em(session, "error", f"  Push attempt {push_attempt + 1}/3 failed: {err[:200]}")
                if push_attempt < 2:
                    backoff = 2 * (2 ** push_attempt)
                    em(session, "system", f"  Retrying push in {backoff}s...")
                    await asyncio.sleep(backoff)
            if not push_ok:
                em(session, "error", "  Push failed — changes committed locally, push manually")
        em(session, "system", "")
        em(session, "phase", "  Project structure:")
        for r, dirs, fns in os.walk(session.workspace):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", "workspaces")]
            for fn in fns:
                af.append(os.path.relpath(os.path.join(r, fn), session.workspace))
        for x in sorted(af)[:30]:
            em(session, "system", f"    {x}")
        if len(af) > 30:
            em(session, "system", f"    ...+{len(af) - 30} more")
    except Exception as e:
        em(session, "error", f"  Push error: {e}")
        return af, False
    return af, push_ok


# ── Orchestrator ──────────────────────────────────────────────────────────────


async def run_build(session, brief="", model="sonnet", intent="", resume_from=""):
    em(session, "phase", "  Pi CEO Solo DevOps Tool")
    em(session, "system", f"  Session: {session.id}")
    em(session, "system", f"  Repo:    {session.repo_url}")
    em(session, "system", f"  Model:   {model}")
    if resume_from:
        em(session, "system", f"  Resuming from: {resume_from}")
    if _TAO_AVAILABLE:
        total_budget = (_HARNESS_CONFIG or {}).get("total_token_budget", 100000)
        session.budget = BudgetTracker(total_budget=total_budget)
        em(session, "system", f"  TAO:     budget={total_budget:,} tokens | config={'loaded' if _HARNESS_CONFIG else 'default'}")
    em(session, "system", "")

    if not await _phase_clone(session, resume_from):
        _sync_linear_on_completion(session)
        return
    _phase_analyze(session, resume_from)
    if not await _phase_claude_check(session, resume_from):
        _sync_linear_on_completion(session)
        return
    if not await _phase_sandbox(session, resume_from):
        _sync_linear_on_completion(session)
        return

    if not brief:
        brief = "Analyze this codebase fully. Read every skill in skills/. Read the engine in src/tao/. Produce a detailed analysis in .harness/spec.md. Suggest improvements. Git commit changes."
    resolved_intent = intent or classify_intent(brief)
    em(session, "system", f"  Intent: {resolved_intent.upper()}")
    spec = build_structured_brief(brief, resolved_intent, session.repo_url, session.workspace)

    if not await _phase_generate(session, spec, model, resume_from):
        _sync_linear_on_completion(session)
        return
    total_phases = await _phase_evaluate(session, brief, model, spec, resolved_intent)
    push_ts = time.time()
    af, push_ok = await _phase_push(session, total_phases)

    session.last_completed_phase = "push"
    session.status = "complete"
    persistence.save_session(session)

    # RA-656: log gate_check row — fire-and-forget, never blocks pipeline
    try:
        spec_exists = os.path.isfile(os.path.join(session.workspace, ".harness", "spec.md"))
        plan_exists = os.path.isfile(os.path.join(session.workspace, ".harness", "plan.md"))
        # RA-674: passed_low_confidence is a passing state (score gate cleared)
        # RA-676: scope_violation is NOT a passing state
        review_passed = getattr(session, "evaluator_status", "") in (
            "passed", "passed_low_confidence"
        )
        review_score = float(session.evaluator_score or 0)
        log_gate_check(
            pipeline_id=session.id,
            session_id=session.id,
            gate_checks={
                "spec_exists":    spec_exists,
                "plan_exists":    plan_exists,
                "build_complete": True,   # reached here only if generate succeeded
                "tests_passed":   True,   # reached here only if sandbox succeeded
                "review_passed":  review_passed,
            },
            review_score=review_score,
            shipped=push_ok,
            session_started_at=session.started_at,   # RA-672: C3 mean time to value
            push_timestamp=push_ts if push_ok else None,
            confidence=session.evaluator_confidence,  # RA-674: log to Supabase
            scope_adhered=session.scope_adhered,      # RA-676: scope contract result
            files_modified=len(session.modified_files),  # RA-676: modified file count
        )
    except Exception:
        pass  # observability must never block the pipeline

    # Two-way Linear sync: move issue to "In Review" now that the build is pushed
    if session.linear_issue_id:
        em(session, "system", f"  Updating Linear issue {session.linear_issue_id} → In Review")
        _update_linear_state(session.linear_issue_id, "In Review")

    em(session, "system", "")
    em(session, "phase", "  Summary")
    em(session, "system", f"    Duration: {time.time() - session.started_at:.0f}s")
    em(session, "system", f"    Files: {len(af)}")
    em(session, "success", "  === SESSION COMPLETE ===")

    # RA-665/666 — post outcome comment to Linear now build is fully complete
    try:
        _sync_linear_on_completion(session)
    except Exception:
        pass  # Linear sync must never crash the build pipeline

async def create_session(
    repo_url,
    brief="",
    model="",
    evaluator_enabled=True,
    intent="",
    parent_session_id="",
    linear_issue_id: Optional[str] = None,
    budget_minutes: Optional[int] = None,
    scope: Optional[dict] = None,
):
    """Create and start a new build session.

    RA-677: when budget_minutes is provided, auto-tunes eval_threshold,
    max_retries, model, and generator timeout via budget.budget_to_params().
    Per-request budget_minutes overrides TAO_AUTONOMY_BUDGET global default.

    RA-676: when scope is provided ({type, primary_file?, max_files_modified?}),
    the evaluator enforces a file-count ceiling and fires a Telegram alert on
    violation.  Default max_files_modified = 5.
    """
    if len(_sessions) >= config.MAX_CONCURRENT_SESSIONS:
        raise RuntimeError("Max sessions reached")
    resolved_model = _select_model("generator", model)
    # RA-677 — apply AUTONOMY_BUDGET if specified
    bp: Optional[dict] = None
    if budget_minutes and budget_minutes > 0:
        from .budget import budget_to_params, describe_budget  # noqa: PLC0415
        bp = budget_to_params(budget_minutes)
        resolved_model = bp["model"]
        _log.info("AUTONOMY_BUDGET applied: %s", describe_budget(bp))
    session = BuildSession(
        repo_url=repo_url,
        started_at=time.time(),
        evaluator_enabled=evaluator_enabled,
        parent_session_id=parent_session_id or None,
        linear_issue_id=linear_issue_id or None,
        budget_params=bp,
        scope=scope or None,
    )
    if scope:
        _log.info(
            "Scope contract set: session=%s type=%s max_files=%s",
            session.id, scope.get("type", "?"), scope.get("max_files_modified", 5),
        )
    _sessions[session.id] = session
    persistence.save_session(session)
    asyncio.create_task(run_build(session, brief, resolved_model, intent=intent))
    return session

async def kill_session(sid):
    s = _sessions.get(sid)
    if not s or not s.process:
        return False
    try:
        s.process.terminate()
        await asyncio.sleep(2)
        if s.process.returncode is None:
            s.process.kill()
        s.status = "killed"
        persistence.save_session(s)
        em(s, "error", "Killed by user")
        return True
    except Exception:
        return False

def cleanup_session(sid):
    s = _sessions.pop(sid, None)
    if s and s.workspace and os.path.exists(s.workspace):
        shutil.rmtree(s.workspace, ignore_errors=True)
    persistence.delete_session_file(sid)
