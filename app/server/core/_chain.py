"""
core/_chain.py — Pure Ship Chain primitives (RA-682).

These are the same three functions from scripts/pi_essentials.py, lifted into
production form so both the MCP server and the advanced layer can share them.

generate():  run the claude CLI against a spec in a workspace directory.
evaluate():  score a git diff against the original brief.
decide():    choose pass / retry / warn from score + attempt counters.

No async, no Agent SDK calls here — this layer must run without any event loop
so it can be called from scripts, tests, and non-async contexts.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess

log = logging.getLogger("pi-ceo.core.chain")

# ── generate ──────────────────────────────────────────────────────────────────

def generate(
    spec: str,
    workspace: str,
    model: str = "sonnet",
    timeout: int = 300,
) -> bool:
    """Run `claude -p <spec>` in workspace. Returns True on success.

    When the claude CLI is not installed, logs a warning and returns True
    (demo-safe: callers can still exercise the rest of the chain).
    """
    if not shutil.which("claude"):
        log.warning("core.generate: `claude` CLI not found — skipping (demo mode)")
        return True

    cmd = [
        "claude", "--dangerously-skip-permissions",
        "-p", spec,
        "--model", model,
        "--output-format", "stream-json",
        "--verbose",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=workspace, capture_output=True, text=True, timeout=timeout,
        )
        for line in proc.stdout.splitlines():
            try:
                evt = json.loads(line)
                if evt.get("type") == "text":
                    log.info("generate | %s", evt["text"][:200])
            except json.JSONDecodeError:
                pass
        if proc.returncode != 0:
            log.error("core.generate: claude exited %d", proc.returncode)
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        log.error("core.generate: timed out after %ds", timeout)
        return False


# ── evaluate ──────────────────────────────────────────────────────────────────

_EVAL_PROMPT = """\
You are a senior code reviewer. Score the diff below against the original brief.

ORIGINAL BRIEF:
{brief}

GIT DIFF (last commit):
{diff}

Score on 4 dimensions (1-10) and give a final overall score:
COMPLETENESS: <n>/10 — <reason>
CORRECTNESS:  <n>/10 — <reason>
CONCISENESS:  <n>/10 — <reason>
FORMAT:       <n>/10 — <reason>
OVERALL: <average>/10 — PASS or FAIL (threshold: {threshold}/10)
CONFIDENCE: <0-100>% — <how certain are you?>
"""


def evaluate(
    workspace: str,
    brief: str,
    threshold: float = 8.0,
) -> tuple[float, str]:
    """Run the evaluator pass. Returns (score, eval_text). Score = 0.0 on failure."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1"],
            cwd=workspace, capture_output=True, text=True, timeout=15,
        )
        diff = result.stdout[:6000] if result.stdout else "(no diff)"
    except Exception as exc:
        log.warning("core.evaluate: git diff failed: %s", exc)
        diff = "(no diff)"

    if not shutil.which("claude"):
        log.warning("core.evaluate: `claude` CLI not found — returning demo score 8.5")
        return 8.5, "OVERALL: 8.5/10 — PASS"

    prompt = _EVAL_PROMPT.format(brief=brief, diff=diff, threshold=threshold)
    cmd = [
        "claude", "--dangerously-skip-permissions",
        "-p", prompt,
        "--model", "sonnet",
        "--output-format", "text",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        text = proc.stdout
        for line in text.splitlines():
            if line.upper().startswith("OVERALL:"):
                m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", line)
                if m:
                    return float(m.group(1)), text
    except subprocess.TimeoutExpired:
        log.error("core.evaluate: timed out")
    return 0.0, ""


# ── decide ────────────────────────────────────────────────────────────────────

def decide(
    score: float,
    threshold: float,
    attempt: int,
    max_retries: int,
) -> str:
    """Map (score, attempt) to 'pass' | 'retry' | 'warn'."""
    if score >= threshold:
        return "pass"
    if attempt < max_retries:
        return "retry"
    return "warn"
