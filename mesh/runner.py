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
import types
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent_sandbox  # noqa: E402
import plan_lane  # noqa: E402
import ship_run  # noqa: E402
from fleet_state import active_agent_count, next_work  # noqa: E402
from prompt import build_prompt  # noqa: E402
from repo_guard import repo_dir_for, repo_dir_problem  # noqa: E402
import claim_lifecycle  # noqa: E402
import left_running  # noqa: E402
import node_health  # noqa: E402
import preflight  # noqa: E402
import quota  # noqa: E402
import run_record  # noqa: E402
import runner_idle  # noqa: E402
import self_update  # noqa: E402
from env_file import from_env_file as _from_env_file, resolve_key  # noqa: E402


PI_CEO_API_URL = (
    os.environ.get("PI_CEO_API_URL")
    or _from_env_file("PI_CEO_API_URL")
    or "https://pi-dev-ops-production.up.railway.app"
)
PI_CEO_SECRET = resolve_key("PI_CEO_API_KEY")  # .hermes/.env wins (RA-7905)
HOST = socket.gethostname().split(".")[0]
HARD_STOP = Path.home() / ".claude" / "HARD_STOP"
AGENT_CMD = os.environ.get("MESH_AGENT_CMD", "claude")
POLL_INTERVAL = int(os.environ.get("MESH_POLL_INTERVAL", "30"))
MAX_PARALLEL = int(os.environ.get("MESH_MAX_PARALLEL", "1"))
MAX_CLAIMS = int(os.environ.get("MESH_MAX_CLAIMS", "25"))
IDLE_RECLAIM_DELAY = float(os.environ.get("MESH_IDLE_RECLAIM_DELAY", "3"))
# RA-7802: preflight before claiming; tests/conftest.py turns it off
PREFLIGHT_ENABLED = os.environ.get("MESH_PREFLIGHT", "1") != "0"
SELF_UPDATE_ENABLED = os.environ.get("MESH_SELF_UPDATE", "1") != "0"
CODE_DIR = Path(__file__).resolve().parents[1]
RUNTIME_VERSION = self_update.runtime_version(CODE_DIR)  # reported in every breadcrumb
STATE_FILE = Path(os.environ.get(
    "MESH_RUNNER_STATE", str(Path.home() / ".claude" / "mesh-runner-state.json")))
MESH_KILL_POLL_SECONDS = float(os.environ.get("MESH_KILL_POLL_SECONDS", "5"))
MESH_KILL_GRACE_SECONDS = 10
AGENT_TIMEOUT_SECONDS = 3600
DEFAULT_REPO_DIR = Path(os.environ.get(
    "MESH_REPO_DIR", str(Path(__file__).resolve().parents[1])))
REPOS_ROOT = Path(os.environ.get("MESH_REPOS_ROOT", str(Path.home())))  # other repos' clones
LOG = runner_idle.Log()  # ts, hold reason, poll outcome and last server contact on every line


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


def stuck_file() -> Path:
    """Beside the state file, outside the repo, so no checkout can remove it."""
    return STATE_FILE.with_name("mesh-runner-STUCK")


def killed() -> bool:
    """Return whether the machine-local hard stop is armed."""
    return HARD_STOP.exists()


def write_state(current_task, state: str, session_id: str | None = None, hold_reason: str | None = None) -> None:
    """Write the runner breadcrumb consumed by the heartbeat/Mission Control.

    ``session_id`` is this claim's run id. The heartbeat forwards it into
    ``mesh_agents.session_id`` — the column the mesh schema defined for the
    fleet-identity/session join and that nothing ever populated, so an agent row
    could say *which machine* was busy but never *which run* it was busy on.
    """
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({
            "runtime": AGENT_CMD,
            "current_task": current_task,
            "session_id": session_id,
            "state": state,
            "hold_reason": hold_reason,  # why a held node claims nothing; a quota hold names its reset
            "version": RUNTIME_VERSION,
            "ts": int(time.time()),
        }))
    except OSError:
        pass


