"""CLI: python -m jev_platform {decide,calibrate,verify-calibration,ratings,ask,approve,scout,pick-first,ask-jev,agent}.

Shadow/advisory only.

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

from jev_platform import agent, ask, cli_scale, client, engine
from jev_platform import committed as verified
from jev_platform import manifest as mf

URL = "https://api.typesafe.ai/v1/systemone"


def http_post(body: dict, timeout: float):
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with client.open_url(req, timeout) as resp:
            return resp.status, client.strict_json(resp.read().decode()), None
    except ValueError:  # round 26: a duplicate-key reply is no signal, never a judgment
        return 0, None, None
    except urllib.error.HTTPError as e:
        retry = e.headers.get("retry-after")
        return e.code, None, float(retry) if retry and retry.replace(".", "", 1).isdigit() else None


def _live_ready() -> bool:
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        print("BLOCKED: TYPESAFE_API_KEY not in environment (use `vercel env run`)", file=sys.stderr)
        return False
    return True


# PLAN.md rev 4: a live decision sends only a synthetic action as COMMITTED; a working-copy edit is never admitted.
FIXTURE_AT_HEAD = "jev_platform/fixtures/synthetic_actions.json"


def _committed_actions() -> dict:
    try:
        return client.strict_json(verified.at_head(engine.ROOT, FIXTURE_AT_HEAD)[2])["actions"]  # round 12: rehashed
    except (ValueError, KeyError, TypeError):
        return {}


def cmd_decide(a) -> int:
    actions = _committed_actions() if a.live else client.strict_json(engine.FIXTURES.read_text())["actions"]
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
    rating, problems, head = engine.artifact_binding(a.rule)  # round 16: the commit the bytes were compared with
    print(f"{a.rule}: {rating} @ {head or 'no commit'}" + (f" — {'; '.join(problems)}" if problems else ""))
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
    return subprocess.run(cmd, capture_output=True, text=True, env=ask.git_env()).stdout.strip()


def cmd_ask(a) -> int:
    if not _live_ready():
        return 2
    out = ask.ask_files(_repo(a.repo), a.file, a.q, http_post, client.Budget(a.max_usd, a.max_seconds))
    print(json.dumps(out, indent=1))
    return 2 if "blocked" in out else 0


def cmd_approve(a) -> int:
    if sum(x is not None for x in (a.path, a.glob, a.prompt_file)) != 1 or (a.prompt_file is None) != (a.id is None):
        print("REFUSED: give exactly one of PATH, --glob G, or --prompt-file F --id ID", file=sys.stderr)
        return 2
    if a.prompt_file is not None:
        out = mf.approve_prompt(a.prompt_file, a.id)
    elif a.glob is not None:
        out = mf.approve_glob(_repo(a.repo), a.glob)
    else:
        out = ask.approve_entry(_repo(a.repo), a.path)
    print(json.dumps(out, indent=1))
    print("Review, paste into .jev-approved.json and commit it; this tool never writes the manifest.",
          file=sys.stderr)
    return 2 if a.path is None and "files" not in out and "prompts" not in out else 0


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
    pr = sub.add_parser("approve", help="print manifest entries (never writes them)")
    pr.add_argument("path", nargs="?")
    pr.add_argument("--glob")
    pr.add_argument("--prompt-file")
    pr.add_argument("--id")
    pr.add_argument("--repo")
    cli_scale.register(sub, http_post)
    agent.register(sub, http_post)
    a = p.parse_args(argv)
    if a.cmd == "ask" and len(a.file) > 50:
        print("REFUSED: at most 50 files per run", file=sys.stderr)
        return 2
    return {"decide": cmd_decide, "calibrate": cmd_calibrate,
            "verify-calibration": cmd_verify, "ratings": cmd_ratings,
            "ask": cmd_ask, "approve": cmd_approve}.get(a.cmd, getattr(a, "func", None))(a)


if __name__ == "__main__":
    raise SystemExit(main())
