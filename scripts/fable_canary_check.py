#!/usr/bin/env python3
"""fable_canary_check.py — daily watch on the Fable-5 adversary canary (RA-1099 Wave 3).

Logs in to the prod server, reads /api/canary/fable, and — silent on clean, per the
6-pager convention — sends a Telegram alert ONLY when the canary is DISARMED or its
amplification BREACHES the kill-threshold. Always prints the summary for the Action log.

Env: TAO_PROD_URL, TAO_PASSWORD (login), TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (alerts).
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import urllib.request

# The prod URL is not a secret — smoke_pipeline.yml has hardcoded this same value for
# months and logs in successfully every 6h. Defaulting it (as scripts/smoke_test_pipeline.py
# already does) removes the dependency on a TAO_PROD_URL secret that does not exist, which
# is what made this canary skip every night. TAO_PROD_URL still overrides.
DEFAULT_PROD_URL = "https://pi-dev-ops-production.up.railway.app"
URL = (os.environ.get("TAO_PROD_URL") or DEFAULT_PROD_URL).rstrip("/")
PASSWORD = os.environ.get("TAO_PASSWORD", "")


def _client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def main() -> int:
    if not PASSWORD:
        # Previously this returned 0, so a missing secret produced a green check and a
        # daily all-clear on a canary that had never once been read. A security control
        # that cannot run must say so loudly: an unarmed canary is not a clean canary.
        print(
            "FAIL: TAO_PASSWORD not set — canary NOT checked. This is not a clean result.",
            file=sys.stderr,
        )
        return 1
    opener = _client()
    # login (cookie session)
    login = urllib.request.Request(
        f"{URL}/api/login",
        data=json.dumps({"password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        opener.open(login, timeout=15)
        with opener.open(f"{URL}/api/canary/fable", timeout=15) as resp:
            data = json.load(resp)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR reaching canary endpoint: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("Fable canary:", json.dumps(data))
    status = data.get("status")
    if status == "OK":
        return 0  # silent on clean

    # non-OK → alert
    if status == "DISARMED":
        msg = "🔴 Fable canary DISARMED — TAO_FABLE_ALLOWED_ROLES no longer includes adversary. Pre-push reviews are back on Opus."
    else:  # BREACH
        msg = (
            f"🚨 Fable canary BREACH — median amplification {data.get('median_amplification')} "
            f"> {data.get('kill_threshold')} over {data.get('fable_adversary_runs_7d')} runs "
            f"({data.get('refusals_7d')} refusals). Consider reverting: railway variable delete "
            f"TAO_FABLE_ALLOWED_ROLES -s Pi-Dev-Ops"
        )
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from send_telegram import send_telegram  # type: ignore

        send_telegram(msg)
        print("alert sent:", msg)
    except Exception as exc:  # noqa: BLE001
        print(f"ALERT (telegram failed {exc}): {msg}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