def get_work() -> list[dict]:
    """Assigned work first, else a self-claimed mesh:auto ticket (fleet_state.next_work)."""
    return next_work(_api, HOST, LOG.polled, LOG.contacted)


def default_repo_dir_problem() -> str:
    """Why DEFAULT_REPO_DIR must not be trusted, or "" when it is sound."""
    return repo_dir_problem(DEFAULT_REPO_DIR, Path(__file__).resolve().parents[1])


def _repo_dir_for(claim: dict) -> Path:
    """Resolve a claim repo directory; a named `repo` is never built in another repo (W1b)."""
    if claim.get("repo") and not claim.get("repo_dir"):
        return repo_dir_for(claim["repo"], DEFAULT_REPO_DIR, REPOS_ROOT)
    value = claim.get("repo_dir") or str(DEFAULT_REPO_DIR)
    return Path(value).expanduser().resolve()


def _fail_claim(plan: dict, linear_id: str, branch: str, error: str) -> dict:
    """Mark a claim failed and TELL THE SERVER, then return the plan.

    Reporting is the whole point. `mesh_work_claims_one_open` is a partial
    unique index over `claimed`/`working`, so a claim left in either state
    blocks every other node from taking that ticket — and `_reap_stale_claims`
    will not release it, because that deliberately skips machines whose
    heartbeat is fresh, which a runner failing this way still has.

    Extracted because this sequence existed twice and one copy omitted the POST:
    a repo with no `.git` returned `state: failed` to a caller that only prints
    it, so the ticket stayed claimed, unworked and locked (RA-7394). One
    function means the next terminal failure cannot forget the report.
    """
    plan.update(state="failed", error=error)
    _api("POST", "/api/mesh/claim/update", {
        "linear_id": linear_id, "state": "failed", "branch": branch, "host": HOST,
        "claim_id": plan.get("claim_id"), **run_record.fields(None, plan)})
    write_state(None, "idle")
    return plan


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
            claim_lifecycle.terminate(proc, MESH_KILL_GRACE_SECONDS)
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
    """Execute one work claim and report its state. `lane: plan` reviews an idea in
    plan_lane.py; anything else builds in an isolated branch/worktree."""
    if plan_lane.lane_of(claim) == "plan" and not dry_run:
        return plan_lane.run_plan_claim(claim, types.SimpleNamespace(**globals()))
    linear_id = claim["linear_id"]
    repo_dir = _repo_dir_for(claim)
    run_id = uuid.uuid4().hex[:8]
    branch = f"mesh/{HOST.lower()}/{linear_id.lower()}-{run_id}"
    plan = {"linear_id": linear_id, "claim_id": claim.get("id"), "repo_dir": str(repo_dir),
            "branch": branch, "agent": AGENT_CMD}
    if dry_run:
        return {**plan, "dry_run": True}
    if not (repo_dir / ".git").exists():
        return _fail_claim(plan, linear_id, branch, f"repo missing: {repo_dir}")

    worktree = claim_lifecycle.worktree_path(linear_id, run_id)
    held: list = []  # the run record, kept even when an interrupt escapes run_agent
    try:  # from `working` on, every way out — even an interrupt — ends the claim in the finally
        write_state(linear_id, "working", session_id=run_id)
        _api("POST", "/api/mesh/claim/update", {
            "linear_id": linear_id, "state": "working", "branch": branch, "host": HOST,
            "claim_id": plan["claim_id"]})
        start = ship_run.start_point(repo_dir)  # RA-7780: held where the agent cannot move it
        if claim_lifecycle.add_worktree(repo_dir, branch, worktree):
            run_record.run_agent(
                lambda: agent_sandbox.agent_argv(AGENT_CMD, build_prompt(claim, linear_id, branch)),
                str(worktree), STATE_FILE.parent, run_id, plan, _wait_for_agent, held)
            quota.release_if_quota(held, plan, time.time())  # RA-7930: requeued, never a failure
            claim_lifecycle.deliver(  # RA-7780: `done` means pushed, checked before the worktree goes
                lambda: ship_run.settle(plan, start, worktree, branch, linear_id, HOST), plan)
        else:  # a failed add can still leave a partial worktree; the finally removes it
            plan.update(state="failed", error="git worktree add failed")
    finally:
        rec = held[0] if held else None
        claim_lifecycle.end(lambda: _api("POST", "/api/mesh/claim/update", {
            "linear_id": linear_id, "branch": branch, "host": HOST, "claim_id": plan["claim_id"],
            **run_record.terminal(rec, plan)}),
            lambda: claim_lifecycle.remove_worktree(repo_dir, worktree), lambda: write_state(None, "idle"),
            agent_alive=run_record.unreaped(rec), pause=MESH_KILL_POLL_SECONDS,
            then=lambda: run_record.release_interrupt(rec),
            first=lambda: left_running.track(rec))  # RA-7798: never self-update away from an unstopped agent
    return plan


