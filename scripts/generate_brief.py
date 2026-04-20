#!/usr/bin/env python3
"""
generate_brief.py — Qwen 3 14B intelligence brief generator.

Called by n8n (HTTP Request node) after keyword-filtered RSS items are appended
to Google Docs.  Reads filtered items from stdin or a JSON file, calls the Qwen
inference endpoint, and writes a structured brief JSON to stdout.

Usage (n8n Execute Command node):
    echo '$json_items' | python scripts/generate_brief.py

Usage (standalone test):
    python scripts/generate_brief.py --input /tmp/filtered_items.json --dry-run

Environment variables (set in Railway / n8n credentials):
    QWEN_API_URL      — OpenAI-compatible base URL (e.g. http://qwen-host:8000/v1)
    QWEN_API_KEY      — Bearer token (leave empty for local Ollama)
    QWEN_MODEL        — model name (default: qwen3:14b)
    TELEGRAM_BOT_TOKEN — used for delivery; script posts when --deliver flag set
    TELEGRAM_CHAT_ID  — target chat / channel ID
    GDOC_BRIEF_URL    — Google Doc URL to embed in Telegram message
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("generate_brief")

QWEN_API_URL = os.environ.get("QWEN_API_URL", "http://localhost:11434/v1")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "ollama")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen3:14b")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GDOC_BRIEF_URL = os.environ.get("GDOC_BRIEF_URL", "")

SYSTEM_PROMPT = """\
You are an intelligence analyst for a software engineering team. \
You receive a list of RSS feed items that have already been filtered \
for relevance. Produce a concise daily brief in valid JSON only — \
no prose outside the JSON object. The output must start with {{ and end with }}.

JSON schema:
{{
  "date": "<ISO 8601 date>",
  "headline": "<one sentence capturing the most important signal>",
  "sections": [
    {{
      "title": "<section heading>",
      "items": [
        {{
          "summary": "<2-3 sentence summary>",
          "source": "<feed name>",
          "url": "<article URL>",
          "relevance": "<why this matters to an autonomous AI dev team>"
        }}
      ]
    }}
  ],
  "action_items": ["<concrete next step>"],
  "risk_flags": ["<anything that needs human attention>"]
}}

Group items into 2-4 sections by theme. Limit to the 8 most important items.
Return raw JSON only — no markdown fences, no explanation.
"""


def _load_items(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Load filtered RSS items from --input file or stdin."""
    if args.input:
        with open(args.input) as fh:
            data = json.load(fh)
    else:
        raw = sys.stdin.read().strip()
        if not raw:
            log.error("No input: pass --input FILE or pipe JSON to stdin")
            sys.exit(1)
        data = json.loads(raw)

    # Accept either a bare list or {"items": [...]}
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    raise ValueError(f"Unexpected input shape: {type(data)}")


def _call_qwen(items: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    """POST to Qwen OpenAI-compatible /chat/completions endpoint."""
    user_content = json.dumps(items, ensure_ascii=False, indent=2)
    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
        "stream": False,
    }

    if dry_run:
        log.info("DRY RUN — skipping Qwen API call, returning stub brief")
        return _stub_brief(items)

    url = f"{QWEN_API_URL.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {QWEN_API_KEY}",
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
    except urllib.error.URLError as exc:
        log.error("Qwen API request failed: %s", exc)
        sys.exit(2)

    raw_text = result["choices"][0]["message"]["content"].strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        log.error("Qwen returned non-JSON: %s …\nParse error: %s", raw_text[:200], exc)
        sys.exit(3)


def _stub_brief(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a minimal valid brief for smoke-testing without a live Qwen endpoint."""
    return {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "headline": f"[DRY RUN] {len(items)} items ingested, Qwen not called.",
        "sections": [
            {
                "title": "All items (stub)",
                "items": [
                    {
                        "summary": item.get("title", "(no title)"),
                        "source": item.get("feed_name", "unknown"),
                        "url": item.get("link", ""),
                        "relevance": "stub",
                    }
                    for item in items[:8]
                ],
            }
        ],
        "action_items": ["Review full item list in Google Doc"],
        "risk_flags": [],
    }


def _validate_brief(brief: dict[str, Any]) -> None:
    """Raise ValueError if the brief is missing required top-level keys."""
    required = {"date", "headline", "sections", "action_items", "risk_flags"}
    missing = required - brief.keys()
    if missing:
        raise ValueError(f"Brief missing required keys: {missing}")
    if not isinstance(brief["sections"], list) or len(brief["sections"]) == 0:
        raise ValueError("Brief.sections must be a non-empty list")


def _send_telegram(brief: dict[str, Any]) -> None:
    """Send a formatted brief summary to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping delivery")
        return

    doc_link = f"\n📄 [Full brief]({GDOC_BRIEF_URL})" if GDOC_BRIEF_URL else ""
    action_lines = "\n".join(f"  • {a}" for a in brief.get("action_items", []))
    risk_lines = "\n".join(f"  ⚠️ {r}" for r in brief.get("risk_flags", []))

    text = (
        f"*Pi-CEO Intelligence Brief — {brief['date']}*\n\n"
        f"_{brief['headline']}_\n"
    )
    for section in brief.get("sections", []):
        text += f"\n*{section['title']}*\n"
        for item in section.get("items", []):
            url = item.get("url", "")
            summary = item.get("summary", "")
            source = item.get("source", "")
            link = f"[{source}]({url})" if url else source
            text += f"• {summary} — {link}\n"

    if action_lines:
        text += f"\n*Actions*\n{action_lines}\n"
    if risk_lines:
        text += f"\n*Risk flags*\n{risk_lines}\n"
    text += doc_link

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if not result.get("ok"):
                log.error("Telegram API error: %s", result)
            else:
                log.info("Telegram message sent: message_id=%s", result["result"]["message_id"])
    except urllib.error.URLError as exc:
        log.error("Telegram delivery failed: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate intelligence brief from filtered RSS items")
    parser.add_argument("--input", "-i", help="JSON file of filtered items (default: stdin)")
    parser.add_argument("--output", "-o", help="Write brief JSON to file (default: stdout)")
    parser.add_argument("--dry-run", action="store_true", help="Skip Qwen call, return stub brief")
    parser.add_argument("--deliver", action="store_true", help="Send brief to Telegram after generation")
    args = parser.parse_args()

    items = _load_items(args)
    log.info("Loaded %d filtered RSS items", len(items))

    brief = _call_qwen(items, dry_run=args.dry_run)
    _validate_brief(brief)
    log.info("Brief generated: %s — %d sections", brief["date"], len(brief["sections"]))

    output_json = json.dumps(brief, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w") as fh:
            fh.write(output_json)
        log.info("Brief written to %s", args.output)
    else:
        print(output_json)

    if args.deliver:
        _send_telegram(brief)


if __name__ == "__main__":
    main()
