#!/usr/bin/env python3
"""
workspace_update_brief.py — RA-826: Generate weekly Google Workspace update brief.

Reads stored workspace intel from .harness/workspace-intel/*.jsonl, generates a
concise executive brief via Qwen 3 14B (local Ollama), and sends it to Telegram.

Usage:
    python3 scripts/workspace_update_brief.py           # last 7 days (default)
    python3 scripts/workspace_update_brief.py --days 14  # last 14 days

Environment (from telegram-bot/.env or process env):
    TELEGRAM_BOT_TOKEN   — piceoagent_bot token
    ALLOWED_USERS        — comma-separated chat IDs (first used as recipient)
    TELEGRAM_CHAT_ID     — explicit override

    OLLAMA_BASE_URL      — default: http://localhost:11434
    OLLAMA_TIMEOUT_S     — default: 120
    QWEN_MODEL           — default: qwen3:14b
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INTEL_DIR = REPO_ROOT / ".harness" / "workspace-intel"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT  = int(os.environ.get("OLLAMA_TIMEOUT_S", "120"))
QWEN_MODEL      = os.environ.get("QWEN_MODEL", "qwen3:14b")

_SYSTEM_PROMPT = (
    "Produce a concise 'Weekly Workspace Update' executive brief for the Pi-CEO Intelligence Report. "
    "Focus on: Gemini and AI capability changes, MCP or agent protocol updates, NotebookLM enhancements, "
    "Workspace automation and scheduling changes, pricing or policy shifts. "
    "Output 200-300 words. No filler words (delve, tapestry, landscape, leverage, robust, seamless, elevate). "
    "No first-person language. Bullet points for key items. "
    "End with a 'Recommended Actions' section listing at most 3 concrete next steps."
)


def _load_entries(days: int) -> list[dict]:
    """Read all workspace intel JSONL entries from the last `days` days."""
    if not INTEL_DIR.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entries: list[dict] = []
    for jsonl_file in sorted(INTEL_DIR.glob("*.jsonl")):
        try:
            file_date = datetime.strptime(jsonl_file.stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if file_date < cutoff:
            continue
        for line in jsonl_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    entries.sort(key=lambda e: e.get("published", ""), reverse=True)
    return entries


def _call_ollama(system: str, user: str) -> str | None:
    """Call local Ollama with the given prompt. Returns response text or None."""
    body = json.dumps({
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.3},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data.get("message", {}).get("content", "").strip() or None
    except urllib.error.URLError as exc:
        print(f"ERROR: Ollama request failed: {exc}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"ERROR: Unexpected Ollama error: {exc}", file=sys.stderr)
        return None


def _build_user_prompt(entries: list[dict]) -> str:
    capped = entries[:20]  # Qwen 3 14B context limit safety cap
    lines = "\n".join(
        f"{i + 1}. {e['title']} ({(e.get('published') or '')[:10]}): "
        f"{(e.get('summary') or '')[:400]}"
        for i, e in enumerate(capped)
    )
    return (
        f"Summarise these {len(capped)} Google Workspace updates into the weekly brief:\n\n{lines}"
    )


def _format_telegram_message(brief: str) -> str:
    today = datetime.now().strftime("%-d %B %Y")
    header = f"📋 *Weekly Workspace Intel*\n_{today}_\n\n"
    footer = "\n\n_Source: workspaceupdates.googleblog.com via Pi-CEO RA-826_"
    msg = header + brief + footer
    if len(msg) > 4000:
        msg = msg[:4000] + "\n\n…_(truncated)_"
    return msg


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate weekly Workspace Update brief")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="Print brief to stdout, skip Telegram")
    args = parser.parse_args()

    entries = _load_entries(args.days)
    if not entries:
        print(f"No workspace intel found in last {args.days} days — nothing to brief.")
        return 0

    print(f"Loaded {len(entries)} entries from last {args.days} days. Calling {QWEN_MODEL}…")
    brief = _call_ollama(_SYSTEM_PROMPT, _build_user_prompt(entries))
    if not brief:
        print("ERROR: Qwen returned empty response. Check Ollama is running.", file=sys.stderr)
        return 1

    message = _format_telegram_message(brief)

    if args.dry_run:
        print("\n── Brief ──────────────────────────────────────────────────────────\n")
        print(message)
        print("\n── End ────────────────────────────────────────────────────────────\n")
        return 0

    sys.path.insert(0, str(REPO_ROOT))
    try:
        from scripts.send_telegram import send_telegram
    except ImportError:
        print("ERROR: could not import send_telegram", file=sys.stderr)
        return 1

    try:
        ids = send_telegram(message, parse_mode="Markdown")
        print(f"Weekly Workspace brief delivered. Message IDs: {ids}")
        return 0
    except Exception as exc:
        print(f"ERROR: Telegram delivery failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