def _stop_status(processed: int) -> dict | None:
    """The status line that ends the loop, or None to keep going."""
    if killed():
        return {"runner": HOST, "status": "HARD_STOP"}
    if stuck := self_update.stuck_reason(stuck_file()):  # delete the file once HEAD is proven code
        return {"runner": HOST, "status": "STUCK", "state": "stuck", "reason": stuck}
    if MAX_CLAIMS and processed >= MAX_CLAIMS:
        return {"runner": HOST, "status": "MAX_CLAIMS", "processed": processed}
    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nexus Mesh runner")
    parser.add_argument("--once", action="store_true", help="process current claims once and exit")
    parser.add_argument("--dry-run", action="store_true", help="plan only; no worktrees, no agent runs")
    return parser.parse_args()


def main() -> int:
    """Run the persistent per-machine claim loop."""
    args = _parse_args()
    problem = default_repo_dir_problem()
    if problem:
        # Non-zero on purpose: KeepAlive{SuccessfulExit:false} retries it, so
        # the node keeps announcing this and resumes once it is fixed.
        print(LOG.line(None, runner=HOST, status="REFUSED", reason=problem))
        return 2
    check = (lambda: preflight.check(DEFAULT_REPO_DIR, AGENT_CMD)) if PREFLIGHT_ENABLED else (lambda: "")
    health, processed = node_health.NodeHealth(check), 0
    updater = self_update.Updater(CODE_DIR, AGENT_CMD) if SELF_UPDATE_ENABLED else None
    while True:
        stop = _stop_status(processed)
        if stop:
            write_state(None, stop.get("state", "idle"))
            print(LOG.line(health, **stop), flush=True)
            # A clean exit keeps launchd from restarting the runner, right for HARD_STOP and
            # STUCK; at the claim cap the Mini just stopped for good (audit 30/09 #18).
            return 4 if stop["status"] == "MAX_CLAIMS" else 0
        if not args.dry_run and not health.may_claim():
            code = runner_idle.hold(types.SimpleNamespace(**globals()), health, args.once)
            if code is not None:
                return code
            continue
        work = get_work()
        results = health.run_batch(work, lambda claim: run_claim(claim, dry_run=args.dry_run), lambda c: _api(
            "POST", "/api/mesh/claim/update",
            {"linear_id": c["linear_id"], "state": "released", "host": HOST, "claim_id": c.get("id")}))
        processed += len(results)
        print(LOG.line(health, runner=HOST, claims=len(work), results=results, processed=processed), flush=True)
        if args.once:
            return 0
        agents = active_agent_count(_api, HOST)
        if work and health.state == "healthy" and agents is not None and agents < MAX_PARALLEL:
            time.sleep(IDLE_RECLAIM_DELAY)
            continue
        if (code := runner_idle.idle(types.SimpleNamespace(**globals()), updater, health, work)) is not None:
            return code
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
