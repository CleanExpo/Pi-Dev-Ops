#!/usr/bin/env python3
"""
Pi-CEO Enhanced — Health Check & Telegram Alerting
RA-640 | Runs every 5 minutes via launchd
Checks: Ollama /api/tags + n8n /healthz

Alert rules:
  - Only fires after 2 consecutive failures (avoids restart false positives)
  - 30-minute cooldown between alerts for the same service
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

TIMEOUT             = 10    # seconds per request
FAILURE_THRESHOLD   = 2     # consecutive failures before alert
COOLDOWN_MINUTES    = 30    # minutes between repeat alerts per service
LOG_FILE            = os.path.expanduser("~/pi-ceo/logs/health_check.log")
STATE_FILE          = os.path.expanduser("~/pi-ceo/logs/health_check_state.json")
# ─────────────────────────────────────────────────────────────────────────────


def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


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
        log(f"WARN {name} returned HTTP {resp.status}")
        return False
    except urllib.error.URLError as e:
        log(f"FAIL {name}: {e.reason}")
        return False
    except Exception as e:
        log(f"FAIL {name}: {e}")
        return False


def should_alert(state: dict, name: str) -> bool:
    svc = state.get(name, {})
    last_alert = svc.get("last_alert")
    if not last_alert:
        return True
    elapsed = (datetime.datetime.now() - datetime.datetime.fromisoformat(last_alert)).total_seconds()
    return elapsed >= COOLDOWN_MINUTES * 60


def main():
    log("── health check start ──")
    state = load_state()
    now_iso = datetime.datetime.now().isoformat()
    to_alert = []

    for name, url in SERVICES.items():
        svc = state.setdefault(name, {"failures": 0, "last_alert": None})
        if check_service(name, url):
            if svc["failures"] > 0:
                log(f"RECOVERED {name} (was {svc['failures']} consecutive failures)")
            svc["failures"] = 0
        else:
            svc["failures"] += 1
            log(f"Consecutive failures for {name}: {svc['failures']}/{FAILURE_THRESHOLD}")
            if svc["failures"] >= FAILURE_THRESHOLD and should_alert(state, name):
                to_alert.append(name)
                svc["last_alert"] = now_iso

    save_state(state)

    if to_alert:
        names = ", ".join(to_alert)
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
