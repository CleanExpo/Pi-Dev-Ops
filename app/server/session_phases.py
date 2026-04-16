"""session_phases.py — Build phase pipeline for Pi-CEO sessions.

Extracted from sessions.py (RA-890). Contains the complete build pipeline:
utilities, all _phase_* functions, and run_build().

Import graph (dependencies):
  session_phases  →  session_model  (BuildSession, _sessions, em)
  session_phases  →  session_sdk    (_run_claude_via_sdk, _emit_sdk_canary_metric)
  session_phases  →  session_evaluator (_parse_evaluator_dimensions, etc.)
  session_phases  →  session_linear (_update_linear_state, etc.)
  session_phases  →  config, persistence, brief, lessons, supabase_log

Public API (re-exported by sessions.py for backward compatibility):
  run_cmd, parse_event, run_build
  _build_incident_context, _select_model, _HARNESS_CONFIG, _TAO_AVAILABLE
  _phase_clone, _phase_analyze, _phase_claude_check, _phase_sandbox,
  _phase_generate, _phase_evaluate, _phase_push
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from . import config
from . import persistence
from .brief import classify_intent, build_structured_brief, scan_repo_context
from .lessons import append_lesson, load_lessons, extract_lesson_from_eval, append_lesson_dedup
from .supabase_log import log_gate_check
from .session_recorder import record_episode, retrieve_similar_episodes, format_episodes_as_context
from .session_model import em
from .session_sdk import _run_claude_via_sdk, _emit_sdk_canary_metric
from .session_evaluator import (
    _parse_evaluator_dimensions,
    _extract_eval_confidence,
    _send_low_confidence_alert,
    _run_parallel_eval,
    _run_parallel_eval_cached,
    _run_persona_review,
)
from .session_linear import (
    _update_linear_state,
    _record_session_outcome,
    _sync_linear_on_completion,
)

_log = logging.getLogger("pi-ceo.sessions")

# ── RA-932: Think-block cold-start seeds ─────────────────────────────────────
# Prepend structural prompts before the model enters extended reasoning.
# Active when THINK_SEED_ENABLED=1 in env (default off until validated).
_THINK_SEED_ENABLED = os.environ.get("THINK_SEED_ENABLED", "0") == "1"

GENERATOR_THINK_SEED = (
    "Before editing any files:\n"
    "1. Which files need to change? List them.\n"
    "2. What is the minimal diff that satisfies the brief?\n"
    "3. Which tests need updating?\n"
    "4. What side-effects could this change have?\n\n"
)

EVALUATOR_THINK_SEED = (
    "Before scoring:\n"
    "1. List every requirement from the brief.\n"
    "2. Check each requirement against the diff. Note gaps.\n"
    "3. Identify any bugs, type errors, or logic issues.\n"
    "4. Check project conventions.\n\n"
)

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


# ── RA-934: 4-file task memory ────────────────────────────────────────────────

async def _write_task_memory(session, brief: str, spec: str) -> None:
    """Write PROMPT/PLAN/IMPLEMENT.md to .pi-ceo/{session_id}/ in the workspace.

    These files become the cross-session working memory passed to every agent
    invocation.  STATUS.md is created empty for the generator to populate.
    Never raises — task memory failure must not block the build pipeline.
    """
    from pathlib import Path  # noqa: PLC0415
    try:
        pi_dir = Path(session.workspace) / ".pi-ceo" / session.id
        pi_dir.mkdir(parents=True, exist_ok=True)
        (pi_dir / "PROMPT.md").write_text(
            f"# Task Brief\n\n{brief}\n\n## Session: {session.id}\n",
            encoding="utf-8",
        )
        (pi_dir / "PLAN.md").write_text(
            f"# Implementation Plan\n\n{spec}\n",
            encoding="utf-8",
        )
        (pi_dir / "STATUS.md").write_text(
            f"# Status Log\n\n_Session {session.id} — update after each milestone._\n",
            encoding="utf-8",
        )
        impl_template = Path(__file__).parent / "templates" / "IMPLEMENT.md"
        if impl_template.exists():
            shutil.copy(impl_template, pi_dir / "IMPLEMENT.md")
        _log.info("RA-934: task memory written to %s", pi_dir)
    except Exception as exc:
        _log.warning("RA-934: _write_task_memory failed (non-fatal): %s", exc)


# ── RA-936: Structured repair loop helpers ────────────────────────────────────

async def _classify_failure(eval_text: str, diff_text: str, session) -> dict:
    """Use Haiku to classify the evaluator failure and determine minimal repair scope.

    Returns a dict with: FAILURE_TYPE, IMPLICATED_FILES, REPAIR_SCOPE,
    REPAIR_INSTRUCTIONS.  Returns {} on any error — caller falls back to
    the legacy retry_brief format.
    """
    haiku_model = getattr(config, "HAIKU_MODEL", "claude-haiku-4-5")
    classification_prompt = (
        "You are a code repair classifier. Analyse the evaluator output and diff, "
        "then classify the failure concisely.\n\n"
        f"EVALUATOR OUTPUT:\n{eval_text[:2000]}\n\n"
        f"GIT DIFF SUMMARY:\n{diff_text[:1000]}\n\n"
        "Respond in JSON only (no markdown fences):\n"
        "{\n"
        '  "FAILURE_TYPE": "test_failure|lint_error|type_error|logic_error|incomplete|scope_violation",\n'
        '  "IMPLICATED_FILES": ["list", "of", "file", "paths"],\n'
        '  "REPAIR_SCOPE": "minimal|moderate|full_rewrite",\n'
        '  "REPAIR_INSTRUCTIONS": ["step 1", "step 2", "step 3"]\n'
        "}"
    )
    try:
        rc, text, _ = await _run_claude_via_sdk(
            classification_prompt, haiku_model, session.workspace,
            timeout=45, session_id=session.id, phase="repair_classifier",
        )
        if rc == 0 and text.strip():
            # Strip any accidental markdown fences
            clean = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            return json.loads(clean)
    except Exception as exc:
        _log.debug("RA-936: _classify_failure error (non-fatal): %s", exc)
    return {}


def _build_repair_brief(
    spec: str,
    eval_text: str,
    classification: dict,
    threshold: float,
    weak_dims: list[str],
) -> str:
    """Build a targeted repair brief from the failure classification.

    Falls back to the legacy retry format when classification is empty.
    """
    if not classification:
        # Legacy format (existing behaviour preserved)
        return (
            spec + "\n\n--- RETRY INSTRUCTIONS ---\n"
            f"Previous attempt scored below threshold ({threshold}/10).\n"
            "Issues found:\n" + "\n".join(f"- {w}" for w in weak_dims) + "\n"
            "Fix these specific issues. Do not rewrite everything.\n--- END RETRY ---"
        )
    failure_type = classification.get("FAILURE_TYPE", "unknown")
    implicated = classification.get("IMPLICATED_FILES", [])
    scope = classification.get("REPAIR_SCOPE", "minimal")
    instructions = classification.get("REPAIR_INSTRUCTIONS", [])

    files_line = ", ".join(implicated) if implicated else "see evaluator output"
    instructions_text = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(instructions))

    return (
        f"REPAIR TASK — failure type: {failure_type}, scope: {scope}\n\n"
        f"Do NOT rewrite everything. Touch only the implicated files: {files_line}\n\n"
        f"Original task spec:\n{spec[:1500]}\n\n"
        f"Evaluator feedback:\n{eval_text[:1500]}\n\n"
        f"Specific repair instructions:\n{instructions_text or '  - Fix the issues described in the evaluator feedback above'}\n\n"
        "Verify your changes with a quick test run if tests exist.\n"
        "Do not modify files not in the implicated list."
    )


def _send_repair_exhausted_alert(session, score: float, eval_text: str) -> None:
    """RA-936 — Telegram alert when the repair loop exhausts all retries.

    Lets the operator know a session needs human review rather than silently
    being marked 'warned'. Never raises.
    """
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_ALERT_CHAT_ID
    if not token or not chat_id:
        return
    repo = getattr(session, "repo_url", "?").rstrip("/").split("/")[-1]
    issue_id = getattr(session, "linear_issue_id", None)
    ticket = f" | {issue_id}" if issue_id else ""
    # Pull first failing dimension from eval text for the alert
    failing_dim = ""
    for line in eval_text.splitlines():
        if any(d in line for d in ("COMPLETENESS:", "CORRECTNESS:", "CONCISENESS:", "FORMAT:")):
            if "/10" in line:
                try:
                    score_val = float(line.split("/10")[0].split()[-1])
                    if score_val < 7:
                        failing_dim = line.strip()[:80]
                        break
                except ValueError:
                    pass
    msg = (
        f"🔄 *Repair loop exhausted:* `{repo}`\n"
        f"Score: {score:.1f}/10 — needs human review{ticket}\n"
        f"{failing_dim}"
    )
    payload = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "Markdown",
                          "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        _log.debug("RA-936: _send_repair_exhausted_alert failed (non-fatal): %s", exc)


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


# ── RA-1032: Per-phase cost/duration metric helper ────────────────────────────

def _emit_phase_metric(session, phase_name: str, phase_start: float, phase_cost: float = 0.0) -> None:
    """Append a phase_metric event to session.output_lines (never raises)."""
    try:
        duration_s = round(time.monotonic() - phase_start, 1)
        session.phase_metrics[phase_name] = {"duration_s": duration_s, "cost_usd": phase_cost}
        session.output_lines.append({
            "type": "phase_metric",
            "phase": phase_name,
            "duration_s": duration_s,
            "cost_usd": phase_cost,
            "ts": time.time(),
            "text": f"  {phase_name}: {duration_s}s · ${phase_cost:.4f}",
        })
    except Exception:
        pass  # metric tracking must never break a phase


_PHASE_ORDER = ["clone", "analyze", "claude_check", "sandbox", "plan", "generator", "evaluator", "push"]


def _should_skip(phase: str, resume_from: str) -> bool:
    """Return True if this phase should be skipped (already completed before resume)."""
    if not resume_from:
        return False
    try:
        return _PHASE_ORDER.index(phase) <= _PHASE_ORDER.index(resume_from)
    except ValueError:
        return False


# ── Phase helpers (RA-529) ────────────────────────────────────────────────────


# RA-1094B — _stream_claude() removed. SDK-only mandate: no more claude CLI
# subprocess, so no need to parse its stream-json output.


async def _phase_clone(session, resume_from: str) -> bool:
    phase_start = time.monotonic()
    if _should_skip("clone", resume_from):
        em(session, "system", "  [SKIP] Clone (already completed)")
        if not session.workspace:
            session.workspace = os.path.join(config.WORKSPACE_ROOT, session.id)
        return True

    # RA-1029: use git worktree if this is a worker session with a shared parent workspace
    if session.shared_workspace and session.parent_session_id:
        branch_name = f"worker-{session.id[:8]}"
        worktree_path = Path(session.shared_workspace).parent / session.id
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", session.shared_workspace, "worktree", "add",
                 str(worktree_path), "-b", branch_name],
                capture_output=True, text=True,
            )
        except Exception as exc:
            _log.warning("Worktree creation raised exception, falling back to full clone: %s", exc)
            result = None
        if result is not None and result.returncode == 0:
            session.workspace = str(worktree_path)
            session.status = "cloning"
            session.last_completed_phase = "clone"
            em(session, "success", "  Using git worktree (skipped network clone)")
            persistence.save_session(session)
            _emit_phase_metric(session, "clone", phase_start)
            return True
        stderr_msg = result.stderr.strip() if result is not None else "exception"
        _log.warning("Worktree creation failed, falling back to full clone: %s", stderr_msg)

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
                _emit_phase_metric(session, "clone", phase_start)
                return True
            em(session, "error", f"  Clone attempt {attempt + 1}/3 failed: {stderr[:200]}")
        except asyncio.TimeoutError:
            em(session, "error", f"  Clone attempt {attempt + 1}/3 timed out")
        except FileNotFoundError:
            em(session, "error", "  Git not in PATH")
            session.status = "failed"
            persistence.save_session(session)
            _emit_phase_metric(session, "clone", phase_start)
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
    _emit_phase_metric(session, "clone", phase_start)
    return False


def _phase_analyze(session, resume_from: str) -> None:
    phase_start = time.monotonic()
    if _should_skip("analyze", resume_from):
        em(session, "system", "  [SKIP] Analyze (already completed)")
        return
    em(session, "phase", "[2/5] Analyzing workspace...")
    files = [f for f in os.listdir(session.workspace) if not f.startswith(".")]
    em(session, "system", f"  Files: {', '.join(files[:15]) or '(empty)'}")
    # RA-1025 — grounded repo scan: detect language, test framework, CI commands
    try:
        repo_ctx = scan_repo_context(str(session.workspace))
        session.repo_context = repo_ctx
        em(session, "system", (
            f"  Repo context: lang={repo_ctx['primary_language']} "
            f"test={repo_ctx['test_framework']} "
            f"has_claude_md={repo_ctx['has_claude_md']}"
        ))
    except Exception:
        session.repo_context = {}  # never block the pipeline
    session.last_completed_phase = "analyze"
    persistence.save_session(session)
    _emit_phase_metric(session, "analyze", phase_start)


async def _phase_claude_check(session, resume_from: str) -> bool:
    if _should_skip("claude_check", resume_from):
        em(session, "system", "  [SKIP] Claude check (already completed)")
        return True
    em(session, "phase", "[3/5] Checking Claude Code...")

    # SDK-only path (RA-1094B). The subprocess `claude --version` fallback was
    # removed — the Agent SDK is the only supported execution path.
    try:
        import claude_agent_sdk as _sdk  # noqa: PLC0415
        version = getattr(_sdk, "__version__", "installed")
        em(session, "success", f"  claude_agent_sdk {version} (SDK mode)")
        session.last_completed_phase = "claude_check"
        persistence.save_session(session)
        return True
    except ImportError:
        em(session, "error", "  claude_agent_sdk not installed — required by SDK-only mandate (RA-1094B)")
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


async def _phase_plan(session, spec: str, resume_from: str) -> None:
    """RA-1026 — Lightweight Haiku planning phase between sandbox and generator.

    Converts the structured brief into a JSON implementation plan with up to 8
    units, then writes it to .pi-ceo/{session_id}/PLAN.md and attaches a
    markdown summary to session.plan.

    Never blocks the pipeline: any error is logged and the function returns
    without setting session.status = "failed".
    """
    phase_start = time.monotonic()
    if _should_skip("plan", resume_from):
        em(session, "system", "  [SKIP] Plan (already completed)")
        return

    em(session, "phase", "[3.7/5] Planning implementation (haiku)...")
    haiku_model = getattr(config, "HAIKU_MODEL", "haiku")

    repo_context_snippet = ""
    if session.workspace and os.path.isdir(session.workspace):
        try:
            files = [
                f for f in os.listdir(session.workspace)
                if not f.startswith(".") and f not in ("node_modules", "__pycache__")
            ]
            repo_context_snippet = "Top-level files: " + ", ".join(sorted(files)[:20])
        except Exception:
            pass

    planning_prompt = (
        "You are a planning agent. Convert this brief into a structured implementation plan.\n\n"
        f"Brief:\n{spec[:3000]}\n\n"
        f"Repo context: {repo_context_snippet or 'not available'}\n\n"
        "Output a JSON object (no markdown fences):\n"
        "{\n"
        '  "units": [\n'
        "    {\n"
        '      "id": 1,\n'
        '      "title": "...",\n'
        '      "files": ["path/to/file.py"],\n'
        '      "test_scenarios": ["happy path: ...", "edge case: ..."],\n'
        '      "is_behavioral": true\n'
        "    }\n"
        "  ],\n"
        '  "confidence": 0.0,\n'
        '  "risk_notes": "..."\n'
        "}\n\n"
        "Rules:\n"
        "- 3-8 units maximum\n"
        "- Be specific about file paths\n"
        "- For non-behavioral units (config, scaffolding) set is_behavioral: false "
        "and omit test_scenarios\n"
        "- confidence is 0.0-1.0 (your certainty this plan fully covers the brief)\n"
        "- Respond with JSON only — no explanation, no markdown fences"
    )

    try:
        rc, plan_text, _ = await asyncio.wait_for(
            _run_claude_via_sdk(
                planning_prompt, haiku_model, session.workspace,
                timeout=45, session_id=session.id, phase="planner",
            ),
            timeout=50,
        )
    except asyncio.TimeoutError:
        _log.warning("RA-1026: _phase_plan timed out (non-fatal) — continuing without plan")
        em(session, "system", "  Plan phase timed out — continuing without plan")
        session.last_completed_phase = "plan"
        persistence.save_session(session)
        _emit_phase_metric(session, "plan", phase_start)
        return
    except Exception as exc:
        _log.warning("RA-1026: _phase_plan error (non-fatal): %s", exc)
        em(session, "system", f"  Plan phase error — continuing without plan: {exc}")
        session.last_completed_phase = "plan"
        persistence.save_session(session)
        _emit_phase_metric(session, "plan", phase_start)
        return

    if rc != 0 or not plan_text.strip():
        _log.warning("RA-1026: planner returned rc=%d or empty text — continuing without plan", rc)
        em(session, "system", "  Plan phase returned no output — continuing without plan")
        session.last_completed_phase = "plan"
        persistence.save_session(session)
        _emit_phase_metric(session, "plan", phase_start)
        return

    # Parse JSON — strip accidental markdown fences if the model added them
    plan_data: dict = {}
    try:
        clean = plan_text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        plan_data = json.loads(clean)
    except Exception as exc:
        _log.warning("RA-1026: plan JSON parse failed (non-fatal): %s — raw: %.200s", exc, plan_text)
        em(session, "system", "  Plan JSON parse failed — continuing without structured plan")
        session.last_completed_phase = "plan"
        persistence.save_session(session)
        _emit_phase_metric(session, "plan", phase_start)
        return

    # Confidence gate — warn but never block
    confidence = float(plan_data.get("confidence", 1.0))
    if confidence < 0.7:
        _log.warning(
            "RA-1026: plan confidence=%.2f < 0.7 for session=%s — proceeding with low-confidence plan",
            confidence, session.id,
        )
        em(session, "system", f"  Plan confidence low ({confidence:.0%}) — proceeding with caution")

    # Build markdown summary for session.plan and PLAN.md
    units = plan_data.get("units", [])
    risk_notes = plan_data.get("risk_notes", "")

    md_lines = [
        "# Implementation Plan\n",
        f"**Session:** {session.id}  ",
        f"**Confidence:** {confidence:.0%}",
        "",
    ]
    if risk_notes:
        md_lines += [f"**Risk notes:** {risk_notes}", ""]

    for unit in units:
        uid = unit.get("id", "?")
        title = unit.get("title", "Untitled")
        files = unit.get("files", [])
        scenarios = unit.get("test_scenarios", [])
        is_behavioral = unit.get("is_behavioral", True)

        md_lines.append(f"## Unit {uid}: {title}")
        if files:
            md_lines.append("**Files:** " + ", ".join(f"`{f}`" for f in files))
        if is_behavioral and scenarios:
            md_lines.append("**Test scenarios:**")
            for s in scenarios:
                md_lines.append(f"  - {s}")
        md_lines.append("")

    plan_md = "\n".join(md_lines)

    # Write PLAN.md to .pi-ceo/{session_id}/ (create dirs if needed)
    try:
        from pathlib import Path  # noqa: PLC0415
        pi_dir = Path(session.workspace) / ".pi-ceo" / session.id
        pi_dir.mkdir(parents=True, exist_ok=True)
        plan_path = pi_dir / "PLAN.md"
        plan_path.write_text(plan_md, encoding="utf-8")
        _log.info(
            "RA-1026: plan written to %s (%d units, confidence=%.2f)",
            plan_path, len(units), confidence,
        )
        em(session, "system", f"  Plan: {len(units)} unit(s) written → .pi-ceo/{session.id}/PLAN.md")
    except Exception as exc:
        _log.warning("RA-1026: PLAN.md write failed (non-fatal): %s", exc)

    # Attach plan to session for generator injection
    session.plan = plan_md
    session.last_completed_phase = "plan"
    persistence.save_session(session)
    _emit_phase_metric(session, "plan", phase_start)
    em(session, "success", "  Plan phase complete")


async def _phase_generate(session, spec: str, model: str, resume_from: str) -> bool:
    """Run claude CLI; retry once with simplified prompt on failure."""
    phase_start = time.monotonic()
    _generate_cost: float = 0.0
    em(session, "phase", "[4/5] Running Claude Code (live)...")
    em(session, "system", "")
    session.status = "building"
    persistence.save_session(session)
    # RA-697: canary routing — route a fraction of requests through the canary path.
    # TODO: when a distinct canary SDK variant/endpoint is available, wire it here
    # instead of sharing the same _run_claude_via_sdk call signature.
    use_canary = (
        getattr(config, "AGENT_SDK_CANARY_RATE", 0.0) > 0
        and random.random() < getattr(config, "AGENT_SDK_CANARY_RATE", 0.0)
    )
    if use_canary:
        _log.info(
            "Session %s: canary path selected (rate=%.2f)",
            session.id, config.AGENT_SDK_CANARY_RATE,
        )
    # RA-1094B — SDK-only mandate: subprocess generator path removed.
    # RA-660 — prepend recent institutional memory so generator avoids known pitfalls
    incident_ctx = _build_incident_context(repo_url=getattr(session, "repo_url", ""))
    for attempt in range(2):
        base_spec = spec if attempt == 0 else spec[:4000] + "\n\n[NOTE: Simplified due to previous failure. Focus on core task only.]"
        # RA-932: prepend generator think seed when enabled
        seeded_spec = (GENERATOR_THINK_SEED + base_spec) if _THINK_SEED_ENABLED else base_spec
        current_spec = (incident_ctx + seeded_spec) if incident_ctx else seeded_spec
        try:
            em(session, "tool", f"  $ claude --model {model} (via SDK)")
            em(session, "system", "")
            rc, sdk_output, cost = await _run_claude_via_sdk(
                current_spec, model, session.workspace,
                session_id=session.id, phase="generator",
            )
            _generate_cost += float(cost or 0.0)
            if rc == 0:
                for line in sdk_output.split("\n"):
                    if line.strip():
                        parse_event(line, session)
                em(session, "system", "")
                em(session, "success", "  Claude Code completed")
                session.last_completed_phase = "generator"
                persistence.save_session(session)
                _emit_phase_metric(session, "generate", phase_start, _generate_cost)
                # RA-697: emit canary metric on successful canary run
                if use_canary:
                    _emit_sdk_canary_metric(session.id, success=True)
                return True
            _log.warning("SDK generator failed rc=%d (attempt %d/2)", rc, attempt + 1)
            em(session, "error", f"  SDK failed rc={rc} (attempt {attempt + 1}/2)")
            if attempt == 0:
                em(session, "system", "  Retrying with simplified prompt...")
        except Exception as e:
            em(session, "error", f"  Error: {e} (attempt {attempt + 1}/2)")
            if attempt > 0:
                break
    em(session, "error", "  Generator failed after 2 attempts")
    session.status = "failed"
    persistence.save_session(session)
    _emit_phase_metric(session, "generate", phase_start, _generate_cost)
    return False


async def _phase_evaluate(session, brief: str, model: str, spec: str, resolved_intent: str) -> int:
    """Run closed-loop evaluator. Returns total_phases (6 if evaluator ran, 5 if skipped)."""
    phase_start = time.monotonic()
    _evaluate_cost: float = 0.0
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
    # RA-1027 — stash brief so _run_persona_review can include it in persona prompts
    session._brief_context_for_persona = brief_context
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
        "4. FORMAT \u2014 Does it match the project's existing conventions exactly? Style violations or inconsistent naming = ≤6.\n"
        "5. KARPATHY ADHERENCE \u2014 Score the four Karpathy principles together "
        "(CLAUDE.md lines 184\u2013246):\n"
        "   \u2022 Surgical: every changed line traces to the brief\n"
        "   \u2022 Simple: minimum code, no speculative abstractions\n"
        "   \u2022 Goal-verified: tests/checks defined before implementation\n"
        "   \u2022 Assumption-surfaced: assumptions stated upfront, not silently chosen\n"
        "   10 = all four honoured; ≤5 if any principle is violated. "
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
                    + "ORIGINAL BRIEF (what was asked for):\n" + brief_context + "\n\n"
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
            # Karpathy is a *soft* axis (CLAUDE.md lines 184–246): it feeds
            # lessons but does not block merge on its own. OVERALL comes from the
            # evaluator (average of the 4 hard axes); karpathy failures surface
            # as lessons so operators can tighten the gate later without a
            # regression risk today.
            passed = session.evaluator_score >= threshold
            try:
                dimensions = _parse_evaluator_dimensions(eval_text)
                for dim_name, (score, reason) in dimensions.items():
                    if score < threshold:
                        lesson_category = "karpathy" if dim_name == "karpathy" else resolved_intent
                        append_lesson(source="evaluator", category=lesson_category,
                            lesson=f"{dim_name} scored {score}/10: {reason}",
                            severity="warn" if score < threshold - 1 else "info")
                if not passed:
                    weak = ", ".join(d for d, (s, _) in dimensions.items() if s < threshold)
                    append_lesson(source="evaluator", category=resolved_intent,
                        lesson=f"Build scored {session.evaluator_score}/10 (below {threshold}). Weak: {weak}",
                        severity="warn")
            except Exception:
                pass
            # RA-1028 — auto-extract structured lesson from evaluator output
            try:
                extracted = extract_lesson_from_eval(
                    session.brief or "",
                    eval_text,
                    session.evaluator_score or 0.0,
                )
                if extracted:
                    append_lesson_dedup(
                        extracted["text"],
                        category=extracted["category"],
                        repo=getattr(session, "repo_url", "") or "",
                        severity=extracted.get("severity", "info"),
                    )
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
                _send_repair_exhausted_alert(session, session.evaluator_score, eval_text)  # RA-936
                break
            dimensions = _parse_evaluator_dimensions(eval_text)
            weak_dims = [f"{d}: {s}/10 \u2014 {r}" for d, (s, r) in dimensions.items() if s < threshold]
            # RA-936: fast failure classification before targeted repair
            em(session, "system", "  Classifying failure (haiku)\u2026")
            classification = await _classify_failure(eval_text, diff_full or "", session)
            retry_brief = _build_repair_brief(spec, eval_text, classification, threshold, weak_dims)
            em(session, "error", f"  Evaluator: {session.evaluator_score}/10 \u2014 RETRYING")
            em(session, "phase", f"[4/{total_phases}] Re-running Claude Code (retry {eval_attempt + 1})...")
            session.status = "building"
            persistence.save_session(session)

            # RA-1094B — SDK-only mandate: subprocess retry path removed.
            em(session, "tool", f"  $ claude --model {model} (via SDK, retry)")
            em(session, "system", "")
            rc, sdk_output, cost = await _run_claude_via_sdk(
                retry_brief, model, session.workspace,
                session_id=session.id, phase="generator_retry",
            )
            if rc != 0:
                _log.warning("SDK retry failed rc=%d — aborting evaluator retry", rc)
                em(session, "error", f"  SDK retry failed rc={rc}")
                break
            for line in sdk_output.split("\n"):
                if line.strip():
                    parse_event(line, session)
            em(session, "system", "")
            em(session, "success", "  Retry generation complete")
        except asyncio.TimeoutError:
            session.evaluator_status = "timeout"
            em(session, "error", "  Evaluator timed out (120s)")
            break
        except Exception as e:
            session.evaluator_status = "error"
            em(session, "error", f"  Evaluator error: {e}")
            break
    # RA-1027 — run multi-persona parallel review and emit structured findings
    try:
        findings = await _run_persona_review(session, session.workspace)
        session.evaluator_findings = findings
        if findings:
            import time as _time  # noqa: PLC0415
            session.output_lines.append({
                "type": "evaluator_findings",
                "findings": findings,
                "ts": _time.time(),
            })
            em(session, "system", f"  Persona review: {len(findings)} finding(s) (RA-1027)")
    except Exception as _pf_exc:
        _log.warning("persona review failed (non-fatal): %s", _pf_exc)
    session.last_completed_phase = "evaluator"
    persistence.save_session(session)
    _emit_phase_metric(session, "evaluate", phase_start, _evaluate_cost)
    return total_phases


async def _phase_push(session, total_phases: int) -> tuple[list[str], bool]:
    """Commit uncommitted changes, push to GitHub on a feature branch. Returns (all-files, push_ok)."""
    phase_start = time.monotonic()
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
            # ── Embed GITHUB_TOKEN in remote URL for authenticated push ──
            github_token = os.environ.get("GITHUB_TOKEN", "")
            if github_token:
                try:
                    _, ru, _ = await run_cmd(session.workspace, "git", "remote", "get-url", "origin", timeout=5)
                    ru = ru.strip()
                    if "github.com" in ru and "@" not in ru:
                        authed = ru.replace("https://github.com/", f"https://x-access-token:{github_token}@github.com/")
                        await run_cmd(session.workspace, "git", "remote", "set-url", "origin", authed.strip(), timeout=5)
                        em(session, "system", "  Remote: authenticated via GITHUB_TOKEN")
                except Exception as _auth_err:
                    em(session, "system", f"  Remote auth setup warning: {_auth_err}")
            # ── Push to a feature branch (not main) ──
            sid_short = getattr(session, "id", "auto")[:8]
            branch_name = f"pidev/auto-{sid_short}"
            await run_cmd(session.workspace, "git", "checkout", "-b", branch_name, timeout=10)
            em(session, "system", f"  Pushing {len(commits)} commits on branch {branch_name}...")
            for push_attempt in range(3):
                rc, _, err = await run_cmd(session.workspace, "git", "push", "origin", branch_name, timeout=30)
                if rc == 0:
                    push_ok = True
                    em(session, "success", f"  Pushed to GitHub! Branch: {branch_name}")
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
        _emit_phase_metric(session, "push", phase_start)
        return af, False
    _emit_phase_metric(session, "push", phase_start)
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
    # RA-681 — resolve brief complexity tier (explicit override or auto-detect)
    from .brief import classify_brief_complexity  # noqa: PLC0415
    resolved_tier = session.complexity_tier or classify_brief_complexity(brief)
    em(session, "system", f"  Brief tier: {resolved_tier.upper()}")

    # RA-931 — inject verified past episodes as context before spec construction
    _similar_episodes: list = []
    try:
        _similar_episodes = await retrieve_similar_episodes(brief, session.repo_url)
        if _similar_episodes:
            em(session, "system", f"  Context replay: {len(_similar_episodes)} similar past episode(s) found")
    except Exception:
        pass  # never block the pipeline

    spec = build_structured_brief(
        brief, resolved_intent, session.repo_url, session.workspace,
        complexity_tier=resolved_tier,
        repo_context=getattr(session, "repo_context", None) or None,
    )
    # RA-931 — prepend verified past episodes to spec for context replay
    if _similar_episodes:
        episode_ctx = format_episodes_as_context(_similar_episodes)
        spec = episode_ctx + "\n\n" + spec

    # RA-679 — optional plan variation discovery (generates 3 approaches, picks best)
    if getattr(session, "plan_discovery", False):
        try:
            from .agents.plan_discovery import discover_best_plan  # noqa: PLC0415
            em(session, "phase", "[3.5/5] Plan Discovery (3 variants, haiku)...")
            spec, meta = await discover_best_plan(brief, spec, session_id=session.id)
            session.plan_discovery_meta = meta
            if meta:
                em(session, "system",
                   f"  Plan Discovery: variant {meta['winner']} won "
                   f"({meta['winner_score']:.1f}/10) in {meta['duration_s']}s")
        except Exception as _disc_exc:
            _log.warning("plan_discovery hook failed (non-fatal): %s", _disc_exc)

    # RA-934 — write cross-session task memory files to workspace before generation
    await _write_task_memory(session, brief, spec)
    em(session, "system", f"  Task memory: .pi-ceo/{session.id}/PLAN.md written")

    # RA-1026 — structured planning phase (haiku) before generator
    await _phase_plan(session, spec, resume_from)
    if session.plan:
        plan_header = (
            "## Implementation Plan (pre-computed)\n"
            f"{session.plan}\n\n"
            "Follow this plan. Implement each unit in order. "
            "Do not introduce components outside the plan units.\n\n"
        )
        spec = plan_header + spec

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
        # RA-672 C2: "In Review" after push = PR open, awaiting merge.
        # Written to Supabase so C2 scoring survives Railway redeploys.
        _linear_state = "In Review" if (getattr(session, "linear_issue_id", None) and push_ok) else ""
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
            linear_state_after=_linear_state or None,    # RA-672 C2: durable state
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

    # RA-672 Phase 2 — C2 data: log session outcome for ZTE v2 Section C scoring
    try:
        _record_session_outcome(session, push_ok, push_ts)
    except Exception:
        pass  # observability must never block the pipeline

    # RA-931 — record this build run as an episode for future context replay
    try:
        await record_episode(session, brief)
    except Exception:
        pass  # observability must never block the pipeline
