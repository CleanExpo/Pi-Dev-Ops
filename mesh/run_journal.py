"""A mesh run's journal: what it holds, written before it acts, so a dead run is found (UNI-2963).

Durable Agent Harness slice 1. A runner killed with SIGKILL, or a machine that lost
power, never reaches `run_claim`'s finally. Its claim then sat `working` for good:
the server reaper skips any machine whose heartbeat daemon is fresh, and
`fleet_state.my_claims` only hands back `claimed` rows. The agent's uncommitted
work sat in a temp worktree nobody would look at again.

So each run writes `<state dir>/mesh-runs/<run_id>.json` (beside its log, 0600)
BEFORE it reports `working`: claim id, ticket, branch, worktree, repo, host and the
runner's pid. A heartbeat thread refreshes `ts` while the run lasts and records the
agent's pid and process group the moment it has one. The journal is deleted only
once the server has accepted the claim's terminal update. No schema change: the
heartbeat lives on this machine, which is the only place a run can be resumed from.

`reconcile` runs when a runner starts. A journal whose runner is gone (pid proven
dead, or a heartbeat older than STALE_SECONDS, which also covers a pid reused after a
reboot) AND whose agent is proven gone is an orphan: its work is committed on the
run's own branch, the worktree removed, and the claim reported `released` with its
claim id and host, which returns the ticket to the pool. Anything unknown counts as
alive, as in left_running.py: an agent that may still be writing keeps its claim.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import claim_lifecycle
import left_running
import ship_run

STALE_SECONDS = float(os.environ.get("MESH_RUN_STALE_S", "1800"))  # beyond any ship/report window
BEAT_SECONDS = float(os.environ.get("MESH_RUN_BEAT_S", "5"))
_FIRST_BEAT = 0.05  # until the agent's pid is recorded: keeps the unrecorded window tiny
_RUN_ID = re.compile(r"[0-9a-f]{8}")
_FIELDS = ("linear_id", "claim_id", "branch", "repo_dir", "worktree", "host")
_UPDATE = "/api/mesh/claim/update"


def path(base_dir: Path, run_id: str) -> Path:
    return Path(base_dir) / "mesh-runs" / f"{run_id}.json"


def write(base_dir: Path, run_id: str, entry: dict) -> bool:
    """Replace the journal atomically, owner-only. Never raises: a journal that cannot be
    written costs the run its recovery, never the run itself."""
    target = path(base_dir, run_id)
    tmp = target.with_name(f".{run_id}.json.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(entry))
        os.replace(tmp, target)
        return True
    except Exception:  # noqa: BLE001 — any failure, including a planted link at tmp
        return False


def clear(base_dir: Path, run_id: str) -> None:
    try:
        path(base_dir, run_id).unlink(missing_ok=True)
    except OSError:
        pass


class Beat:
    """The run's heartbeat: the journal's `ts` plus the agent's pid/pgid, every BEAT_SECONDS."""

    def __init__(self, base_dir: Path, run_id: str, entry: dict):
        self.base_dir, self.run_id, self.entry = base_dir, run_id, entry
        self.held: list = []  # run_agent's RunRecord, kept even when an interrupt escapes run_agent
        self._halt, self._lock = threading.Event(), threading.Lock()
        self._thread = threading.Thread(target=self._loop, name=f"mesh-beat-{run_id}", daemon=True)

    def mark(self, phase: str) -> None:
        """Record the run's phase synchronously: `launching` is written before the agent starts."""
        with self._lock:
            self.entry["phase"] = phase
        self.beat()

    def beat(self) -> None:
        """One heartbeat. Locked: the thread and `mark` share the entry and the temp file."""
        with self._lock:
            rec = self.held[0] if self.held else None
            pid = getattr(getattr(rec, "proc", None), "pid", None)
            if isinstance(pid, int):
                self.entry.update(agent_pid=pid, agent_pgid=getattr(rec, "pgid", None), phase="agent")
            self.entry["ts"] = time.time()
            write(self.base_dir, self.run_id, dict(self.entry))

    def _loop(self) -> None:
        while not self._halt.wait(BEAT_SECONDS if "agent_pid" in self.entry else _FIRST_BEAT):
            try:
                self.beat()
            except Exception:  # noqa: BLE001 — a heartbeat never takes the run down
                pass

    def stop(self) -> None:
        self._halt.set()
        if self._thread.is_alive():
            self._thread.join(timeout=BEAT_SECONDS + 1)

    def clear(self) -> None:
        self.stop()
        clear(self.base_dir, self.run_id)


