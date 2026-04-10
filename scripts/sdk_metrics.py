#!/usr/bin/env python3
"""
sdk_metrics.py — Analyse SDK invocation metrics from .harness/agent-sdk-metrics/.

Reads daily JSONL files and prints p50/p95 latency, success rate, and per-phase
breakdown for a given date (default: today).

Usage:
  python scripts/sdk_metrics.py                  # today
  python scripts/sdk_metrics.py --date 2026-04-11
  python scripts/sdk_metrics.py --all            # aggregate all days
  python scripts/sdk_metrics.py --json           # machine-readable output
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from statistics import median, quantiles

_METRICS_DIR = Path(__file__).parents[1] / ".harness" / "agent-sdk-metrics"


def _load_rows(date_str: str | None = None, all_days: bool = False) -> list[dict]:
    rows: list[dict] = []
    if not _METRICS_DIR.exists():
        return rows
    if all_days:
        files = sorted(_METRICS_DIR.glob("*.jsonl"))
    else:
        target = date_str or datetime.date.today().isoformat()
        f = _METRICS_DIR / f"{target}.jsonl"
        files = [f] if f.exists() else []
    for f in files:
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    data = sorted(data)
    idx = (p / 100) * (len(data) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
    return data[lo] + (data[hi] - data[lo]) * (idx - lo)


def _analyse(rows: list[dict]) -> dict:
    if not rows:
        return {"total": 0}
    total = len(rows)
    successes = [r for r in rows if r.get("success")]
    failures = [r for r in rows if not r.get("success")]
    latencies = [r["latency_s"] for r in rows if "latency_s" in r]
    by_phase: dict[str, dict] = {}
    for r in rows:
        phase = r.get("phase", "unknown")
        if phase not in by_phase:
            by_phase[phase] = {"total": 0, "success": 0, "latencies": []}
        by_phase[phase]["total"] += 1
        if r.get("success"):
            by_phase[phase]["success"] += 1
        if "latency_s" in r:
            by_phase[phase]["latencies"].append(r["latency_s"])
    phase_summary = {}
    for phase, stats in by_phase.items():
        lats = stats["latencies"]
        phase_summary[phase] = {
            "total": stats["total"],
            "success_rate": round(stats["success"] / stats["total"], 3),
            "p50_s": round(_percentile(lats, 50), 2),
            "p95_s": round(_percentile(lats, 95), 2),
        }
    errors = {}
    for r in failures:
        err = r.get("error") or "unknown"
        errors[err] = errors.get(err, 0) + 1
    return {
        "total": total,
        "success": len(successes),
        "failure": len(failures),
        "success_rate": round(len(successes) / total, 3),
        "p50_s": round(_percentile(latencies, 50), 2),
        "p95_s": round(_percentile(latencies, 95), 2),
        "by_phase": phase_summary,
        "top_errors": dict(sorted(errors.items(), key=lambda x: -x[1])[:5]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SDK invocation metrics analyser")
    parser.add_argument("--date", help="ISO date (default: today)")
    parser.add_argument("--all", action="store_true", dest="all_days", help="Aggregate all days")
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON output")
    args = parser.parse_args()

    rows = _load_rows(args.date, args.all_days)
    result = _analyse(rows)

    if args.as_json:
        print(json.dumps(result, indent=2))
        return 0

    if not rows:
        label = "all days" if args.all_days else (args.date or datetime.date.today().isoformat())
        print(f"No SDK metrics found for {label}.")
        print(f"  Metrics dir: {_METRICS_DIR}")
        print("  SDK path activates when TAO_USE_AGENT_SDK=1.")
        return 0

    label = "all days" if args.all_days else (args.date or datetime.date.today().isoformat())
    print()
    print("═" * 60)
    print(f"  SDK Metrics — {label}")
    print("═" * 60)
    print(f"  Total calls : {result['total']}")
    print(f"  Success     : {result['success']} ({result['success_rate']*100:.1f}%)")
    print(f"  Failure     : {result['failure']}")
    print(f"  p50 latency : {result['p50_s']}s")
    print(f"  p95 latency : {result['p95_s']}s")
    if result.get("by_phase"):
        print()
        print(f"  {'Phase':<20}  {'Calls':<6}  {'Success%':<10}  {'p50s':<7}  p95s")
        print(f"  {'-'*20}  {'-'*6}  {'-'*10}  {'-'*7}  ----")
        for phase, s in result["by_phase"].items():
            print(f"  {phase:<20}  {s['total']:<6}  {s['success_rate']*100:<10.1f}  {s['p50_s']:<7}  {s['p95_s']}")
    if result.get("top_errors"):
        print()
        print("  Top errors:")
        for err, count in result["top_errors"].items():
            print(f"    [{count}x] {err[:70]}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
