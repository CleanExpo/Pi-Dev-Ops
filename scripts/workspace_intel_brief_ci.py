#!/usr/bin/env python3
"""
workspace_intel_brief_ci.py — RA-826 always-on weekly brief for GitHub Actions.

Fetches stored workspace intel from the Pi-CEO Railway backend
(GET /api/workspace-intel), generates an executive brief via Claude Haiku,
and delivers it to Telegram.

Unlike workspace_intel_brief.py (which requires local Ollama), this script
uses only stdlib + the Anthropic and Telegram HTTP APIs — safe for GitHub
Actions and any environment without a local LLM.

Usage:
    python3 scripts/workspace_intel_brief_ci.py           # fetch + brief + send
    python3 scripts/workspace_intel_brief_ci.py --dry-run  # print only, no Telegram

Environment:
    PI_CEO_RAILWAY_URL       — e.g. https://pi-ceo-production.up.railway.app
    PI_CEO_WEBHOOK_SECRET    — value of TAO_WEBHOOK_SECRET from Railway env
    ANTHROPIC_API_KEY        — for Claude Haiku brief generation
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID         — or ALLOWED_USERS (first entry used)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# ─── Configuration ────────────────────────────────────────────────────────────

_CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
_CLAUDE_MODEL   = "claude-haiku-4-5"
_SYSTEM_PROMPT  = (
    "You are a senior technology advisor briefing a founder. "
    "Write a concise executive brief on recent Google Workspace updates. Rules:\n"
    "- Maximum 400 words\n"
    "- Lead with the most strategically important items\n"
    "- Flag anything directly relevant to: MCP integrations, AI agent workflows, "
    "NotebookLM, n8n automation\n"
    "- No filler words. No 'In summary'. Direct, specific, actionable\n"
    "- Format: 3-5 bullet points, each starting with an emoji matching the update type"
)


# ─── Railway client ───────────────────────────────────────────────────────────

def _fetch_intel(railway_url: str, secret: str, limit: int = 30) -> list[dict]:
    """Fetch recent workspace intel batches from Pi-CEO Railway backend."""
    url = f"{railway_url.rstrip('/')}/api/workspace-intel?limit={limit}"
    req = urllib.request.Request(
        url,
        headers={"X-Pi-CEO-Secret": secret},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Railway API HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Railway API connection failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Railway API returned invalid JSON: {exc}") from exc
    return body.get("entries", [])


# ─── Prompt builder ───────────────────────────────────────────────────────────

def _format_intel_block(entries: list[dict]) -> str:
    """Build readable intel text for the LLM prompt."""
    lines: list[str] = [f"# Google Workspace Updates — {len(entries)} recent batches\n"]
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


# ─── Claude client ────────────────────────────────────────────────────────────

def _call_claude(system: str, user: str, api_key: str) -> str:
    """Call Anthropic Claude Haiku and return the assistant message content."""
    payload = json.dumps({
        "model": _CLAUDE_MODEL,
        "max_tokens": 700,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(
        _CLAUDE_API_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Anthropic API HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Anthropic API connection failed: {exc}") from exc
    content: str = (body.get("content") or [{}])[0].get("text", "")
    if not content:
        raise RuntimeError(f"Anthropic API returned empty content: {body}")
    return content.strip()


# ─── Telegram sender ──────────────────────────────────────────────────────────

def _send_telegram(text: str, token: str, chat_id: str) -> None:
    """Post message to Telegram (splits if > 4096 chars)."""
    for chunk in _split_message(text):
        data = urllib.parse.urlencode({
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
            raise RuntimeError(
                f"Telegram HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}"
            ) from exc


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
    parser = argparse.ArgumentParser(
        description="CI weekly Workspace Update brief via Claude Haiku"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print brief; skip Telegram")
    args = parser.parse_args()

    railway_url = os.environ.get("PI_CEO_RAILWAY_URL", "").strip()
    secret      = os.environ.get("PI_CEO_WEBHOOK_SECRET", "").strip()
    api_key     = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    tg_token    = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    allowed     = os.environ.get("ALLOWED_USERS", "")
    tg_chat     = (os.environ.get("TELEGRAM_CHAT_ID") or (allowed.split(",")[0] if allowed else "")).strip()

    if not args.dry_run:
        missing = [k for k, v in [
            ("PI_CEO_RAILWAY_URL",    railway_url),
            ("PI_CEO_WEBHOOK_SECRET", secret),
            ("ANTHROPIC_API_KEY",     api_key),
            ("TELEGRAM_BOT_TOKEN",    tg_token),
        ] if not v]
        if missing:
            print(f"ERROR: missing env vars: {', '.join(missing)}", file=sys.stderr)
            return 1
        if not tg_chat:
            print("ERROR: TELEGRAM_CHAT_ID or ALLOWED_USERS not set", file=sys.stderr)
            return 1

    print("Fetching workspace intel from Railway …")
    try:
        entries = _fetch_intel(railway_url, secret)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not entries:
        print("No workspace intel entries found — n8n RSS monitor may not have run yet.")
        return 0

    total_items = sum(len(b.get("items", [])) for b in entries)
    print(f"Loaded {len(entries)} batches / {total_items} items")

    intel_block = _format_intel_block(entries)
    user_prompt = f"{intel_block}\n\nWrite the weekly executive brief now."

    print(f"Generating brief via {_CLAUDE_MODEL} …")
    try:
        brief = _call_claude(_SYSTEM_PROMPT, user_prompt, api_key)
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
        _send_telegram(message, tg_token, tg_chat)
        print(f"Brief delivered to Telegram chat {tg_chat}")
    except RuntimeError as exc:
        print(f"Telegram error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
