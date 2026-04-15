"""
session_recorder.py — RA-931: Experience Recorder.

Writes a structured episode record to `build_episodes` Supabase table after
every run_build() completion. Enables context replay for similar future tasks
(Contextual Experience Replay — CER, ACL 2025).

All writes are fire-and-forget: errors are logged at WARNING level but never
raised. The pipeline must never fail because of observability.

Trust anchor (AgentRR pattern): only episodes with outcome='complete' AND
tests_passed=True are marked verified=True and eligible for context injection.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("pi-ceo.session_recorder")

_URL: str = ""
_KEY: str = ""


def _cfg() -> tuple[str, str]:
    """Lazy-load Supabase credentials from config — same pattern as supabase_log."""
    global _URL, _KEY
    if not _URL:
        from . import config as _c
        _URL = _c.SUPABASE_URL
        _KEY = _c.SUPABASE_SERVICE_ROLE_KEY
    return _URL, _KEY


def _extract_files_touched(output_lines: list[str]) -> list[str]:
    """Parse git diff --stat output from session output_lines, return file list."""
    files: list[str] = []
    for line in output_lines:
        # Git stat format: " path/to/file.py | 12 ++----"
        if "|" in line and ("+" in line or "-" in line):
            path = line.split("|")[0].strip()
            if path and not path.startswith("..."):
                files.append(path)
    return files[:50]  # cap at 50 files


def _extract_error_patterns(output_lines: list[str]) -> list[str]:
    """Extract recurring error type tokens (ImportError, TypeError, etc.) from output."""
    error_re = re.compile(
        r"\b(ImportError|ModuleNotFoundError|TypeError|ValueError|AttributeError|"
        r"RuntimeError|AssertionError|SyntaxError|NameError|KeyError|IndexError|"
        r"PermissionError|FileNotFoundError|TimeoutError)\b"
    )
    seen: set[str] = set()
    for line in output_lines:
        for m in error_re.finditer(line):
            seen.add(m.group(1))
    return sorted(seen)


def _classify_task_type(brief: str) -> str:
    """Heuristic task type from brief text — maps to Linear convention."""
    brief_lower = brief.lower()
    if any(w in brief_lower for w in ("fix", "bug", "error", "broken", "failing")):
        return "fix_bug"
    if any(w in brief_lower for w in ("refactor", "cleanup", "clean up", "reorganise", "restructure")):
        return "refactor"
    if any(w in brief_lower for w in ("doc", "readme", "comment", "docstring")):
        return "docs"
    if any(w in brief_lower for w in ("test", "spec", "coverage", "pytest")):
        return "test"
    return "add_feature"


async def record_episode(session, brief: str = "") -> None:
    """RA-931 — Write a build_episodes row after run_build() completes.

    Args:
        session: BuildSession dataclass.
        brief:   Original task description passed to run_build().

    The call is fire-and-forget — never raises.
    """
    url, key = _cfg()
    if not url or not key:
        log.debug("RA-931: Supabase not configured — skipping episode record")
        return

    try:
        output_lines = getattr(session, "output_lines", [])
        eval_score = float(getattr(session, "evaluator_score", 0) or 0)
        outcome = "complete" if session.status == "complete" else "failed"
        tests_passed = getattr(session, "sandbox_ok", True)  # sandbox phase passed = tests_passed
        verified = (outcome == "complete") and tests_passed

        started_at = getattr(session, "started_at", None)
        duration_s: int | None = None
        if started_at:
            import time
            duration_s = int(time.time() - started_at)

        files_touched = _extract_files_touched(output_lines)
        error_patterns = _extract_error_patterns(output_lines)
        task_type = _classify_task_type(brief)

        # git diff --stat summary (first 500 chars)
        diff_summary_lines = [
            line for line in output_lines
            if "|" in line and ("+" in line or "-" in line)
        ]
        git_diff_summary = "\n".join(diff_summary_lines[:20])[:500]

        row: dict[str, Any] = {
            "session_id":      session.id,
            "task_type":       task_type,
            "repo_url":        getattr(session, "repo_url", ""),
            "files_touched":   files_touched,
            "outcome":         outcome,
            "evaluator_score": eval_score,
            "tests_passed":    tests_passed,
            "verified":        verified,
            "error_patterns":  error_patterns,
            "git_diff_summary": git_diff_summary,
            "created_at":      datetime.now(timezone.utc).isoformat(),
        }
        if duration_s is not None:
            row["duration_s"] = duration_s

        payload = json.dumps(row).encode()
        req = urllib.request.Request(
            f"{url}/rest/v1/build_episodes",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Prefer": "return=minimal",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
        log.info(
            "RA-931: episode recorded session=%s outcome=%s score=%.1f verified=%s files=%d",
            session.id, outcome, eval_score, verified, len(files_touched),
        )
    except Exception as exc:
        log.warning("RA-931: record_episode failed (non-fatal): %s", exc)


async def retrieve_similar_episodes(
    task_description: str,
    repo_url: str = "",
    k: int = 3,
) -> list[dict[str, Any]]:
    """RA-931 — Return up to k verified past episodes for context injection.

    Filters by repo_url (same repo) and outcome='complete'. Returns the k most
    recent verified episodes as formatted context strings. No pgvector on Railway
    free tier — falls back to recency ordering until embedding column is available.

    Args:
        task_description: Brief for the new task (used for future semantic search).
        repo_url:         Repository URL to filter by.
        k:                Maximum number of episodes to return.

    Returns:
        List of dicts with keys: session_id, task_type, files_touched,
        evaluator_score, git_diff_summary, created_at.
    """
    url, key = _cfg()
    if not url or not key:
        return []

    try:
        params = (
            "verified=eq.true"
            "&outcome=eq.complete"
        )
        if repo_url:
            import urllib.parse
            params += f"&repo_url=eq.{urllib.parse.quote(repo_url)}"
        params += f"&order=created_at.desc&limit={k}"

        req = urllib.request.Request(
            f"{url}/rest/v1/build_episodes?{params}",
            method="GET",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            rows = json.loads(resp.read())
        log.debug("RA-931: retrieved %d similar episodes for context", len(rows))
        return rows or []
    except Exception as exc:
        log.warning("RA-931: retrieve_similar_episodes failed (non-fatal): %s", exc)
        return []


def format_episodes_as_context(episodes: list[dict[str, Any]]) -> str:
    """Format retrieved episodes as a compact context block for spec injection.

    Returns:
        Formatted string ready to prepend to the generator spec.
    """
    if not episodes:
        return ""
    lines = ["--- SIMILAR PAST EPISODES (RA-931) ---"]
    for ep in episodes:
        lines.append(
            f"[{ep.get('task_type', '?')}] score={ep.get('evaluator_score', 0):.1f} "
            f"files={','.join((ep.get('files_touched') or [])[:5])} "
            f"date={str(ep.get('created_at', ''))[:10]}"
        )
        if ep.get("git_diff_summary"):
            lines.append(f"  diff_summary: {ep['git_diff_summary'][:200]}")
    lines.append("--- END PAST EPISODES ---")
    return "\n".join(lines)
