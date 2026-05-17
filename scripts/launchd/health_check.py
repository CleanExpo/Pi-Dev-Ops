#!/usr/bin/env python3
"""
Pi-CEO Enhanced — Health Check & Telegram Alerting
RA-640 | RA-3753 (Pi-CEO FastAPI probe + auto-restart added 2026-05-12)
Runs every 5 minutes via launchd (com.piceo.healthcheck)

Probes:
  - Ollama        http://localhost:11434/api/tags
  - n8n           http://localhost:5678/healthz
  - Pi-CEO API    http://localhost:7777/health    ← RA-3753

If Pi-CEO API is down: attempts auto-restart via `launchctl kickstart`
before alerting. Telegram alert always fires on any service-down state
that does not auto-recover in this tick.

Alerts: Telegram via @piceoagent_bot
"""

import urllib.request
import urllib.error
import json
import os
import subprocess
import sys
import time
import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("PICEO_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID   = os.environ.get("PICEO_CHAT_ID",   "YOUR_CHAT_ID_HERE")

SERVICES = {
    "Ollama":     "http://localhost:11434/api/tags",
    "n8n":        "http://localhost:5678/healthz",
    "Pi-CEO API": "http://localhost:7777/health",   # RA-3753 — was missing, caused silent outage 2026-05-12 05:56-06:16 UTC
}

# Services that should auto-restart on failure (RA-3753).
# Maps service label → launchd job label.
AUTO_RESTART = {
    "Pi-CEO API": "com.piceo.fastapi-standby",
}

TIMEOUT       = 10   # seconds per request
RESTART_WAIT  = 8    # seconds to wait after launchctl kickstart before recheck
LOG_FILE      = os.path.expanduser("~/pi-ceo/logs/health_check.log")
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


def attempt_auto_restart(service_name: str, launchd_label: str) -> bool:
    """RA-3753 — try `launchctl kickstart` on a failed service, then re-probe.

    Returns True if the service recovered after restart, False otherwise.
    """
    log(f"AUTO-RESTART attempting kickstart {launchd_label}...")
    uid = os.getuid()
    try:
        result = subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{uid}/{launchd_label}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            log(f"AUTO-RESTART launchctl returned rc={result.returncode}: {result.stderr.strip()}")
            return False
    except Exception as exc:  # noqa: BLE001
        log(f"AUTO-RESTART kickstart raised: {exc}")
        return False

    log(f"AUTO-RESTART waiting {RESTART_WAIT}s for {service_name} to boot...")
    time.sleep(RESTART_WAIT)
    if check_service(service_name, SERVICES[service_name]):
        log(f"AUTO-RESTART recovered {service_name} ✓")
        return True
    return False


def main():
    log("── health check start ──")
    failed = []
    recovered = []

    for name, url in SERVICES.items():
        if not check_service(name, url):
            # RA-3753: if service has an auto-restart mapping, try it first
            if name in AUTO_RESTART:
                if attempt_auto_restart(name, AUTO_RESTART[name]):
                    recovered.append(name)
                    continue
            failed.append(name)

    # Alert on either: failures that did not auto-recover, OR auto-recovered services
    # (so Phill knows the gap closed — but with different urgency).
    if failed:
        names = ", ".join(failed)
        msg = (
            f"🚨 <b>Pi-CEO Alert</b>\n\n"
            f"Service(s) DOWN: <b>{names}</b>\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Auto-restart {'attempted but did not recover' if any(n in AUTO_RESTART for n in failed) else 'not configured for these services'}.\n"
            f"Check your Mac Mini immediately."
        )
        send_telegram(msg)
        log(f"ALERT fired for: {names}")
        sys.exit(1)
    elif recovered:
        msg = (
            f"⚠️ <b>Pi-CEO Auto-Recovered</b>\n\n"
            f"Service(s) restarted via launchctl: <b>{', '.join(recovered)}</b>\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Service now healthy. Investigate the underlying cause when you have time."
        )
        send_telegram(msg)
        log(f"AUTO-RECOVERED: {', '.join(recovered)}")
        sys.exit(0)
    else:
        log("All services healthy ✓")
        sys.exit(0)


if __name__ == "__main__":
    main()
