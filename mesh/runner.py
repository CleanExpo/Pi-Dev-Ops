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
# Capacity: how many agents may run on THIS machine at once. Idle detection keeps
# the node pulling work while under this ceiling instead of sleeping a poll cycle.
MAX_PARALLEL = int(os.environ.get("MESH_MAX_PARALLEL", "1"))
# Cost mandate: hard cap on claims a single runner lifetime may process (0 = unlimited).
MAX_CLAIMS = int(os.environ.get("MESH_MAX_CLAIMS", "0"))
# Breadcrumb the heartbeat daemon reads so Mission Control shows the live task.
STATE_FILE = Path(os.environ.get(
    "MESH_RUNNER_STATE", str(Path.home() / ".claude" / "mesh-runner-state.json")))


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


def write_state(current_task, state: str) -> None:
    """Drop a breadcrumb the heartbeat daemon reads so Mission Control shows this
    runner's live task + state per agent. Best-effort; never blocks the loop."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({
            "runtime": AGENT_CMD, "current_task": current_task,
            "state": state, "ts": int(time.time())}))
    except OSError:
        pass


def my_claims() -> list[dict]:
    fleet = _api("GET", "/api/mesh/fleet")
    return [c for c in fleet.get("claims", []) if c.get("machine") == HOST and c.get("state") == "claimed"]


def active_agent_count() -> int:
    """Non-idle agents on THIS machine, per the fleet snapshot (mesh_agents)."""
    fleet = _api("GET", "/api/mesh/fleet")
    return sum(1 for a in fleet.get("agents", []) if a.get("machine") == HOST)


def get_work() -> list[dict]:
    """Pre-assigned claims first; if none, atomically self-claim the top-priority
    unclaimed `mesh:auto` ticket so capacity never idles waiting on the dispatcher."""
    claims = my_claims()
    if claims:
        return claims
    resp = _api("POST", "/api/mesh/claim/self", {"host": HOST})
    claimed = resp.get("claimed")
    return [claimed] if claimed else []


def run_claim(claim: dict, *, dry_run: bool) -> dict:
    """Execute one work claim in an isolated worktree on a mesh branch."""
    linear_id = claim["linear_id"]
    repo_dir = claim.get("repo_dir") or os.getcwd()
    branch = f"mesh/{HOST.lower()}/{linear_id.lower()}"
    plan = {"linear_id": linear_id, "repo_dir": repo_dir, "branch": branch, "agent": AGENT_CMD}
    if dry_run:
        plan["dry_run"] = True
        return plan
    write_state(linear_id, "working")
    _api("POST", "/api/mesh/claim/update", {"linear_id": linear_id, "state": "working", "branch": branch})
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
        write_state(None, "idle")
    _api("POST", "/api/mesh/claim/update", {"linear_id": linear_id, "state": plan["state"], "branch": branch})
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description="Nexus Mesh runner")
    ap.add_argument("--once", action="store_true", help="process current claims once and exit")
    ap.add_argument("--dry-run", action="store_true", help="plan only; no worktrees, no agent runs")
    args = ap.parse_args()
    processed = 0
    while True:
        # Kill switch + cost mandate, re-checked every cycle before any work.
        if killed():
            write_state(None, "idle")
            print(json.dumps({"runner": HOST, "status": "HARD_STOP"})); return 0
        if MAX_CLAIMS and processed >= MAX_CLAIMS:
            write_state(None, "idle")
            print(json.dumps({"runner": HOST, "status": "MAX_CLAIMS", "processed": processed})); return 0
        work = get_work()
        results = [run_claim(c, dry_run=args.dry_run) for c in work]
        processed += len(work)
        print(json.dumps({"runner": HOST, "claims": len(work), "results": results, "processed": processed}))
        if args.once:
            return 0
        # Idle detection: if we did work and stay under this machine's capacity,
        # immediately pull the next claim instead of waiting a full poll cycle —
        # keeps the node draining the queue. Only sleep when idle or at capacity.
        if work and active_agent_count() < MAX_PARALLEL:
            continue
        write_state(None, "idle")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
