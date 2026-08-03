#!/usr/bin/env python3
"""notify.py — outbound-only Telegram notifier for the fence.

ASYMMETRIC BY CONSTRUCTION. This script SENDS. It has no inbound path, no command
parser, and no way to act on a reply. It cannot be used by an agent to send
arbitrary text: it accepts a KIND and a PATH to a fence-generated artifact, reads
that artifact off disk, and sends it. There is no free-text argument.

That matters because the official Anthropic Telegram plugin is BIDIRECTIONAL — it
turns a Telegram DM into a Claude Code instruction. If that plugin is installed,
the inbound restriction is NOT enforced here; it is enforced by the fence, which
does not care where an instruction came from. A DM saying "deploy to prod" is
refused by exactly the same rule as a keystroke saying it.

Bot: PiCeoEmpire_Bot
Token: from BotFather -> TELEGRAM_BOT_TOKEN. FOUNDER-SUPPLIED. Not obtainable by
an agent, and deliberately not stored in this repo.

Usage:  python notify.py incident <path>
        python notify.py drift    <path>
        python notify.py brief    <path>
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

KINDS = {
    "incident": "\U0001F6D1 FENCE INCIDENT — agent frozen",
    "drift":    "\U000026A0 FENCE DRIFT — reality and fence.json disagree",
    "brief":    "\U0001F4CB Morning brief",
}
MAX = 3800   # Telegram hard limit is 4096


def send(kind: str, path: Path) -> int:
    if kind not in KINDS:
        print(f"unknown kind '{kind}'; allowed: {', '.join(KINDS)}", file=sys.stderr)
        return 2
    if not path.exists():
        print(f"nothing to send: {path} does not exist", file=sys.stderr)
        return 2

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        # Inert, loudly. Never silently "succeed" with nothing sent.
        print("NOT SENT — TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set.\n"
              "This is the one-time founder step: create the token with BotFather for\n"
              "PiCeoEmpire_Bot, then set both variables. Until then the fence still\n"
              "freezes and still writes incident notes to disk — you just don't get pinged.",
              file=sys.stderr)
        return 3

    body = path.read_text(encoding="utf-8", errors="replace")
    if len(body) > MAX:
        body = body[:MAX] + "\n\n[truncated — full note on the desktop]"
    text = f"{KINDS[kind]}\n\n{body}"

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat, "text": text,
                         "disable_web_page_preview": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ok = json.loads(r.read()).get("ok", False)
        print("sent" if ok else "telegram rejected the message", file=sys.stderr)
        return 0 if ok else 1
    except Exception as exc:
        print(f"send failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(send(sys.argv[1], Path(sys.argv[2])))
