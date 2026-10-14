"""A mesh run's journal: what it holds, written before it acts, so a dead run is found (UNI-2963).

Durable Agent Harness slice 1. A runner killed with SIGKILL, or a machine that lost
power, never reaches `run_claim`'s finally. Its claim then sat `working` for good:
the server reaper skips any machine whose heartbeat daemon is fresh, and
`fleet_state.my_claims` only hands back `claimed` rows. The agent's uncommitted
work sat in a temp worktree nobody would look at again.

So each run writes `<state dir>/mesh-runs/<run_id>.json` (beside its log, 0600)
BEFORE it reports `working`, and a run whose journal cannot be written never reports
`working` at all. The journal holds claim id, ticket, branch, worktree, repo, host and
the runner's pid. A heartbeat thread refreshes `ts` and records the agent's pid and
process group the moment it has one; a failed heartbeat write is reported on stderr.
The journal is deleted only once the server has accepted the claim's terminal update,
and never brought back by a late heartbeat. No schema change.

`reconcile` runs when a runner starts. A journal is an orphan only when its runner pid
is PROVEN dead and its agent's process group is PROVEN empty. `ts` is never evidence of
death (review r1: a live runner whose writes failed was released), and a run with no
recorded process group is held, because a dead direct pid says nothing about what it
started. Anything unknown counts as alive, as in left_running.py. An orphan's work is
first kept on a ref named after the run's own branch (ship_run.keep); only once that is
verified is the worktree removed and the claim reported `released` with its claim id
and host. Work that could not be kept keeps its claim, worktree and journal.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import claim_lifecycle
import left_running
import ship_run
from run_settle import Outcome, replay, settling  # noqa: F401 — Outcome for runner.py

BEAT_SECONDS = float(os.environ.get("MESH_RUN_BEAT_S", "5"))
RECONCILE_EVERY_S = float(os.environ.get("MESH_RECONCILE_EVERY_S", "300"))  # retry of held settlements
_FIRST_BEAT = 0.05  # until the agent's pid is recorded: keeps the unrecorded window tiny
_RUN_ID = re.compile(r"[0-9a-f]{8}")
_FIELDS = ("linear_id", "claim_id", "branch", "repo_dir", "worktree", "host")
_UPDATE = "/api/mesh/claim/update"


def path(base_dir: Path, run_id: str) -> Path:
    return Path(base_dir) / "mesh-runs" / f"{run_id}.json"


def write(base_dir: Path, run_id: str, entry: dict) -> bool:
    """Replace the journal atomically, owner-only. Never raises; False means not written."""
    target = path(base_dir, run_id)
    tmp = target.with_name(f".{run_id}.json.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(entry))
            fh.flush()
            os.fsync(fh.fileno())  # r4: the bytes, then the rename, must survive a power cut
        os.replace(tmp, target)
        _fsync_dir(target.parent)
        return True
    except Exception:  # noqa: BLE001 — any failure, including a planted link at tmp
        return False


def _fsync_dir(directory: Path) -> None:
    """Make the rename durable. Windows cannot open a directory; there the replace stands alone."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


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
        self.ok, self.cleared, self.write_failures = True, False, 0
        self._halt, self._lock = threading.Event(), threading.Lock()
        self._thread = threading.Thread(target=self._loop, name=f"mesh-beat-{run_id}", daemon=True)

    def mark(self, phase: str) -> bool:
        """Record the run's phase synchronously; True only once it is on disk."""
        with self._lock:
            self.entry["phase"] = phase
        return self.beat()

    def note(self, **fields: Any) -> bool:
        """Add fields to the journal synchronously; True only once they are on disk."""
        with self._lock:
            self.entry.update(fields)
        return self.beat()

    def launching(self) -> None:
        """The checked precondition of starting the agent (review r2 P0): the journal must say
        `launching` on disk first, or a later reconcile could take a live agent for one that
        never started. Raising here fails the run before Popen."""
        if not self.mark("launching"):
            raise RuntimeError("run journal unwritable at launch; the agent was not started")

    def beat(self) -> bool:
        """One heartbeat. Locked: the thread, `mark` and `clear` share the entry and the file."""
        with self._lock:
            if self.cleared:
                return False  # review r1: a late write must never bring a cleared journal back
            rec = self.held[0] if self.held else None
            pid = getattr(getattr(rec, "proc", None), "pid", None)
            if isinstance(pid, int):
                self.entry.update(agent_pid=pid, agent_pgid=getattr(rec, "pgid", None), phase="agent")
            self.entry["ts"] = time.time()
            if write(self.base_dir, self.run_id, dict(self.entry)):
                return True
            self.write_failures += 1
            if self.write_failures % 60 == 1:
                print(f"mesh: run {self.run_id} heartbeat could not write its journal "
                      f"({self.write_failures} failures)", file=sys.stderr)
            return False

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
        """Stop beating and delete the journal. Under the write lock, so no write in flight can
        land after the unlink; a lock that cannot be had keeps the journal (fail toward retry)."""
        self.stop()
        if not self._lock.acquire(timeout=BEAT_SECONDS + 5):
            print(f"mesh: run {self.run_id} journal kept: its heartbeat is stuck in a write", file=sys.stderr)
            return
        try:
            self.cleared = True
            clear(self.base_dir, self.run_id)
        finally:
            self._lock.release()


