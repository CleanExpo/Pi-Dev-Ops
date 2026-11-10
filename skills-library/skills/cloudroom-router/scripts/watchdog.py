#!/usr/bin/env python3
"""watchdog.py: flag router workers that are stuck, silent, finished-but-unreviewed or lost.

Runs as a Cloudroom Loop script every 10 minutes (SKILL.md has the exact command). The
router only hears from a worker when the worker speaks, so a silent worker is invisible
without this. Stdlib only, one self-contained file: a loop stores a private copy of it.

    watchdog.py --router thr_X --tickets specs/tickets [--stall-min 20] [--json]
    watchdog.py ... --input threads.json --now-ms 1792000000000     # offline, for tests

A loop script takes no arguments, so every option also reads an environment variable:
ROUTER_THREAD_ID, ROUTER_TICKETS, ROUTER_STALL_MIN, ROUTER_NOTIFY, ROUTER_STATE, ROUTER_RENOTIFY_MIN.

Flags, one line each (a thread gets at most one; the first that applies wins):
  FAILED               worker thread status is error/failed
  WAITING_HUMAN        worker has a pending interaction (a question or permission prompt)
  STALLED              worker is active and its last update is older than --stall-min
  FINISHED_UNREVIEWED  worker is idle and the ticket's status file still says doing
  ORPHAN               status file says doing, but the worker thread is not in the open list

Exit codes: 0 clean (no output), 1 flags printed, 2 UNKNOWN: the read could not be trusted
(room-cli failed, empty or malformed output, router thread missing from the list, tickets
folder unreadable) or --notify could not reach the router. UNKNOWN is never "all clear".

--notify (a script loop has no agent to speak for it): when flags exist, queue one message
to the router thread (`room-cli thread queue create ... --json`) and exit 0. `create` alone is
right: on an idle router it is delivered at once (a following `queue send` would 404), on a busy
one it waits in the queue and is delivered when the router goes idle. The same flag set is not
sent again for --renotify-min (default 60) so a worker that stays stuck does not spam the router
every 10 minutes; a changed set is sent at once, and a clean run forgets the state. A failed
create is UNKNOWN (exit 2) and is retried next tick.

The board it reads is the tickets folder: each ticket's `status` file (router-owned, written by
board.py). board.md is a generated view and is never read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

FAILED_STATES = {"error", "failed"}


class Unknown(Exception):
    """The inputs cannot support a verdict. Printed as UNKNOWN, exit 2."""


def read_threads(input_path: str | None) -> list[dict]:
    if input_path:
        try:
            with open(input_path, encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            raise Unknown(f"cannot read --input {input_path}: {e}")
        source = f"--input {input_path}"
    else:
        cli = os.environ.get("ROOM_CLI") or "room-cli"
        try:
            p = subprocess.run([cli, "thread", "list", "--json"], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise Unknown(f"room-cli thread list failed to run: {e}")
        if p.returncode != 0:
            raise Unknown(f"room-cli thread list exited {p.returncode}: {p.stderr.strip()[:200]}")
        raw = p.stdout
        source = "room-cli thread list"
    if not raw.strip():
        raise Unknown(f"{source} returned no output")
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise Unknown(f"{source} is not JSON: {e}")
    if not isinstance(data, list) or not data:
        raise Unknown(f"{source} is not a non-empty list of threads")
    for i, t in enumerate(data):
        if not isinstance(t, dict) or not isinstance(t.get("id"), str) or not isinstance(t.get("status"), str):
            raise Unknown(f"{source}: entry {i} has no string id/status")
    return data


def read_board_doing(tickets_dir: str) -> dict[str, str]:
    """{ticket id: worker thread id} for every ticket whose status file says doing.

    Reads the router-owned `status` files, never board.md (a generated view). One line:
    `<state> [worker=thr_x] [was=<state>]`.
    """
    root = os.path.abspath(tickets_dir)
    try:
        names = sorted(n for n in os.listdir(root) if re.match(r"^\d+-", n) and os.path.isdir(os.path.join(root, n)))
    except OSError as e:
        raise Unknown(f"cannot read tickets folder {tickets_dir}: {e}")
    if not names:
        raise Unknown(f"no ticket folders (NNN-slug) in {tickets_dir}; wrong path?")
    doing: dict[str, str] = {}
    for n in names:
        path = os.path.join(root, n, "status")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                parts = f.read().split()
        except OSError as e:
            raise Unknown(f"cannot read {n}/status: {e}")
        if not parts:
            raise Unknown(f"{n}/status is empty")
        if parts[0] == "doing":
            worker = next((p[7:] for p in parts[1:] if p.startswith("worker=")), "")
            doing[n.split("-")[0]] = worker
    return doing


def evaluate(threads: list[dict], router: str, doing: dict[str, str], now_ms: int, stall_min: float) -> list[dict]:
    by_id = {t["id"]: t for t in threads}
    if router not in by_id:
        raise Unknown(f"router thread {router} is not in the open thread list "
                      f"(wrong id, archived, or a partial read); refusing to report all clear")
    ticket_of = {w: tid for tid, w in doing.items() if w}
    flags: list[dict] = []

    def add(kind: str, thread: str, detail: str) -> None:
        flags.append({"kind": kind, "thread": thread, "ticket": ticket_of.get(thread, ""), "detail": detail})

    children = [t for t in threads if t.get("parentThreadId") == router]
    for t in children:
        tid, status = t["id"], t["status"]
        runtime_status = (t.get("runtime") or {}).get("displayStatus", "")
        age_min = (now_ms - t["updatedAt"]) / 60000 if isinstance(t.get("updatedAt"), (int, float)) else None
        if status in FAILED_STATES or runtime_status in FAILED_STATES:
            add("FAILED", tid, f"status {status}")
        elif t.get("hasPendingInteraction"):
            add("WAITING_HUMAN", tid, "has a pending question or permission prompt")
        elif status == "active":
            if age_min is None:
                raise Unknown(f"thread {tid} is active but has no numeric updatedAt")
            if age_min > stall_min:
                bg = (t.get("activity") or {}).get("activeBackgroundCommandCount", 0)
                add("STALLED", tid, f"no update for {int(age_min)} min (limit {stall_min:g}); background commands: {bg}")
        elif status == "idle" and tid in ticket_of:
            add("FINISHED_UNREVIEWED", tid, "worker is idle but the board still says doing")
    for ticket, worker in doing.items():
        if not worker:
            flags.append({"kind": "ORPHAN", "thread": "", "ticket": ticket, "detail": "board says doing with no worker id"})
        elif worker not in by_id:
            flags.append({"kind": "ORPHAN", "thread": worker, "ticket": ticket,
                          "detail": "board says doing but the worker thread is not in the open list"})
    return flags


def line(f: dict) -> str:
    who = f["thread"] or "-"
    tk = f" ticket {f['ticket']}" if f["ticket"] else ""
    return f"{f['kind']} {who}{tk}: {f['detail']}"


def _cli() -> str:
    return os.environ.get("ROOM_CLI") or "room-cli"


def _run_cli(args: list[str], what: str) -> str:
    try:
        p = subprocess.run([_cli(), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Unknown(f"could not notify router: {what} failed to run: {e}")
    if p.returncode != 0:
        raise Unknown(f"could not notify router: {what} exited {p.returncode}: {(p.stderr or p.stdout).strip()[:200]}")
    return p.stdout


def signature(flags: list[dict]) -> str:
    """Identity of a flag set. Ignores the detail text: 'no update for 23 min' changes every tick."""
    keys = sorted(f"{f['kind']}|{f['thread']}|{f['ticket']}" for f in flags)
    return hashlib.sha256("\n".join(keys).encode()).hexdigest()


def notify(router: str, flags: list[dict], state_path: str, now_ms: int, renotify_min: float) -> None:
    sig = signature(flags)
    try:
        with open(state_path, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        prev = {}
    if prev.get("sig") == sig and isinstance(prev.get("at"), (int, float)) and (now_ms - prev["at"]) / 60000 < renotify_min:
        return
    body = "\n".join(line(f) for f in flags)
    message = (f"Watchdog: {len(flags)} flag(s) on your workers.\n{body}\n"
               "Handle each per the cloudroom-router skill. Edit no project files.")
    out = _run_cli(["thread", "queue", "create", router, message, "--json"], "queue create")
    try:
        json.loads(out)["id"]
    except (ValueError, KeyError, TypeError):
        raise Unknown(f"could not notify router: queue create returned no message id: {out.strip()[:200]}")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(state_path) or ".", prefix=".wd-state-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"sig": sig, "at": now_ms}, f)
    os.replace(tmp, state_path)


def forget(state_path: str) -> None:
    try:
        os.unlink(state_path)
    except FileNotFoundError:
        pass


def main(argv: list[str] | None = None) -> int:
    env = os.environ
    ap = argparse.ArgumentParser(prog="watchdog.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--router", default=env.get("ROUTER_THREAD_ID"))
    ap.add_argument("--tickets", default=env.get("ROUTER_TICKETS", "specs/tickets"))
    ap.add_argument("--stall-min", type=float, default=float(env.get("ROUTER_STALL_MIN", "20")))
    ap.add_argument("--input", help="read this thread-list JSON instead of calling room-cli")
    ap.add_argument("--now-ms", type=int, help="override the clock (tests)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--notify", action="store_true", default=env.get("ROUTER_NOTIFY") == "1",
                    help="queue the flags to the router thread (queue create); exit 0 once queued")
    ap.add_argument("--state", help="de-duplication state file (default: a file in the temp dir named for the router)")
    ap.add_argument("--renotify-min", type=float, default=float(env.get("ROUTER_RENOTIFY_MIN", "60")))
    args = ap.parse_args(argv)
    try:
        if not args.router:
            raise Unknown("no router thread id: pass --router or set ROUTER_THREAD_ID")
        threads = read_threads(args.input)
        doing = read_board_doing(args.tickets)
        now_ms = args.now_ms if args.now_ms is not None else int(time.time() * 1000)
        flags = evaluate(threads, args.router, doing, now_ms, args.stall_min)
        if args.notify:
            state = args.state or env.get("ROUTER_STATE") or os.path.join(tempfile.gettempdir(), f"router-watchdog-{args.router}.json")
            if flags:
                notify(args.router, flags, state, now_ms, args.renotify_min)
            else:
                forget(state)
    except Unknown as e:
        print(f"UNKNOWN: {e}", file=sys.stderr)
        return 2
    if args.json:
        if flags:
            print(json.dumps({"flags": flags}))
    else:
        for f in flags:
            print(line(f))
    return 0 if (args.notify or not flags) else 1


if __name__ == "__main__":
    sys.exit(main())
