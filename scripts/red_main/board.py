"""Board rows for red mains (RA-8174). Pure functions over the parsed ops/jobs.json.

One card per repo, id W-MAIN-RED-<repo>. A red episode opens it; green closes it and
resumes every job parked on that repo (field `waits_for_main`). UNKNOWN changes
nothing but a note: an unread repo never closes a card and never resumes a job.
"""
from __future__ import annotations

import datetime

from red_main.common import FAIL, OK, UNKNOWN, card_id, short, stamp

PARKED_STATES = {"parked", "blocked", "waiting"}


def _jobs(d: dict) -> dict:
    return {j.get("id"): j for j in d.get("jobs", []) if isinstance(j, dict)}


def open_card(d: dict, repo: str, info: dict, at: datetime.datetime) -> dict:
    """Create or reopen the repo's card for a new red episode (no owner yet)."""
    episode = at.strftime("%Y%m%d%H%M")
    card = _jobs(d).get(card_id(repo))
    fresh = {"title": f"RED MAIN: {repo} {info.get('branch', 'main')} is red", "status": "open",
             "priority": "P0", "repo": repo, "branch": info.get("branch", "main"),
             "failing": info.get("failing", []), "red_since": info.get("since"), "episode": episode,
             "fix_branch": f"fix/red-main-{episode}", "launches": 0, "lane": None, "owner": None,
             "claimed_by": None, "linear": None, "check_state": FAIL, "unknown_since": None,
             "escalated": None, "updated": stamp(at), "note": f"Red main detected {stamp(at)} by red-main watcher."}
    if card is None:
        card = {"id": card_id(repo), "created": stamp(at), **fresh}
        d.setdefault("jobs", []).append(card)
    else:
        card.update(fresh)
    return card


def resume_parked(d: dict, repo: str, at: datetime.datetime) -> list[str]:
    """Jobs whose waits_for_main names this repo go back to the status they parked from."""
    names = {repo, short(repo)}
    resumed = []
    for j in d.get("jobs", []):
        if not isinstance(j, dict) or j.get("waits_for_main") not in names or j.get("status") == "done":
            continue
        j["status"] = j.pop("parked_from_status", None) or "todo"
        j.pop("waits_for_main", None)
        j["blocker"] = ""
        j["note"] = (str(j.get("note") or "") + f" | Resumed {stamp(at)}: {repo} main is green.").strip(" |")
        j["updated"] = stamp(at)
        resumed.append(j.get("id"))
    return resumed


def reconcile(d: dict, results: dict, at: datetime.datetime) -> bool:
    """Apply one scan. results = {repo: (state, info)}. True if anything changed."""
    changed, jobs = False, _jobs(d)
    for repo, (state, info) in results.items():
        card = jobs.get(card_id(repo))
        live = card is not None and card.get("status") != "done"
        if state == OK:
            if live:
                card.update({"status": "done", "check_state": OK, "updated": stamp(at), "unknown_since": None,
                             "result": f"Green at {stamp(at)}.", "blocker": ""})
                changed = True
            changed = bool(resume_parked(d, repo, at)) or changed
        elif state == FAIL:
            if not live:
                open_card(d, repo, info, at)
            elif card.get("failing") != info.get("failing") or card.get("check_state") != FAIL:
                card.update({"failing": info.get("failing", []), "check_state": FAIL,
                             "unknown_since": None, "updated": stamp(at)})
            else:
                continue
            changed = True
        elif state == UNKNOWN and live and not card.get("unknown_since"):
            card.update({"unknown_since": stamp(at), "check_note": info.get("reason", "")})
            changed = True
    return changed


def claim(d: dict, repo: str, linear: str, who: str, at: datetime.datetime) -> bool:
    """The lane's claim: the board rule needs a Linear id before a card is `doing`."""
    card = _jobs(d).get(card_id(repo))
    if card is None or card.get("status") == "done" or not linear.strip() or not who.strip():
        return False
    card.update({"status": "doing", "linear": linear.strip(), "claimed_by": f"{who.strip()} {stamp(at)}",
                 "owner": who.strip(), "updated": stamp(at)})
    return True


def park(d: dict, job_id: str, repo: str, at: datetime.datetime) -> bool:
    """Park a job on a red main; it resumes by itself when that main is green."""
    job = _jobs(d).get(job_id)
    if job is None or job.get("status") == "done":
        return False
    if job.get("waits_for_main") is None:
        job["parked_from_status"] = job.get("status")
    job.update({"waits_for_main": repo, "status": "parked", "updated": stamp(at),
                "blocker": f"Parked on red main {repo} ({card_id(repo)}); resumes when it is green."})
    return True


def live_red_cards(d: dict) -> list[dict]:
    return [j for j in d.get("jobs", []) if isinstance(j, dict) and str(j.get("id", "")).startswith("W-MAIN-RED-")
            and j.get("status") != "done" and j.get("check_state") == FAIL]