def start(base_dir: Path, run_id: str, plan: dict, host: str, worktree: Path) -> Beat:
    """Write the journal (journal before act), then start its heartbeat. `ok` is False when the
    first write failed: the caller must not report `working` then. Never raises an Exception."""
    entry = {**{k: plan.get(k) for k in _FIELDS}, "host": host, "worktree": str(worktree),
             "run_id": run_id, "owner_pid": os.getpid(), "phase": "preparing", "ts": time.time()}
    beat = Beat(base_dir, run_id, entry)
    beat.ok = write(base_dir, run_id, entry)
    if beat.ok:
        try:
            beat._thread.start()
        except RuntimeError:  # no thread to spare: the journal still exists, it just stops ageing
            pass
    return beat


def keep_wip(plan: dict, worktree: Path, host: str, shipper: Any = ship_run) -> Optional[str]:
    """Keep what a run that did not end `done` left, on a ref named after its own branch,
    before the worktree goes (ship_run.keep). `done` already shipped. None means kept or
    nothing to keep; anything else means hold the claim. Never raises an Exception."""
    if plan.get("state") == "done":
        return None
    try:
        return shipper.keep(Path(worktree), plan.get("branch") or "", plan.get("linear_id") or "?",
                             host, f"WIP, mesh run ended {plan.get('state') or 'unknown'}")
    except Exception as exc:  # noqa: BLE001 — git missing, timed out, or a faked subprocess
        return f"wip commit raised {type(exc).__name__}"


