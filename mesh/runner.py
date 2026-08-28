#!/usr/bin/env python3
"""Nexus Mesh runner — the per-machine work loop.

Each fleet node runs one runner. It polls the Pi-CEO mesh API for work claims
assigned to this machine, creates an isolated worktree, runs the configured
local agent, then records the claim outcome. The runner uses the same protected
``~/.hermes/.env`` credential source as the heartbeat daemon so a machine cannot
be visible to the fleet while its worker silently lacks authority.

Kill switch: ``~/.claude/HARD_STOP`` is checked before work and while an agent
subprocess is running. Production ``main`` remains PR+CI gated.
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
import uuid
from pathlib import Path


def _from_env_file(name: str) -> str:
    """Read one key from the protected Hermes env file without executing it."""
    envf = Path.home() / ".hermes" / ".env"
    if not envf.exists():
        return ""
    try:
        for raw in envf.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        return ""
    return ""


PI_CEO_API_URL = (
    os.environ.get("PI_CEO_API_URL")
    or _from_env_file("PI_CEO_API_URL")
    or "https://pi-dev-ops-production.up.railway.app"
)
PI_CEO_SECRET = os.environ.get("PI_CEO_API_KEY") or _from_env_file("PI_CEO_API_KEY")
HOST = socket.gethostname().split(".")[0]
HARD_STOP = Path.home() / ".claude" / "HARD_STOP"
AGENT_CMD = os.environ.get("MESH_AGENT_CMD", "claude")
POLL_INTERVAL = int(os.environ.get("MESH_POLL_INTERVAL", "30"))
MAX_PARALLEL = int(os.environ.get("MESH_MAX_PARALLEL", "1"))
MAX_CLAIMS = int(os.environ.get("MESH_MAX_CLAIMS", "25"))
IDLE_RECLAIM_DELAY = float(os.environ.get("MESH_IDLE_RECLAIM_DELAY", "3"))
STATE_FILE = Path(os.environ.get(
    "MESH_RUNNER_STATE", str(Path.home() / ".claude" / "mesh-runner-state.json")))
MESH_KILL_POLL_SECONDS = float(os.environ.get("MESH_KILL_POLL_SECONDS", "5"))
MESH_KILL_GRACE_SECONDS = 10
AGENT_TIMEOUT_SECONDS = 3600
DEFAULT_REPO_DIR = Path(os.environ.get(
    "MESH_REPO_DIR", str(Path(__file__).resolve().parents[1])))


def _api(method: str, path: str, body=None) -> dict:
    """Call the authenticated Pi-CEO mesh API and return a bounded error object."""
    if not PI_CEO_SECRET:
        return {"error": "PI_CEO_API_KEY missing"}
    url = f"{PI_CEO_API_URL.rstrip('/')}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", "X-Pi-CEO-Secret": PI_CEO_SECRET})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read() or "{}")
    except urllib.error.HTTPError as exc:
        return {
            "error": f"HTTP {exc.code}",
            "detail": exc.read()[:200].decode(errors="replace"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def killed() -> bool:
    """Return whether the machine-local hard stop is armed."""
    return HARD_STOP.exists()


def write_state(current_task, state: str) -> None:
    """Write the runner breadcrumb consumed by the heartbeat/Mission Control."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({
            "runtime": AGENT_CMD,
            "current_task": current_task,
            "state": state,
            "ts": int(time.time()),
        }))
    except OSError:
        pass


def my_claims() -> list[dict]:
    """Return open work claims assigned to this exact host."""
    fleet = _api("GET", "/api/mesh/fleet")
    return [
        claim for claim in fleet.get("claims", [])
        if claim.get("machine") == HOST and claim.get("state") == "claimed"
    ]


def active_agent_count() -> int:
    """Count non-idle agents currently reported on this host."""
    fleet = _api("GET", "/api/mesh/fleet")
    return sum(1 for agent in fleet.get("agents", []) if agent.get("machine") == HOST)


def get_work() -> list[dict]:
    """Use assigned work first, otherwise atomically self-claim a mesh:auto ticket."""
    claims = my_claims()
    if claims:
        return claims
    response = _api("POST", "/api/mesh/claim/self", {"host": HOST})
    claimed = response.get("claimed")
    return [claimed] if claimed else []


def _repo_dir_for(claim: dict) -> Path:
    """Resolve a claim repo directory, defaulting deterministically to this repo."""
    value = claim.get("repo_dir") or str(DEFAULT_REPO_DIR)
    return Path(value).expanduser().resolve()


