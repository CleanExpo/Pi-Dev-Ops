"""What the watcher does for each live red-main card, outside the board lock (RA-8174).

decide() is pure: given the card, the lane's state and the fix branch's state it names
one action. run() probes hosts and GitHub, performs the action, and returns the card
fields to write back under the lock.
"""
from __future__ import annotations

import datetime
import os

from red_main import brief, lanes
from red_main.common import gh_json, max_launches, minutes_since, parse_time, stamp

ALIVE = {"queued", "running"}
STARTUP = datetime.timedelta(minutes=5)   # run.sh writes its first status within seconds


def launching_enabled() -> bool:
    return os.environ.get("RED_MAIN_LAUNCH", "0") == "1"


def pushed_without_pr(repo: str, fix: str, at: datetime.datetime) -> tuple[int | None, str]:
    """(minutes since the fix branch's head commit, reason). None = not pushed, has a PR, or unknown."""
    data, why = gh_json("api", f"repos/{repo}/branches/{fix}")
    if not isinstance(data, dict):
        return None, "" if "404" in why or "Not Found" in why else f"fix branch unreadable: {why}"
    when = (((data.get("commit") or {}).get("commit") or {}).get("committer") or {}).get("date")
    prs, why = gh_json("pr", "list", "-R", repo, "--head", fix, "--state", "all", "--json", "number")
    if not isinstance(prs, list):
        return None, f"PR list unreadable: {why}"
    return (None, "") if prs else (minutes_since(when, at), "")


def lane_alive(card: dict, state: str | None, at: datetime.datetime) -> bool:
    """True while a prior lane still owns the episode.

    queued/running → alive. Unreadable probe (None) or missing status
    ("state-missing") → also alive: during STARTUP that is expected; after
    STARTUP it means we cannot prove the lane ended, so we must not start a
    second concurrent fix. Only a readable terminal status (finished,
    REFUSED, …) returns False and allows relaunch.
    """
    if state in ALIVE:
        return True
    if state in (None, "state-missing"):
        return True
    return False


def decide(card: dict, alive: bool, pushed_min: int | None, grace_min: int) -> str:
    """launch | relaunch-pr | relaunch | flag-no-pr | exhausted | wait."""
    lane, room = card.get("lane"), int(card.get("launches") or 0) < max_launches()
    if not lane:
        return "launch" if room else "exhausted"
    late_pr = pushed_min is not None and pushed_min >= grace_min
    if alive:
        return "flag-no-pr" if late_pr else "wait"
    if not room:
        return "exhausted"
    return "relaunch-pr" if pushed_min is not None else "relaunch"


def _start(card: dict, at: datetime.datetime, pr_only: bool) -> dict:
    attempt = int(card.get("launches") or 0) + 1
    if not launching_enabled():
        return {"note": f"{stamp(at)} lane needed (attempt {attempt}) but RED_MAIN_LAUNCH is off."}
    loads = [(name, via, lanes.busy(via)) for name, via in lanes.hosts()]
    choice = lanes.pick(loads)
    if choice is None:
        return {"owner": None, "note": f"{stamp(at)} no host could take a lane: {loads}"}
    name, via = choice
    ok, where = lanes.launch(via, lanes.lane_name(card["repo"], card["episode"], attempt),
                             brief.build(card, pr_only=pr_only, on_board_host=via == "local"))
    if not ok:
        return {"owner": None, "note": f"{stamp(at)} lane launch on {name} failed: {where}"}
    return {"launches": attempt, "owner": f"red-main lane on {name} ({where})",
            "lane": {"host": name, "via": via, "dir": where, "launched_at": stamp(at), "attempt": attempt,
                     "loads": {n: b for n, _, b in loads}},
            "note": f"{stamp(at)} lane {attempt} started on {name} (least busy of {[(n, b) for n, _, b in loads]})."}


def run(card: dict, at: datetime.datetime, grace_min: int, may_launch: bool = True) -> dict:
    """Fields to merge into the card (empty when nothing changes). may_launch=False: the
    cycle's lane budget is spent, so a card that needs a lane waits (and stays unowned)."""
    lane = card.get("lane") or {}
    state = lanes.lane_state(lane.get("via", ""), lane.get("dir", "")) if lane else None
    pushed, why = pushed_without_pr(card["repo"], card["fix_branch"], at) if lane else (None, "")
    if why:
        return {"check_note": f"{stamp(at)} {why}"}
    alive = lane_alive(card, state, at)
    # After STARTUP, an unreadable status is not "dead": keep the owner and wait.
    if lane and state in (None, "state-missing"):
        launched = parse_time(lane.get("launched_at"))
        if launched is not None and at - launched >= STARTUP and alive:
            note = f"{stamp(at)} lane state unreadable ({state!r}); waiting (no second lane)."
            # Still run decide so flag-no-pr / wait behave; merge the note.
            action = decide(card, alive, pushed, grace_min)
            if action in ("launch", "relaunch", "relaunch-pr"):
                return {"check_note": note}  # belt: should not happen while alive
            if action == "flag-no-pr":
                return {"pr_overdue": f"{card['fix_branch']} pushed {pushed} min ago with no PR; lane still running",
                        "check_note": note}
            return {"check_note": note}
    action = decide(card, alive, pushed, grace_min)
    if action in ("launch", "relaunch", "relaunch-pr"):
        if not may_launch:
            return {}
        return _start(card, at, pr_only=action == "relaunch-pr")
    if action == "flag-no-pr":
        return {"pr_overdue": f"{card['fix_branch']} pushed {pushed} min ago with no PR; lane still running"}
    if action == "exhausted" and card.get("owner"):
        return {"owner": None, "claimed_by": None, "note": f"{stamp(at)} {card.get('launches')} lanes ended and main is still red: "
                                       "needs the lead. Unowned from now."}
    return {}

