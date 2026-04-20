#!/usr/bin/env python3
"""
workspace_intel_brief.py — RA-826 standalone weekly Workspace Update brief generator.

Reads recent workspace intel from .harness/workspace-intel/*.jsonl,
generates an executive brief via Ollama (Qwen 3 14B), and posts to Telegram.

Usage:
    python3 scripts/workspace_intel_brief.py           # last 7 days (default)
    python3 scripts/workspace_intel_brief.py --days 14 # last 14 days
    python3 scripts/workspace_intel_brief.py --dry-run  # print brief, skip Telegram

Environment (env vars or telegram-bot/.env):
    OLLAMA_BASE_URL   — Default: http://localhost:11434
    OLLAMA_BRIEF_MODEL — Default: qwen3:14b
    TELEGRAM_BOT_TOKEN
    ALLOWED_USERS or TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ─── Configuration ────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent.parent
_INTEL_DIR = _REPO_ROOT / ".harness" / "workspace-intel"
_DEFAULT_DAYS = 7
_OLLAMA_DEFAULT_URL = "http://localhost:11434"
_OLLAMA_DEFAULT_MODEL = "qwen3:14b"
_SYSTEM_PROMPT = (
    "You are a senior technology advisor briefing a founder. "
    "Write a concise executive brief on recent Google Workspace updates. Rules:\n"
    "- Maximum 400 words\n"
    "- Lead with the most strategically important items\n"
    "- Flag anything directly relevant to: MCP integrations, AI agent workflows, "
    "NotebookLM, n8n automation\n"
    "- No filler words. No 'In summary'. Direct, specific, actionable\n"
    "- Format: 3-5 bullet points, each starting with an emoji matching the update type"
)


# ─── Intel reader ─────────────────────────────────────────────────────────────

def _load_recent_entries(days: int) -> list[dict]:
    """Read workspace intel batches from JSONL files for the last `days` days."""
    if not _INTEL_DIR.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entries: list[dict] = []

    for jsonl_file in sorted(_INTEL_DIR.glob("*.jsonl")):
        try:
            for line in jsonl_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    batch = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Filter by timestamp
                ts_raw = batch.get("ts", "")
                if ts_raw:
                    try:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                        if ts < cutoff:
                            continue
                    except ValueError:
                        pass
                entries.append(batch)
        except OSError:
            continue

    return entries


def _format_intel_for_prompt(entries: list[dict], days: int = _DEFAULT_DAYS) -> str:
    """Convert raw batches into a readable intel block for the LLM prompt."""
    if not entries:
        return ""
    lines: list[str] = [f"# Google Workspace Updates — last {days} days\n"]
    for batch in entries:
        for item in batch.get("items", []):
            lines.append(f"## {item.get('title', 'Untitled')}")
            lines.append(f"Date: {item.get('pub_date', '')}")
            lines.append(f"URL: {item.get('link', '')}")
            kw = item.get("keywords_matched", [])
            if kw:
                lines.append(f"Keywords: {', '.join(kw)}")
            summary = item.get("summary", "")
            if summary:
                lines.append(f"\n{summary}\n")
            lines.append("---")
    return "\n".join(lines)


# ─── Ollama client ────────────────────────────────────────────────────────────

def _call_ollama(system: str, user: str, base_url: str, model: str) -> str:
    """Call Ollama /api/chat and return the assistant's message content."""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.4, "num_predict": 600},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama connection failed ({base_url}): {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned invalid JSON: {exc}") from exc

    content = (body.get("message") or {}).get("content", "")
    if not content:
        raise RuntimeError(f"Ollama returned empty content: {body}")
    return content.strip()


# ─── Telegram sender ──────────────────────────────────────────────────────────

def _resolve_telegram_config() -> tuple[str, str]:
    """Return (bot_token, chat_id). Falls back to telegram-bot/.env file."""
    import re as _re

    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    allowed = os.environ.get("ALLOWED_USERS", "")

    if not token or not allowed:
        env_path = _REPO_ROOT / "telegram-bot" / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = _re.match(r"^([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$", line)
                if m:
                    k, v = m.group(1), m.group(2).strip().strip('"').strip("'")
                    token   = token   or (v if k == "TELEGRAM_BOT_TOKEN" else "")
                    allowed = allowed or (v if k == "ALLOWED_USERS"       else "")
                    chat_id = chat_id or (v if k == "TELEGRAM_CHAT_ID"    else "")

    if not token:
        raise SystemExit("ERROR: TELEGRAM_BOT_TOKEN not set")
    if not chat_id:
        if not allowed:
            raise SystemExit("ERROR: TELEGRAM_CHAT_ID or ALLOWED_USERS not set")
        chat_id = allowed.split(",")[0].strip()
    return token, chat_id


def _send_telegram(text: str, token: str, chat_id: str) -> None:
    """Fire-and-forget Telegram sendMessage (splits at 4096 chars if needed)."""
    import urllib.parse as _up

    for chunk in _split_message(text):
        data = _up.urlencode({
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15):
                pass
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Telegram HTTP {exc.code}: {body}") from exc


def _split_message(text: str, limit: int = 4096) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remainder = text
    while remainder:
        if len(remainder) <= limit:
            chunks.append(remainder)
            break
        for sep in ("\n\n", "\n", " "):
            pos = remainder.rfind(sep, 0, limit)
            if pos > 0:
                chunks.append(remainder[:pos])
                remainder = remainder[pos:].lstrip()
                break
        else:
            chunks.append(remainder[:limit])
            remainder = remainder[limit:]
    return chunks


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate weekly Workspace Update brief")
    parser.add_argument("--days",    type=int, default=_DEFAULT_DAYS, help="Days of intel to include")
    parser.add_argument("--dry-run", action="store_true", help="Print brief; skip Telegram")
    args = parser.parse_args()

    entries = _load_recent_entries(args.days)
    if not entries:
        print(f"No workspace intel entries found for the last {args.days} days in {_INTEL_DIR}")
        print("Run the n8n RSS monitor workflow first, or wait for the next poll cycle.")
        return 0

    total_items = sum(len(b.get("items", [])) for b in entries)
    print(f"Loaded {len(entries)} batches / {total_items} items from the last {args.days} days")

    intel_block = _format_intel_for_prompt(entries, args.days)
    user_prompt = f"{intel_block}\n\nWrite the weekly executive brief now."

    ollama_url   = os.environ.get("OLLAMA_BASE_URL",     _OLLAMA_DEFAULT_URL)
    ollama_model = os.environ.get("OLLAMA_BRIEF_MODEL",  _OLLAMA_DEFAULT_MODEL)

    print(f"Calling Ollama at {ollama_url} with model {ollama_model} …")
    try:
        brief = _call_ollama(_SYSTEM_PROMPT, user_prompt, ollama_url, ollama_model)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    message = (
        f"📋 *Weekly Workspace Update Brief — {today}*\n\n"
        f"{brief}\n\n"
        f"_Source: workspaceupdates.googleblog.com · {total_items} updates · Pi-CEO RA-826_"
    )

    print("\n" + "─" * 60)
    print(message)
    print("─" * 60 + "\n")

    if args.dry_run:
        print("Dry run — Telegram delivery skipped.")
        return 0

    try:
        token, chat_id = _resolve_telegram_config()
        _send_telegram(message, token, chat_id)
        print(f"Brief delivered to Telegram chat {chat_id}")
    except RuntimeError as exc:
        print(f"Telegram error: {exc}", file=sys.stderr)
        return 2
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