def start(base_dir: Path, run_id: str, plan: dict, host: str, worktree: Path) -> Beat:
    """Write the journal (journal before act), then start its heartbeat. Never raises an Exception."""
    entry = {**{k: plan.get(k) for k in _FIELDS}, "host": host, "worktree": str(worktree),
             "run_id": run_id, "owner_pid": os.getpid(), "phase": "preparing", "ts": time.time()}
    beat = Beat(base_dir, run_id, entry)
    write(base_dir, run_id, entry)
    try:
        beat._thread.start()
    except RuntimeError:  # no thread to spare: the journal still exists, it just stops ageing
        pass
    return beat


def keep_wip(plan: dict, worktree: Path, host: str) -> Optional[str]:
    """Commit what a run that did not end `done` left uncommitted, on its own branch, before
    the worktree is force-removed. `done` already committed in ship_run.settle. Never raises
    an Exception: the claim must still end. Returns why nothing was kept, or None."""
    state = plan.get("state")
    if state == "done" or not Path(worktree).is_dir():
        return None
    try:
        return ship_run.commit_leftovers(Path(worktree), plan.get("linear_id") or "?", host,
                                         f"WIP, mesh run ended {state or 'unknown'}")
    except Exception as exc:  # noqa: BLE001 — git missing, timed out, or a faked subprocess
        return f"wip commit raised {type(exc).__name__}"


def blocker(entry: dict, host: str, now: float) -> str:
    """Why this journal must be left alone, or "" when its run is provably dead."""
    if entry.get("host") != host:
        return "another host"
    if not all(isinstance(entry.get(k), str) and entry[k] for k in _FIELDS):
        return "incomplete journal"
    if not entry["branch"].startswith("mesh/"):
        return "not a mesh branch"
    owner = entry.get("owner_pid")
    if owner == os.getpid():
        return "this runner's own run"
    fresh = now - float(entry.get("ts") or 0) <= STALE_SECONDS
    if fresh and (not isinstance(owner, int) or left_running._alive(owner)):
        return "runner alive"
    return _agent_blocker(entry)


def _agent_blocker(entry: dict) -> str:
    pid, pgid = entry.get("agent_pid"), entry.get("agent_pgid")
    if pid is None and pgid is None:
        return "" if entry.get("phase") == "preparing" else "agent may be running unrecorded"
    if isinstance(pgid, int) and left_running._group_alive(pgid):
        return "agent group alive"
    if not isinstance(pid, int) or left_running._alive(pid):
        return "agent alive"
    return ""


def settle_orphan(base_dir: Path, entry: dict, api: Callable[..., Any], pause: float) -> dict:
    """Keep a dead run's work, then release its claim. The journal goes only once the
    server accepted the release; until then the next start retries it."""
    worktree = Path(entry["worktree"])
    error = keep_wip({"state": "orphaned", "linear_id": entry["linear_id"]}, worktree, entry["host"])
    accepted = claim_lifecycle.report(lambda: api("POST", _UPDATE, {
        "linear_id": entry["linear_id"], "state": "released", "branch": entry["branch"],
        "host": entry["host"], "claim_id": entry["claim_id"], "run_id": entry["run_id"]}), pause)
    if error is None:
        claim_lifecycle.remove_worktree(Path(entry["repo_dir"]), worktree)
        if accepted:
            clear(base_dir, entry["run_id"])
    return {"linear_id": entry["linear_id"], "claim_id": entry["claim_id"],
            "branch": entry["branch"], "released": accepted, "wip_error": error}


def reconcile(base_dir: Path, host: str, api: Callable[..., Any], pause: float = 1.0) -> list[dict]:
    """Settle every orphaned run this machine journaled. Returns one line per journal acted on
    or held, so the runner can log why a claim was left `working`."""
    out: list[dict] = []
    for p in sorted((Path(base_dir) / "mesh-runs").glob("*.json")):
        if not _RUN_ID.fullmatch(p.stem):
            continue
        try:
            entry = json.loads(p.read_text())
        except (OSError, ValueError):
            out.append({"journal": p.name, "held": "unreadable"})
            continue
        if not isinstance(entry, dict) or entry.get("run_id") != p.stem:
            out.append({"journal": p.name, "held": "malformed"})
            continue
        why = blocker(entry, host, time.time())
        if why:
            out.append({"journal": p.name, "held": why})
        else:
            out.append(settle_orphan(base_dir, entry, api, pause))
    return out


def on_start(rt: Any, dry_run: bool) -> None:
    """The runner's startup reconcile, given its globals as `rt` (as runner_idle takes them).
    Not under HARD_STOP, which means do nothing, nor on a dry run."""
    if dry_run or rt.killed():
        return
    settled = reconcile(rt.STATE_FILE.parent, rt.HOST, rt._api)
    if settled:
        print(rt.LOG.line(None, runner=rt.HOST, status="RECONCILED", runs=settled), flush=True)
