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
import datetime
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
    # RA-1169 — json.loads accepts ANY valid JSON value, not just objects.
    # If the stream contains a bare JSON string (e.g. a line like
    # `"Bash(npm audit)"` from a tool_result rendering a permission list),
    # `evt` is a str and `evt.get(...)` crashes the entire generator phase
    # with `'str' object has no attribute 'get'`. Treat any non-dict as
    # raw output and move on.
    if not isinstance(evt, dict):
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
                # RA-1173 — verify the cloned repo's origin matches session.repo_url.
                # When WORKSPACE_ROOT sits inside a parent git repo, the commands
                # further down the pipeline (commit, push) were using the PARENT
                # repo's .git instead of the cloned child's, silently pushing to
                # the wrong remote. Catch that mismatch loudly here.
                _, origin_ru, _ = await run_cmd(
                    session.workspace, "git", "remote", "get-url", "origin", timeout=5,
                )
                origin_ru = origin_ru.strip()
                # Strip x-access-token auth if any, then compare host+path
                def _canon(u: str) -> str:
                    u = u.replace("https://x-access-token:", "https://").rstrip("/")
                    if "@github.com/" in u:
                        u = "https://github.com/" + u.split("@github.com/", 1)[1]
                    return u.removesuffix(".git")
                if _canon(origin_ru) != _canon(session.repo_url):
                    em(session, "error",
                       f"  Clone contamination: workspace origin={origin_ru} but expected {session.repo_url}. "
                       "Aborting — fix TAO_WORKSPACE to a path outside any parent git repo.")
                    session.status = "failed"
                    persistence.save_session(session)
                    _emit_phase_metric(session, "clone", phase_start)
                    return False
                # Plant a stub CLAUDE.md so Claude Code doesn't walk upward
                # into an ancestor repo's CLAUDE.md when the cloned repo has
                # no CLAUDE.md at the root.
                stub_md = os.path.join(session.workspace, "CLAUDE.md")
                if not os.path.exists(stub_md):
                    try:
                        with open(stub_md, "w", encoding="utf-8") as _fh:
                            _fh.write(
                                "# Scoped Pi-CEO workspace\n\n"
                                "This is an isolated autonomous workspace. Only read and edit files\n"
                                "inside this directory. Do not walk upward into parent directories.\n"
                            )
                    except OSError:
                        pass
                # RA-1374 — append `.pi-ceo/` to the cloned repo's .gitignore
                # so task-memory files (PLAN.md, IMPLEMENT.md, PROMPT.md,
                # STATUS.md) don't get committed when the generator stages
                # changes. Observed on DR-NRPG PR #96 and others. Idempotent:
                # we only add the line if not already present.
                try:
                    gi_path = os.path.join(session.workspace, ".gitignore")
                    gi_existing = ""
                    if os.path.exists(gi_path):
                        with open(gi_path, "r", encoding="utf-8") as _fh:
                            gi_existing = _fh.read()
                    if ".pi-ceo/" not in gi_existing.splitlines():
                        with open(gi_path, "a", encoding="utf-8") as _fh:
                            if gi_existing and not gi_existing.endswith("\n"):
                                _fh.write("\n")
                            _fh.write("# Pi-CEO task-memory (auto-added by Pi-CEO session bootstrap, RA-1374)\n")
                            _fh.write(".pi-ceo/\n")
                except OSError:
                    pass
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

    # RA-1178 — always use Sonnet for the plan phase regardless of tier.
    #
    # RA-1175 originally tried to use Haiku for basic briefs to save cost,
    # but (a) on Claude Max we pay $0.0000 per call so there's no cost
    # pressure, and (b) "Fix with Claude" buttons and many webhook-fired
    # sessions arrive with no complexity_tier set, silently degrading them
    # to Haiku which then emits 5% confidence plans, prose questions, or
    # times out at 45 s. Net: Haiku was the source of every bad plan we
    # saw today. Sonnet is fast enough (30 s observed) and reliable.
    #
    # Budgets scaled by tier (generator budget still tier-aware in
    # RA-1174). advanced/detailed get a longer plan window because their
    # briefs legitimately require more thinking.
    _tier = (getattr(session, "complexity_tier", "") or "").lower()
    plan_model = getattr(config, "SONNET_MODEL", "sonnet")
    _model_label = "sonnet"
    if _tier in ("detailed", "advanced"):
        _plan_sdk_timeout = 120
        _plan_wait_timeout = 130
    else:
        _plan_sdk_timeout = 60
        _plan_wait_timeout = 70
    em(session, "phase", f"[3.7/5] Planning implementation ({_model_label})...")
    haiku_model = plan_model  # legacy variable name; kept for diff minimality

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

    # RA-1177 — prompt hardening. Sonnet (smarter than Haiku) was responding
    # with prose clarification questions when the brief seemed ambiguous,
    # producing empty JSON that broke the plan phase. Hardened rules below
    # force assumption-based output regardless of brief quality.
    planning_prompt = (
        "You are a planning agent. Your ONLY output is a JSON object — no prose, "
        "no questions, no markdown, no explanation.\n\n"
        f"Brief:\n{spec[:3000]}\n\n"
        f"Repo context: {repo_context_snippet or 'not available'}\n\n"
        "Output this JSON shape EXACTLY (no markdown fences):\n"
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
        "- 3-8 units maximum.\n"
        "- Be specific about file paths based on the repo context.\n"
        "- For non-behavioral units (config, scaffolding, docs) set "
        "is_behavioral: false and omit test_scenarios.\n"
        "- confidence is 0.0-1.0 (your certainty this plan fully covers the brief).\n"
        "- If the brief is ambiguous, STILL produce a plan — make reasonable "
        "assumptions, record them in risk_notes, and lower confidence. DO NOT "
        "ask for clarification. DO NOT output any text outside the JSON object.\n"
        "- Your very first character MUST be `{` and your very last character "
        "MUST be `}`. Anything else is a hard failure."
    )

    try:
        rc, plan_text, _ = await asyncio.wait_for(
            _run_claude_via_sdk(
                planning_prompt, haiku_model, session.workspace,
                timeout=_plan_sdk_timeout, session_id=session.id, phase="planner",
            ),
            timeout=_plan_wait_timeout,
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
            # RA-1174 — tier-aware generator timeout. The default 300 s was
            # tripping on advanced-tier briefs (full feature overhauls) that
            # legitimately need 5-15 min of Claude thinking + file writing.
            # Basic stays at 300 s; detailed gets 600 s; advanced gets 900 s.
            _tier = (getattr(session, "complexity_tier", "") or "").lower()
            _gen_timeout = 900 if _tier == "advanced" else (600 if _tier == "detailed" else 300)
            rc, sdk_output, cost = await _run_claude_via_sdk(
                current_spec, model, session.workspace,
                timeout=_gen_timeout,
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
            # RA-1169 — capture the traceback so post-mortem debugging can
            # pinpoint the exact SDK call-site that raised. Without this the
            # log just shows `'str' object has no attribute 'get'` with no
            # way to tell whether it came from parse_event, _run_claude_via_sdk,
            # or the SDK itself.
            import traceback  # noqa: PLC0415
            _tb = traceback.format_exc()
            em(session, "error", f"  Error: {type(e).__name__}: {e} (attempt {attempt + 1}/2)")
            # Emit last few traceback frames so we can see where it came from.
            for ln in _tb.strip().split("\n")[-8:]:
                if ln.strip():
                    em(session, "output", f"    {ln[:200]}")
            _log.exception("Generator attempt %d/2 raised", attempt + 1)
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


def _route_linear_ticket_to_target_project(
    session, owner_repo: str, pr_url: str, pr_number: int | None, pr_title: str,
) -> None:
    """RA-1184 — create a Linear ticket in the TARGET repo's project.

    Reads .harness/projects.json for repo → (linear_team_id, linear_project_id)
    mapping. Creates a ticket titled with the PR name, description linking to
    the PR + session ID + evaluator score. Ticket lands in the correct project
    board (e.g. Disaster-Recovery's Linear project, not Pi-Dev-Ops's) so teams
    see autonomous fixes on their own kanban.

    No-ops if LINEAR_API_KEY is missing, projects.json has no entry, or the
    ticket creation fails for any reason (triage continues).
    """
    from pathlib import Path  # noqa: PLC0415
    import json as _json  # noqa: PLC0415
    from .triage import LinearClient  # noqa: PLC0415

    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        em(session, "system", "  Linear ticket skipped: LINEAR_API_KEY not set")
        return

    # Load projects.json; look up by repo name (case-insensitive)
    projects_path = Path(__file__).parent.parent.parent / ".harness" / "projects.json"
    if not projects_path.exists():
        em(session, "system", "  Linear ticket skipped: projects.json not found")
        return
    with open(projects_path) as _fh:
        data = _json.load(_fh)
    projects = data.get("projects", [])
    # owner_repo is "owner/repo"; take the last path segment
    repo_name = owner_repo.split("/")[-1].lower()
    match = None
    for p in projects:
        if p.get("repo", "").split("/")[-1].lower() == repo_name:
            match = p
            break
    if not match:
        em(session, "system", f"  Linear ticket skipped: no projects.json entry for {repo_name}")
        return

    team_id = match.get("linear_team_id")
    proj_id = match.get("linear_project_id")
    if not team_id:
        em(session, "system", f"  Linear ticket skipped: no team_id for {repo_name}")
        return

    client = LinearClient(api_key)
    score = getattr(session, "evaluator_score", None)
    confidence = getattr(session, "evaluator_confidence", None)
    description = (
        f"**Autonomous Pi-CEO session:** `{session.id}`\n\n"
        f"**PR:** {pr_url}\n\n"
        + (f"**Evaluator score:** {score}/10 @ {confidence}% confidence\n\n" if score else "")
        + "This ticket was auto-created by Pi-CEO's autonomous fix pipeline. "
        "Review the linked PR; close this ticket when the PR is merged.\n\n"
        "🤖 Pi-CEO"
    )
    try:
        issue = client.create_issue(
            team_id=team_id,
            title=f"[Pi-CEO] {pr_title[:200]}",
            description=description,
            priority=3,
            project_id=proj_id,
        )
        _id = issue.get("identifier", "?")
        _url = issue.get("url", "")
        em(session, "success", f"  🎫 Linear ticket created: {_id} → {_url}")
        try:
            session.linear_issue_id = issue.get("id")  # type: ignore[attr-defined]
        except Exception:
            pass
    except Exception as exc:
        raise RuntimeError(f"Linear issueCreate failed: {exc}") from exc


# ── RA-1743 — opus-adversary pre-push gate ─────────────────────────────────

async def _phase_adversary(session, total_phases: int) -> tuple[bool, dict]:
    """RA-1743 — Pre-push opus-adversary review gate.

    Runs Opus 4.7 on the diff produced by generator+evaluator with adversarial
    framing per ~/.claude/skills/opus-adversary/SKILL.md. Verdict APPROVE /
    APPROVE WITH NOTES / BLOCK; BLOCK halts push. Logs every run to
    .harness/adversary-runs/YYYY-MM-DD.jsonl for the training pipeline (RA-1745).

    Returns (proceed_ok, verdict_data) where:
        proceed_ok: True if push should proceed (APPROVE or APPROVE WITH NOTES or skipped)
                    False if BLOCK
        verdict_data: dict with verdict, concerns, raw_output for logging
    """
    phase_start = time.monotonic()
    em(session, "phase", "[Adversary] Opus 4.7 challenging Sonnet's work...")

    # ── Get diff to review ───────────────────────────────────────────────
    rc, diff_out, _ = await run_cmd(session.workspace, "git", "diff", "HEAD", "--")
    if not diff_out.strip():
        em(session, "system", "  No diff to review — skipping adversary phase")
        _emit_phase_metric(session, "adversary", phase_start, 0.0)
        return True, {"verdict": "SKIP_NO_DIFF", "concerns": []}

    # ── Skip on docs-only / test-only diffs (low signal-to-cost) ────────
    rc, stat_out, _ = await run_cmd(session.workspace, "git", "diff", "--stat", "HEAD")
    files_changed = [
        line.split("|")[0].strip()
        for line in stat_out.strip().split("\n")
        if "|" in line
    ]
    code_files = [
        f for f in files_changed
        if not (
            f.startswith("docs/") or f.startswith("README")
            or f.endswith(".md") or f.startswith("tests/")
            or "/test_" in f or f.endswith(".lock") or f == "package-lock.json"
        )
    ]
    if not code_files:
        em(session, "system", f"  Docs/test-only diff ({len(files_changed)} files) — skipping adversary")
        _emit_phase_metric(session, "adversary", phase_start, 0.0)
        return True, {"verdict": "SKIP_DOCS_ONLY", "files": files_changed}

    # ── Build adversarial prompt (mirrors ~/.claude/skills/opus-adversary/SKILL.md) ──
    brief_excerpt = ""
    for attr in ("brief", "_brief_context_for_persona"):
        v = getattr(session, attr, "")
        if v:
            brief_excerpt = (v[:600] + "...") if len(v) > 600 else v
            break

    prompt = (
        "You are reviewing a change Sonnet 4.6 just made. Your job is to find what "
        "I missed — not to validate. Be skeptical, not agreeable.\n\n"
        f"## What was asked for\n{brief_excerpt}\n\n"
        f"## Diff\n```\n{diff_out[:8000]}\n```\n\n"
        "## Your job\n"
        "For each concern, dig into the actual code and report:\n"
        "1. Race conditions, ordering bugs, concurrency assumptions that may not hold\n"
        "2. Error paths I didn't handle, or handled wrong\n"
        "3. Edge cases at boundaries (empty, max, null, unicode, timezone, large input)\n"
        "4. Hidden assumptions about caller behavior, env state, or data shape\n"
        "5. Reversibility — can this be rolled back cleanly if wrong?\n"
        "6. Tests that would have caught a real bug here but don't exist\n"
        "7. Anywhere the obvious approach was picked when a different design would be safer\n\n"
        "Format: numbered concerns with file:line citations. End with verdict on its own line:\n"
        "  APPROVE   /   APPROVE WITH NOTES   /   BLOCK\n"
        "followed by a one-sentence reason. Be terse. No preamble, no praise."
    )

    # ── Call SDK with model=opus, role=adversary ─────────────────────────
    # Use module-level _run_claude_via_sdk (imported at top) so test mocks
    # via patch("app.server.session_phases._run_claude_via_sdk", ...) apply.
    rc, output_text, cost = await _run_claude_via_sdk(
        prompt=prompt,
        model="opus",
        workspace=session.workspace,
        timeout=180,
        session_id=session.id,
        phase="adversary",
        thinking="adaptive",
    )

    # ── Parse verdict from final lines ───────────────────────────────────
    verdict = "UNKNOWN"
    if rc == 0 and output_text:
        last_block = "\n".join(output_text.strip().split("\n")[-6:]).upper()
        if "BLOCK" in last_block:
            verdict = "BLOCK"
        elif "APPROVE WITH NOTES" in last_block:
            verdict = "APPROVE_WITH_NOTES"
        elif "APPROVE" in last_block:
            verdict = "APPROVE"

    # ── Log to .harness/adversary-runs/YYYY-MM-DD.jsonl ──────────────────
    try:
        runs_dir = Path(__file__).resolve().parents[2] / ".harness" / "adversary-runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.date.today().isoformat()
        log_path = runs_dir / f"{today}.jsonl"
        with log_path.open("a") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "session_id": session.id,
                "verdict": verdict,
                "rc": rc,
                "cost_usd": cost,
                "duration_s": round(time.monotonic() - phase_start, 2),
                "files_changed": files_changed,
                "raw_output": output_text[:4000],
            }) + "\n")
    except Exception as exc:
        _log.warning("RA-1743 adversary log write failed: %s", exc)

    _emit_phase_metric(session, "adversary", phase_start, cost)

    # ── Halt on BLOCK ────────────────────────────────────────────────────
    if verdict == "BLOCK":
        em(session, "error", "  Adversary BLOCK — halting push. See .harness/adversary-runs/")
        return False, {"verdict": verdict, "raw_output": output_text}

    em(
        session, "success",
        f"  Adversary verdict: {verdict} (cost ${cost:.3f}, {round(time.monotonic() - phase_start, 1)}s)",
    )
    return True, {"verdict": verdict, "raw_output": output_text}


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

            # RA-1183 — auto-open a PR from pidev/auto-<sid> → main.
            # Only when push succeeded AND the branch has a real diff vs main
            # (avoids empty PRs from sessions that correctly decided nothing
            # needed fixing). Uses GitHub REST API with x-access-token auth
            # from the embedded remote URL.
            if push_ok and github_token:
                try:
                    # Check there's actually a diff to PR
                    rc_diff, diff_out, _ = await run_cmd(
                        session.workspace, "git", "diff", "--name-only", "origin/main", branch_name, timeout=10,
                    )
                    if rc_diff == 0 and diff_out.strip():
                        # Derive owner/repo from remote URL
                        _, ru, _ = await run_cmd(session.workspace, "git", "remote", "get-url", "origin", timeout=5)
                        ru = ru.strip().rstrip("/")
                        # Strip token auth + .git suffix
                        ru = ru.replace(f"https://x-access-token:{github_token}@", "https://")
                        if ru.endswith(".git"):
                            ru = ru[:-4]
                        owner_repo = ru.replace("https://github.com/", "")
                        # Latest commit message for PR title
                        _, last_msg, _ = await run_cmd(
                            session.workspace, "git", "log", "-1", "--pretty=%s", branch_name, timeout=5,
                        )
                        pr_title = last_msg.strip() or f"feat: Pi CEO autonomous fix ({session.id[:8]})"
                        pr_body = (
                            f"Autonomous Pi-CEO session `{session.id}`.\n\n"
                            f"Evaluator score: {getattr(session, 'evaluator_score', 'n/a')}/10 "
                            f"@ {getattr(session, 'evaluator_confidence', 'n/a')}% confidence.\n\n"
                            f"🤖 Generated by Pi-CEO"
                        )
                        import urllib.request as _ur  # noqa: PLC0415
                        import json as _json  # noqa: PLC0415
                        req = _ur.Request(
                            f"https://api.github.com/repos/{owner_repo}/pulls",
                            data=_json.dumps({
                                "title": pr_title,
                                "body": pr_body,
                                "head": branch_name,
                                "base": "main",
                            }).encode(),
                            headers={
                                "Authorization": f"Bearer {github_token}",
                                "Accept": "application/vnd.github+json",
                                "Content-Type": "application/json",
                            },
                            method="POST",
                        )
                        try:
                            with _ur.urlopen(req, timeout=15) as resp:
                                pr_data = _json.loads(resp.read())
                                pr_url = pr_data.get("html_url", "")
                                pr_number = pr_data.get("number")
                                em(session, "success", f"  ✨ PR opened: #{pr_number} → {pr_url}")
                                # Persist PR URL on session for the dashboard
                                try:
                                    session.pr_url = pr_url  # type: ignore[attr-defined]
                                except Exception:
                                    pass
                                # RA-1184 — route Linear ticket to the TARGET
                                # repo's Linear project (not Pi-Dev-Ops). Reads
                                # projects.json for team_id + linear_project_id.
                                # Only creates a ticket when we don't already
                                # have one (linear_issue_id unset).
                                if not getattr(session, "linear_issue_id", None):
                                    try:
                                        _route_linear_ticket_to_target_project(
                                            session, owner_repo, pr_url, pr_number, pr_title,
                                        )
                                    except Exception as _lin_exc:
                                        em(session, "system", f"  Linear auto-ticket skipped: {_lin_exc}")
                        except Exception as _pr_exc:
                            em(session, "system", f"  PR auto-open skipped: {_pr_exc}")
                    else:
                        em(session, "system", "  No diff vs main — skipping PR open")
                except Exception as _pr_err:
                    em(session, "system", f"  PR auto-open check failed: {_pr_err}")
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
    # RA-1294 — persist the resolved tier on the session so the generator phase
    # (line ~918) can scale its timeout by tier. Without this write-back the
    # generator reads session.complexity_tier, finds it still empty (the
    # autonomy poller's create_session call doesn't pass a tier), and defaults
    # to the 300 s basic timeout — every advanced/detailed autonomy-triggered
    # session died at 305 s in the generate phase. Verified by 60+ failed
    # sessions with last_phase=plan, SDK rc=1 @ exactly 305 s × 2 attempts
    # (2026-04-18).
    session.complexity_tier = resolved_tier
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

    # RA-1743 — opus-adversary pre-push gate. BLOCK halts push.
    adversary_ok, _adv_verdict = await _phase_adversary(session, total_phases)
    if not adversary_ok:
        session.last_completed_phase = "adversary_block"
        session.status = "blocked"
        session.adversary_verdict = _adv_verdict
        persistence.save_session(session)
        _sync_linear_on_completion(session)
        return

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
