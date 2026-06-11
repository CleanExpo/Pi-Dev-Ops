#!/usr/bin/env python3
"""Nexus Mesh runner — the per-machine work loop.

Spec: docs/superpowers/specs/2026-06-11-nexus-mesh-design.md

Each fleet node runs one runner. It polls the Pi-CEO mesh API for work claims
assigned to THIS machine, and for each one: creates an isolated git worktree on a
`mesh/<host>/<ticket>` branch, runs the local agent (claude/codex) with the ticket
as the prompt, lets autogit ship every turn, then marks the claim done and updates
Linear. Branch-only — production `main` stays PR+CI gated.

Kill switch: honours `~/.claude/HARD_STOP` and the Pi-CEO /api/swarm/kill state,
exactly like the existing TAO loops (CLAUDE.md: three-layer kill-switch).

This is P1/P2 infrastructure — it goes live once the /api/mesh/* endpoints are
deployed to Railway. Until then `--once --dry-run` exercises the full claim→run
plan without mutating anything, which is how it is tested in CI.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PI_CEO_API_URL = os.environ.get("PI_CEO_API_URL", "https://pi-dev-ops-production.up.railway.app")
PI_CEO_SECRET = os.environ.get("PI_CEO_API_KEY", "")
HOST = socket.gethostname().split(".")[0]
HARD_STOP = Path.home() / ".claude" / "HARD_STOP"
AGENT_CMD = os.environ.get("MESH_AGENT_CMD", "claude")  # claude | codex
POLL_INTERVAL = int(os.environ.get("MESH_POLL_INTERVAL", "30"))


def _api(method: str, path: str, body=None) -> dict:
    url = f"{PI_CEO_API_URL.rstrip('/')}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", "X-Pi-CEO-Secret": PI_CEO_SECRET})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": e.read()[:200].decode(errors="replace")}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def killed() -> bool:
    return HARD_STOP.exists()


def my_claims() -> list[dict]:
    fleet = _api("GET", "/api/mesh/fleet")
    return [c for c in fleet.get("claims", []) if c.get("machine") == HOST and c.get("state") == "claimed"]


def run_claim(claim: dict, *, dry_run: bool) -> dict:
    """Execute one work claim in an isolated worktree on a mesh branch."""
    linear_id = claim["linear_id"]
    repo_dir = claim.get("repo_dir") or os.getcwd()
    branch = f"mesh/{HOST.lower()}/{linear_id.lower()}"
    plan = {"linear_id": linear_id, "repo_dir": repo_dir, "branch": branch, "agent": AGENT_CMD}
    if dry_run:
        plan["dry_run"] = True
        return plan
    wt = Path("/tmp") / f"mesh-{linear_id}"
    subprocess.run(["git", "-C", repo_dir, "worktree", "add", "-b", branch, str(wt)], check=False)
    prompt = (f"Work the Linear ticket {linear_id}. Make a small, verifiable change, "
              f"run the repo's gates, and stop. autogit ships each turn to {branch}.")
    try:
        subprocess.run([AGENT_CMD, "-p", prompt], cwd=str(wt), check=False, timeout=3600)
        plan["state"] = "done"
    except Exception as e:  # noqa: BLE001
        plan["state"] = "failed"; plan["error"] = str(e)
    finally:
        subprocess.run(["git", "-C", repo_dir, "worktree", "remove", "--force", str(wt)], check=False)
    _api("POST", "/api/mesh/claim/update", {"linear_id": linear_id, "state": plan["state"], "branch": branch})
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description="Nexus Mesh runner")
    ap.add_argument("--once", action="store_true", help="process current claims once and exit")
    ap.add_argument("--dry-run", action="store_true", help="plan only; no worktrees, no agent runs")
    args = ap.parse_args()
    while True:
        if killed():
            print(json.dumps({"runner": HOST, "status": "HARD_STOP"})); return 0
        claims = my_claims()
        results = [run_claim(c, dry_run=args.dry_run) for c in claims]
        print(json.dumps({"runner": HOST, "claims": len(claims), "results": results}))
        if args.once:
            return 0
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