def _terminate_for_stop(proc: subprocess.Popen) -> None:
    """Terminate an in-flight agent cleanly, escalating only after the grace period."""
    proc.terminate()
    try:
        proc.wait(timeout=MESH_KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _wait_for_agent(proc: subprocess.Popen, plan: dict) -> None:
    """Poll an agent for completion, hard stop, or timeout."""
    deadline = time.monotonic() + AGENT_TIMEOUT_SECONDS
    while True:
        status = proc.poll()
        if status is not None:
            returncode = getattr(proc, "returncode", status)
            plan["state"] = "done" if returncode == 0 else "failed"
            if returncode:
                plan["error"] = f"agent exited {returncode}"
            return
        if killed():
            _terminate_for_stop(proc)
            plan["state"] = "released"
            return
        if time.monotonic() >= deadline:
            proc.kill()
            proc.wait()
            plan["state"] = "failed"
            plan["error"] = f"timed out after {AGENT_TIMEOUT_SECONDS}s"
            return
        time.sleep(MESH_KILL_POLL_SECONDS)


def run_claim(claim: dict, *, dry_run: bool) -> dict:
    """Execute one work claim in an isolated branch/worktree and report its state."""
    linear_id = claim["linear_id"]
    repo_dir = _repo_dir_for(claim)
    run_id = uuid.uuid4().hex[:8]
    branch = f"mesh/{HOST.lower()}/{linear_id.lower()}-{run_id}"
    plan = {
        "linear_id": linear_id,
        "repo_dir": str(repo_dir),
        "branch": branch,
        "agent": AGENT_CMD,
    }
    if dry_run:
        plan["dry_run"] = True
        return plan
    if not (repo_dir / ".git").exists():
        return {**plan, "state": "failed", "error": f"repo missing: {repo_dir}"}

    write_state(linear_id, "working")
    _api("POST", "/api/mesh/claim/update", {
        "linear_id": linear_id, "state": "working", "branch": branch})
    worktree = Path("/tmp") / f"mesh-{linear_id}-{run_id}"
    added = subprocess.run(
        ["git", "-C", str(repo_dir), "worktree", "add", "-b", branch, str(worktree)],
        capture_output=True, text=True, check=False,
    )
    if getattr(added, "returncode", 0) != 0:
        plan.update(state="failed", error="git worktree add failed")
        _api("POST", "/api/mesh/claim/update", {
            "linear_id": linear_id, "state": "failed", "branch": branch})
        write_state(None, "idle")
        return plan

    prompt = (
        f"Work the Linear ticket {linear_id}. Make a small, verifiable change, "
        f"run the repo's gates, and stop. autogit ships each turn to {branch}."
    )
    try:
        proc = subprocess.Popen([AGENT_CMD, "-p", prompt], cwd=str(worktree))
        _wait_for_agent(proc, plan)
    except Exception as exc:  # noqa: BLE001
        plan["state"] = "failed"
        plan["error"] = str(exc)
    finally:
        subprocess.run(
            ["git", "-C", str(repo_dir), "worktree", "remove", "--force", str(worktree)],
            capture_output=True, check=False,
        )
        write_state(None, "idle")
    _api("POST", "/api/mesh/claim/update", {
        "linear_id": linear_id, "state": plan["state"], "branch": branch})
    return plan


def main() -> int:
    """Run the persistent per-machine claim loop."""
    parser = argparse.ArgumentParser(description="Nexus Mesh runner")
    parser.add_argument("--once", action="store_true", help="process current claims once and exit")
    parser.add_argument("--dry-run", action="store_true", help="plan only; no worktrees, no agent runs")
    args = parser.parse_args()
    processed = 0
    while True:
        if killed():
            write_state(None, "idle")
            print(json.dumps({"runner": HOST, "status": "HARD_STOP"}))
            return 0
        if MAX_CLAIMS and processed >= MAX_CLAIMS:
            write_state(None, "idle")
            print(json.dumps({
                "runner": HOST, "status": "MAX_CLAIMS", "processed": processed}))
            return 0
        work = get_work()
        results = [run_claim(claim, dry_run=args.dry_run) for claim in work]
        processed += len(work)
        print(json.dumps({
            "runner": HOST,
            "claims": len(work),
            "results": results,
            "processed": processed,
        }))
        if args.once:
            return 0
        if work and active_agent_count() < MAX_PARALLEL:
            time.sleep(IDLE_RECLAIM_DELAY)
            continue
        write_state(None, "idle")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
