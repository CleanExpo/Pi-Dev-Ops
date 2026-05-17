#!/usr/bin/env python3
"""
kpi_watchdog.py — RA-2990 / RA-2989 follow-up 2026-05-11

Reads the swarm KPI state files (guardian, cs, cfo, cto) and routes
threshold breaches to Phill's Telegram. Pure Python, zero LLM calls,
zero API spend — runs as a cron tick.

Closes the audit-flagged blind spot: "alerts nobody sees aren't alerts".
The C-suite swarm has been producing telemetry every 30s for weeks
with no human-visible escalation path.

Schema sources (sampled 2026-05-11):
  .harness/swarm/guardian.jsonl   — unacked_count
  .harness/swarm/cs_state.jsonl   — per-business NPS, FCR, GRR, churn threats
  .harness/swarm/cfo_state.jsonl  — per-business MRR, burn_multiple, runway_months
  .harness/swarm/cto_state.jsonl  — per-business change_failure_rate, uptime, p99 latency

Usage:
    python3 scripts/kpi_watchdog.py                  # check + post
    python3 scripts/kpi_watchdog.py --dry-run        # print, do not post
    python3 scripts/kpi_watchdog.py --silent-if-ok   # post only on breach

Run via cron (suggested 06:00 + 18:00 UTC) or wire into .harness/cron-triggers.json.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / ".harness" / "swarm"
GUARDIAN = HARNESS / "guardian.jsonl"
CS = HARNESS / "cs_state.jsonl"
CFO = HARNESS / "cfo_state.jsonl"
CTO = HARNESS / "cto_state.jsonl"

# ── Thresholds (tuned from 2026-05-11 audit baselines) ──────────────────────
#
# Each tuple: (field, comparison, threshold, severity, label)
# Severity: 'critical' = SHOULD page; 'warning' = digest only.
# Critical → leading icon 🚨; warning → 🟡.

GUARDIAN_RULES = [
    ("unacked_count", "gt", 50, "warning", "Guardian backlog over 50 messages"),
    ("unacked_count", "gt", 200, "critical", "Guardian backlog over 200 messages"),
    ("should_suspend", "is_true", None, "critical", "Guardian recommending suspend"),
]

CS_RULES = [  # per business
    ("nps", "lt", 0, "critical", "NPS below 0 (detractor state)"),
    ("nps", "lt", 30, "warning", "NPS below 30"),
    ("fcr_pct", "lt", 0.7, "warning", "First-contact resolution below 70%"),
    ("open_enterprise_churn_threats", "gt", 2, "critical", "Enterprise churn threats above 2"),
    ("avg_first_response_minutes", "gt", 240, "warning", "First-response over 4h"),
]

CFO_RULES = [
    ("runway_months", "lt", 6, "critical", "Runway under 6 months"),
    ("runway_months", "lt", 12, "warning", "Runway under 12 months"),
    ("burn_multiple", "gt", 5, "warning", "Burn multiple over 5"),
    ("burn_multiple", "gt", 20, "critical", "Burn multiple over 20"),
    ("nrr", "lt", 0.9, "warning", "Net revenue retention below 90%"),
]

CTO_RULES = [
    ("change_failure_rate", "gte", 0.5, "critical", "Change failure rate ≥ 50%"),
    ("uptime_pct", "lt", 0.99, "warning", "Uptime below 99%"),
    ("uptime_pct", "lt", 0.95, "critical", "Uptime below 95%"),
    ("p99_latency_ms", "gt", 2000, "warning", "p99 latency over 2s"),
    ("mttr_hours", "gt", 8, "warning", "MTTR over 8h"),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _eval(value, op: str, threshold) -> bool:
    if value is None:
        return False
    try:
        v = float(value) if op != "is_true" else bool(value)
    except (TypeError, ValueError):
        return False
    if op == "gt":
        return v > threshold
    if op == "gte":
        return v >= threshold
    if op == "lt":
        return v < threshold
    if op == "lte":
        return v <= threshold
    if op == "is_true":
        return bool(value) is True
    return False


def _read_latest_per_key(path: Path, key: str = "business_id") -> dict[str, dict]:
    """Read a JSONL file and return latest row per key. Skips malformed."""
    latest: dict[str, dict] = {}
    if not path.exists():
        return latest
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            k = row.get(key)
            if k is None:
                continue
            latest[k] = row
    return latest


def _read_latest_singleton(path: Path) -> dict | None:
    """Read a JSONL file and return the most recent row (no per-key grouping)."""
    if not path.exists():
        return None
    last = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
    return last


def _check_rules(row: dict, rules: list[tuple], context: str) -> list[dict]:
    """Apply each rule to a row; return list of breach dicts."""
    breaches = []
    for field, op, threshold, severity, label in rules:
        if _eval(row.get(field), op, threshold):
            breaches.append({
                "context": context,
                "field": field,
                "value": row.get(field),
                "threshold": threshold,
                "severity": severity,
                "label": label,
            })
    return breaches


def _build_digest(breaches: list[dict]) -> str:
    if not breaches:
        return ""
    # Sort: critical first, then warning
    breaches.sort(key=lambda b: (0 if b["severity"] == "critical" else 1, b["context"]))
    lines = [f"🩺 KPI watchdog — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", ""]
    for b in breaches:
        icon = "🚨" if b["severity"] == "critical" else "🟡"
        # Format value (round floats, leave int/bool alone)
        v = b["value"]
        if isinstance(v, float):
            v = f"{v:.3g}"
        lines.append(f"{icon} {b['context']} · {b['label']} (value={v})")
    lines.append("")
    lines.append(f"Total: {sum(1 for b in breaches if b['severity']=='critical')} critical, "
                 f"{sum(1 for b in breaches if b['severity']=='warning')} warning")
    lines.append("Source: .harness/swarm/{guardian,cs_state,cfo_state,cto_state}.jsonl")
    return "\n".join(lines)


def _send_telegram(message: str) -> int:
    """Use the existing send_telegram.py helper. Returns exit code."""
    script = REPO_ROOT / "scripts" / "send_telegram.py"
    if not script.exists():
        print(f"send_telegram.py not found at {script}; cannot post", file=sys.stderr)
        return 1
    result = subprocess.run(
        ["python3", str(script), message],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"telegram send failed (exit {result.returncode}): {result.stderr}", file=sys.stderr)
    else:
        print(result.stdout.strip())
    return result.returncode


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print but do not send")
    parser.add_argument("--silent-if-ok", action="store_true",
                        help="Post only when at least one breach found")
    args = parser.parse_args()

    breaches: list[dict] = []

    # Guardian (singleton — latest entry across the file)
    guardian = _read_latest_singleton(GUARDIAN)
    if guardian:
        breaches.extend(_check_rules(guardian, GUARDIAN_RULES, "Guardian"))

    # CS / CFO / CTO — per-business
    for path, rules, label in (
        (CS, CS_RULES, "CS"),
        (CFO, CFO_RULES, "CFO"),
        (CTO, CTO_RULES, "CTO"),
    ):
        rows = _read_latest_per_key(path, key="business_id")
        for business_id, row in rows.items():
            breaches.extend(_check_rules(row, rules, f"{business_id} · {label}"))

    if not breaches and args.silent_if_ok:
        print("KPI watchdog: no breaches; silent mode.")
        return 0

    digest = _build_digest(breaches) if breaches else (
        f"🟢 KPI watchdog clean — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        "No breaches across guardian / cs_state / cfo_state / cto_state."
    )

    if args.dry_run:
        print(digest)
        return 0

    return _send_telegram(digest)


if __name__ == "__main__":
    sys.exit(main())
