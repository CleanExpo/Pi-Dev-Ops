#!/usr/bin/env python3
"""
Pi-CEO Enhanced — Health Check & Telegram Alerting
RA-640 | Runs every 5 minutes via launchd
Checks: Ollama /api/tags + n8n /healthz
Alerts: Telegram via @piceoagent_bot
"""

import urllib.request
import urllib.error
import json
import os
import sys
import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("PICEO_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID   = os.environ.get("PICEO_CHAT_ID",   "YOUR_CHAT_ID_HERE")

SERVICES = {
    "Ollama": "http://localhost:11434/api/tags",
    "n8n":    "http://localhost:5678/healthz",
}

TIMEOUT  = 10   # seconds per request
LOG_FILE = os.path.expanduser("~/pi-ceo/logs/health_check.log")
# ─────────────────────────────────────────────────────────────────────────────


def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def send_telegram(message: str):
    if "YOUR_BOT_TOKEN" in TELEGRAM_BOT_TOKEN:
        log("WARNING: Telegram not configured — skipping alert")
        return
    url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}).encode()
    req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT)
        log(f"Telegram alert sent: {message[:60]}...")
    except Exception as e:
        log(f"ERROR sending Telegram alert: {e}")


def check_service(name: str, url: str) -> bool:
    try:
        req  = urllib.request.Request(url, headers={"User-Agent": "pi-ceo-healthcheck/1.0"})
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        if resp.status in (200, 201):
            log(f"OK  {name} ({resp.status})")
            return True
        else:
            log(f"WARN {name} returned HTTP {resp.status}")
            return False
    except urllib.error.URLError as e:
        log(f"DOWN {name}: {e.reason}")
        return False
    except Exception as e:
        log(f"DOWN {name}: {e}")
        return False


def main():
    log("── health check start ──")
    failed = []

    for name, url in SERVICES.items():
        if not check_service(name, url):
            failed.append(name)

    if failed:
        names = ", ".join(failed)
        msg = (
            f"🚨 <b>Pi-CEO Alert</b>\n\n"
            f"Service(s) DOWN: <b>{names}</b>\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Check your Mac Mini immediately."
        )
        send_telegram(msg)
        log(f"ALERT fired for: {names}")
        sys.exit(1)
    else:
        log("All services healthy ✓")
        sys.exit(0)


if __name__ == "__main__":
    main()