def _pid(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def blocker(entry: dict, host: str, own: bool = False) -> str:
    """Why this journal must be left alone, or "" when its run is provably dead. `own` lets the
    runner's loop settle its own earlier runs: between claims none of them is in flight."""
    if entry.get("host") != host:
        return "another host"
    if not all(isinstance(entry.get(k), str) and entry[k] for k in _FIELDS):
        return "incomplete journal"
    if not entry["branch"].startswith("mesh/"):
        return "not a mesh branch"
    owner = _pid(entry.get("owner_pid"))
    if owner == os.getpid() and not own:
        return "this runner's own run"
    if owner is None or (owner != os.getpid() and left_running._alive(owner)):  # a live pid always wins, whatever `ts` says
        return "runner alive"
    pid, pgid = entry.get("agent_pid"), entry.get("agent_pgid")
    if pid is None and pgid is None:  # review r2 P0: `preparing` too; uncertain is not dead
        return "agent may be running unrecorded"
    if _pid(pgid) is None:  # review r1: a dead pid says nothing about what it started
        return "no process group to prove the agent's descendants gone"
    if left_running._group_alive(pgid):
        return "agent group alive"
    if _pid(pid) is None or left_running._alive(pid):
        return "agent alive"
    return ""


def settle_orphan(base_dir: Path, entry: dict, api: Callable[..., Any], pause: float) -> dict:
    """Keep a dead run's work, and only then remove its worktree and release its claim. The
    journal goes once the server accepted the release; until then the next start retries."""
    worktree = Path(entry["worktree"])
    result = {"linear_id": entry["linear_id"], "claim_id": entry["claim_id"],
              "branch": entry["branch"], "released": False, "wip_error": None}
    result["wip_error"] = keep_wip({"state": "orphaned", "linear_id": entry["linear_id"],
                                    "branch": entry["branch"]}, worktree, entry["host"])
    if result["wip_error"] is not None:
        return result  # review r1: never release a claim whose work was not kept
    if not claim_lifecycle.remove_worktree(Path(entry["repo_dir"]), worktree):
        result["held"] = "worktree remove failed"  # review r2 P1: never release over a leftover
        return result
    payload = replay(entry) or {  # r4: the ending's own update; a bare release only if none
        "linear_id": entry["linear_id"], "state": "released", "branch": entry["branch"],
        "host": entry["host"], "claim_id": entry["claim_id"], "run_id": entry["run_id"]}
    result["released"] = claim_lifecycle.report(lambda: api("POST", _UPDATE, payload), pause)
    if result["released"]:
        clear(base_dir, entry["run_id"])
    return result


def _one(base_dir: Path, p: Path, host: str, api: Callable[..., Any], pause: float, own: bool) -> dict:
    with settling(p) as mine:
        if not mine:
            return {"journal": p.name, "held": "being settled elsewhere"}
        try:  # read under the lock: another runner may have settled it meanwhile
            entry = json.loads(p.read_text())
        except (OSError, ValueError):
            return {"journal": p.name, "held": "unreadable or already settled"}
        if not isinstance(entry, dict) or entry.get("run_id") != p.stem:
            return {"journal": p.name, "held": "malformed"}
        why = blocker(entry, host, own)
        if why:
            return {"journal": p.name, "held": why}
        result = settle_orphan(base_dir, entry, api, pause)
        if not p.exists():  # settled: drop the lock file too, while still holding it (r2 P2)
            p.with_suffix(".lock").unlink(missing_ok=True)
        return result


def reconcile(base_dir: Path, host: str, api: Callable[..., Any], pause: float = 1.0,
              own: bool = False) -> list[dict]:
    """Settle every orphaned run this machine journaled. Returns one line per journal acted on
    or held, so the runner can log why a claim was left `working`. One bad journal never
    stops the others."""
    out: list[dict] = []
    for p in sorted((Path(base_dir) / "mesh-runs").glob("*.json")):
        if not _RUN_ID.fullmatch(p.stem):
            continue
        try:
            out.append(_one(base_dir, p, host, api, pause, own))
        except Exception as exc:  # noqa: BLE001 — held, and the next journal still runs
            out.append({"journal": p.name, "held": f"reconcile raised {type(exc).__name__}"})
    return out


class Ticker:
    """The runner's reconcile: at startup, then again at most every RECONCILE_EVERY_S from the
    poll loop, so a settlement held by a transient failure is retried while the runner lives
    (review r2 P1), not only at its next restart. Called with the runner's globals as `rt`
    (as runner_idle takes them), between claims, so the runner's own journals count too. Not
    under HARD_STOP, which means do nothing, nor on a dry run. Never stops the runner."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock, self._last = clock, None

    def __call__(self, rt: Any, dry_run: bool) -> None:
        now = self._clock()
        if dry_run or rt.killed() or (self._last is not None and now - self._last < RECONCILE_EVERY_S):
            return
        first, self._last = self._last is None, now
        try:
            settled = reconcile(rt.STATE_FILE.parent, rt.HOST, rt._api, own=True)
        except Exception as exc:  # noqa: BLE001 — a broken journal dir must not keep the node down
            settled = [{"held": f"reconcile raised {type(exc).__name__}"}]
        if settled and (first or any("released" in r for r in settled)):
            print(rt.LOG.line(None, runner=rt.HOST, status="RECONCILED", runs=settled), flush=True)
