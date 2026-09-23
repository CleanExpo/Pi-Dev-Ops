"""The mesh runner's plan lane: an ``idea:plan`` claim is reviewed, never built.

A build-lane claim gets a git worktree and an agent that changes code. A plan-lane claim
gets neither. The agent runs in a throwaway directory with the code-changing tools denied
(``--disallowedTools`` per ``claude --help``), and its stdout IS the result: one markdown
Board packet, saved locally and handed to the server so the idea-pipeline panel shows it.

Every failure — non-zero exit, empty stdout, timeout, an agent that cannot start, a
packet that cannot be saved — goes through the runner's ``_fail_claim``, so the claim is
reported ``failed`` and never left holding ``mesh_work_claims_one_open``.

The runner's globals arrive as ``rt`` rather than by import: the runner imports this
module (and runs as ``__main__``), and snapshotting its globals at call time is what lets
tests swap ``_api``.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import uuid
from datetime import date
from pathlib import Path

from prompt import build_plan_prompt

PACKET_DIR = Path(os.environ.get(
    "MESH_PACKET_DIR", str(Path.home() / ".local" / "state" / "gs" / "projects" / "ideas")))
PACKET_MAX_CHARS = 20_000  # app/server/mesh_lanes.py caps the same field server-side
DISALLOWED_TOOLS = ("Bash", "Edit", "Write", "NotebookEdit")
_UPDATE = "/api/mesh/claim/update"


def agent_argv(agent_cmd: str, prompt: str) -> list[str]:
    """``--disallowedTools`` is variadic in the claude CLI, so it must come last."""
    return [agent_cmd, "-p", prompt, "--disallowedTools", *DISALLOWED_TOOLS]


def _run_agent(claim: dict, plan: dict, rt) -> str:
    """Run the reviewer in a temp dir, stdout to a temp file, and return that stdout.

    A file rather than a pipe: ``_wait_for_agent`` polls, and a pipe nobody reads fills
    at 64 KiB and would stall a long packet until the timeout killed it.
    """
    prompt = build_plan_prompt(claim, claim["linear_id"])
    with tempfile.TemporaryDirectory(prefix="mesh-plan-") as cwd, \
            tempfile.TemporaryFile("w+b") as out:
        try:
            proc = subprocess.Popen(agent_argv(rt.AGENT_CMD, prompt), cwd=cwd, stdout=out)
            rt._wait_for_agent(proc, plan)
        except Exception as exc:  # noqa: BLE001
            plan.update(state="failed", error=str(exc))
            return ""
        out.seek(0)
        return out.read().decode("utf-8", errors="replace")


def _write_packet(linear_id: str, text: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9-]", "", linear_id) or "unknown"
    PACKET_DIR.mkdir(parents=True, exist_ok=True)
    path = PACKET_DIR / f"{date.today().isoformat()}-{safe_id}-packet.md"
    path.write_text(text, encoding="utf-8")
    return path


def _settle(plan: dict, linear_id: str, stdout: str) -> None:
    """Turn an empty result into a failure, and save whatever packet there is."""
    if plan.get("state") == "done" and not stdout.strip():
        plan.update(state="failed", error="agent produced no packet (empty stdout)")
    if not stdout.strip():
        return
    try:
        plan["packet_path"] = str(_write_packet(linear_id, stdout))
    except OSError as exc:
        plan.update(state="failed", error=f"packet not saved: {exc}")


def run_plan_claim(claim: dict, rt) -> dict:
    """Review one idea without touching a repository, then report the claim."""
    linear_id = claim["linear_id"]
    plan = {"linear_id": linear_id, "lane": "plan", "agent": rt.AGENT_CMD}
    rt.write_state(linear_id, "working", session_id=uuid.uuid4().hex[:8])
    rt._api("POST", _UPDATE, {"linear_id": linear_id, "state": "working"})
    stdout = _run_agent(claim, plan, rt)
    if plan.get("state") == "released":  # HARD_STOP: hand the ticket back, as build does
        rt._api("POST", _UPDATE, {"linear_id": linear_id, "state": "released"})
        rt.write_state(None, "idle")
        return plan
    _settle(plan, linear_id, stdout)
    if plan.get("state") != "done":
        return rt._fail_claim(plan, linear_id, "", plan.get("error") or "plan lane failed")
    rt._api("POST", _UPDATE, {
        "linear_id": linear_id, "state": "done",
        "packet_md": stdout[:PACKET_MAX_CHARS], "title": claim.get("title") or ""})
    rt.write_state(None, "idle")
    return plan
