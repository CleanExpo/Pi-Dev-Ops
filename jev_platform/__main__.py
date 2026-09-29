"""CLI: python -m jev_platform {decide,calibrate,verify-calibration,ratings,ask,approve}. Shadow/advisory only.

The key is read from TYPESAFE_API_KEY at call time (inject with `vercel env run`); it is never logged.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

from jev_platform import ask, client, engine

URL = "https://api.typesafe.ai/v1/systemone"


def http_post(body: dict, timeout: float):
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        retry = e.headers.get("retry-after")
        return e.code, None, float(retry) if retry and retry.replace(".", "", 1).isdigit() else None


def _live_ready() -> bool:
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        print("BLOCKED: TYPESAFE_API_KEY not in environment (use `vercel env run`)", file=sys.stderr)
        return False
    return True


def cmd_decide(a) -> int:
    actions = json.loads(engine.FIXTURES.read_text())["actions"]
    if a.live and a.action not in actions:
        print(f"REFUSED: live decide takes synthetic action ids only: {sorted(actions)}", file=sys.stderr)
        return 2
    if a.live and not _live_ready():
        return 2
    text = actions[a.action]["text"] if a.action in actions else a.action
    post = http_post if a.live else (lambda body, timeout: (503, None, None))
    rec = engine.decide(text, a.rules.split(","), a.claimed_class, post, client.Budget(a.max_usd, a.max_seconds))
    print(json.dumps(rec, indent=1))
    return 0


def cmd_calibrate(a) -> int:
    if not _live_ready():
        return 2
    rec = engine.calibrate(a.rule, http_post, client.Budget(a.max_usd, a.max_seconds))
    print(json.dumps({k: rec.get(k) for k in ("rule", "state", "threshold", "counters", "miss_rate_upper_95",
                                              "errors", "first_error", "spent_usd")}, indent=1))
    return 0 if rec.get("state") not in ("incomplete", None) else 1


def cmd_verify(a) -> int:
    rating, problems = engine.artifact_rating(a.rule)
    head = subprocess.run(["git", "-C", str(engine.ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print(f"{a.rule}: {rating} @ {head}" + (f" — {'; '.join(problems)}" if problems else ""))
    return 0 if rating in ("AA", "AAA") else 1


def cmd_ratings(a) -> int:
    counts = {}
    for rid in engine.registry():
        rating, _ = engine.artifact_rating(rid)
        counts[rating] = counts.get(rating, 0) + 1
        if rating != "FAIL" or a.all:
            print(f"{rid}\t{rating}")
    print("totals " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())) + f" of {sum(counts.values())}")
    return 0


def _repo(path: str | None) -> str:
    cmd = ["git", *(["-C", path] if path else []), "rev-parse", "--show-toplevel"]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def cmd_ask(a) -> int:
    if not _live_ready():
        return 2
    out = ask.ask_files(_repo(a.repo), a.file, a.q, http_post, client.Budget(a.max_usd, a.max_seconds))
    print(json.dumps(out, indent=1))
    return 2 if "blocked" in out else 0


def cmd_approve(a) -> int:
    print(json.dumps(ask.approve_entry(_repo(a.repo), a.path), indent=1))
    print("Paste into .jev-approved.json under \"files\" and commit it; this tool never writes the manifest.",
          file=sys.stderr)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jev_platform")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decide")
    d.add_argument("action")
    d.add_argument("--rules", required=True)
    d.add_argument("--class", dest="claimed_class", type=int, default=None)
    d.add_argument("--live", action="store_true")
    d.add_argument("--max-usd", type=float, default=0.50)
    d.add_argument("--max-seconds", type=float, default=900)
    c = sub.add_parser("calibrate")
    c.add_argument("--rule", required=True)
    c.add_argument("--max-usd", type=float, default=5.00)
    c.add_argument("--max-seconds", type=float, default=1800)
    v = sub.add_parser("verify-calibration")
    v.add_argument("--rule", required=True)
    r = sub.add_parser("ratings")
    r.add_argument("--all", action="store_true")
    k = sub.add_parser("ask", help="Level 8: ask approved question templates about approved files")
    k.add_argument("--file", action="append", required=True)
    k.add_argument("--q", action="append", required=True, help="template id from .jev-approved.json")
    k.add_argument("--max-usd", type=float, default=0.14)
    k.add_argument("--max-seconds", type=float, default=120)
    k.add_argument("--repo", help="repository root (default: the current directory's repo)")
    pr = sub.add_parser("approve", help="print a manifest entry for a file (never writes it)")
    pr.add_argument("path")
    pr.add_argument("--repo")
    a = p.parse_args(argv)
    if a.cmd == "ask" and len(a.file) > 50:
        print("REFUSED: at most 50 files per run", file=sys.stderr)
        return 2
    return {"decide": cmd_decide, "calibrate": cmd_calibrate,
            "verify-calibration": cmd_verify, "ratings": cmd_ratings,
            "ask": cmd_ask, "approve": cmd_approve}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
