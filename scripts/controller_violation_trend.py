"""Controller-violation weekly trend — Margot Monday brief input.

Per Pi-CEO Board memo 2026-05-15 (Layer 4 of the four-layer enforcement
loop, NEXT ACTIONS #3). First firing Mon 2026-05-25 06:00 AEST per the
new hermes cron job (Sunday 20:00 UTC).

Reads ~/Pi-CEO/.harness/swarm/controller-violations.jsonl (populated
by ~/.claude/hooks/discipline/violation_log.py on every controller
Stop event), computes:
  - last-week count
  - 4-week moving average
  - trend direction (down / flat / up)

Outputs a markdown brief to stdout. When --post is passed, also posts
to the Pi-CEO Telegram home channel (chat_id 8792816988).

Stdlib + Hermes Telegram bot token from ~/.hermes/.env (no API key
flowing through chat per feedback-secrets-handling).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_PATH = Path.home() / "Pi-CEO" / ".harness" / "swarm" / "controller-violations.jsonl"
HOME_CHAT_ID = 8792816988  # Phill's Telegram home channel
HERMES_ENV = Path.home() / ".hermes" / ".env"


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def _load_records() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    out = []
    for line in LOG_PATH.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        r["_ts"] = _parse_ts(r.get("ts", ""))
        if r["_ts"]:
            out.append(r)
    return out


def _week_bucket(dt: datetime) -> str:
    # ISO week (year-week)
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def compute_trend(records: list[dict], now: datetime | None = None) -> dict:
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff_4w = now - timedelta(weeks=4)
    cutoff_1w = now - timedelta(weeks=1)

    last_week = [r for r in records if r["_ts"] >= cutoff_1w]
    last_4w = [r for r in records if r["_ts"] >= cutoff_4w]

    last_week_count = sum(len(r.get("violations", [])) for r in last_week)
    last_4w_count = sum(len(r.get("violations", [])) for r in last_4w)
    four_week_avg = last_4w_count / 4.0

    # Prior week (weeks 2-1 ago) for delta
    cutoff_2w = now - timedelta(weeks=2)
    prior_week = [r for r in records if cutoff_2w <= r["_ts"] < cutoff_1w]
    prior_week_count = sum(len(r.get("violations", [])) for r in prior_week)

    if prior_week_count == 0:
        if last_week_count == 0:
            trend = "flat-zero"
        else:
            trend = "establishing-baseline"
    elif last_week_count < prior_week_count:
        trend = "down"
    elif last_week_count > prior_week_count:
        trend = "up"
    else:
        trend = "flat"

    by_pattern = Counter()
    by_week: dict[str, int] = defaultdict(int)
    for r in last_4w:
        wb = _week_bucket(r["_ts"])
        for v in r.get("violations", []):
            by_pattern[v.get("pattern", "?")] += 1
            by_week[wb] += 1

    return {
        "now": now.isoformat(),
        "last_week_count": last_week_count,
        "prior_week_count": prior_week_count,
        "four_week_avg": round(four_week_avg, 1),
        "trend": trend,
        "by_pattern_4w": dict(by_pattern.most_common(10)),
        "by_week": dict(sorted(by_week.items())),
        "total_records_4w": len(last_4w),
    }


def format_brief(trend: dict) -> str:
    icon = {"down": "🟢", "flat-zero": "🟢", "flat": "🟡",
            "establishing-baseline": "🟡", "up": "🔴"}.get(trend["trend"], "⚪")
    lines = [
        "# Controller-Violation Trend — Weekly",
        "",
        f"**Status:** {icon} `{trend['trend']}`",
        "",
        f"- Last week: **{trend['last_week_count']}** violations",
        f"- Prior week: {trend['prior_week_count']}",
        f"- 4-week moving avg: {trend['four_week_avg']}",
        "",
    ]
    if trend["by_pattern_4w"]:
        lines.append("## By pattern (4-week)")
        for k, v in trend["by_pattern_4w"].items():
            lines.append(f"  - {k}: {v}")
        lines.append("")
    if trend["by_week"]:
        lines.append("## Weekly counts (ISO week)")
        for k, v in trend["by_week"].items():
            lines.append(f"  - {k}: {v}")
        lines.append("")
    if trend["trend"] == "up":
        lines.append("⚠️ **Trend rising — review controller scaffolding per Board directive 2026-05-15 (Supabase board_directives id 6298d52f-a1c9-49bb-9180-0c1a48b9cd96).**")
    elif trend["trend"] == "flat" and trend["last_week_count"] > 0:
        lines.append("⚠️ Trend flat — not declining. Loop is not closing as designed.")
    elif trend["trend"] == "down":
        lines.append("✅ Trend declining — enforcement loop is closing.")
    elif trend["trend"] == "flat-zero":
        lines.append("✅ Zero violations both weeks — discipline holding.")
    return "\n".join(lines)


def _bot_token() -> str:
    if not HERMES_ENV.exists():
        return ""
    for line in HERMES_ENV.read_text().splitlines():
        if line.startswith("TELEGRAM_BOT_TOKEN_PICEO=") or line.startswith("TELEGRAM_BOT_TOKEN_UNITEGROUP="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def post_to_telegram(text: str, chat_id: int = HOME_CHAT_ID) -> bool:
    token = _bot_token()
    if not token:
        sys.stderr.write("no PI-CEO / UniteGroup bot token in ~/.hermes/.env\n")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        sys.stderr.write(f"telegram post failed: {e}\n")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", action="store_true", help="Post to Telegram home channel")
    ap.add_argument("--json", action="store_true", help="JSON output instead of markdown")
    args = ap.parse_args()

    records = _load_records()
    trend = compute_trend(records)

    if args.json:
        print(json.dumps(trend, indent=2))
        return 0

    brief = format_brief(trend)
    print(brief)

    if args.post:
        ok = post_to_telegram(brief)
        print(f"\nTelegram post: {'OK' if ok else 'FAILED'}", file=sys.stderr)
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
