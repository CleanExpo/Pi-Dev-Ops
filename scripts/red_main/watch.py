"""One red-main watcher cycle (RA-8174): read GitHub, update the board, start lanes.

Network reads and lane launches run outside the jobs.json lock; each board write is
a short locked read-modify-write. The whole cycle holds a single-run lock so two
cycles can never both start a lane for the same red episode.
"""
from __future__ import annotations

import datetime
import os

from red_main import actions, board, detect, store
from red_main.common import UNKNOWN, env_minutes, minutes_since, now, stamp


def scan(at: datetime.datetime) -> tuple[dict, list[str]]:
    """({repo: (state, info)}, problems). A repo that raises is UNKNOWN, never skipped silently."""
    repos, why = detect.list_repos(at)
    if repos is None:
        return {}, [f"AMBER red-main watcher could not list repos: {why}"]
    results, problems = {}, []
    for repo, branch in repos:
        try:
            results[repo] = detect.repo_state(repo, branch)
        except Exception as e:  # noqa: BLE001 — one repo must never stop the sweep
            results[repo] = (UNKNOWN, {"reason": f"{repo} check raised: {type(e).__name__}: {e}"})
        if results[repo][0] == UNKNOWN:
            problems.append(f"AMBER red-main check could not read {results[repo][1].get('reason')}")
    return results, problems


def _merge(card: dict, fields: dict, at: datetime.datetime) -> None:
    note = fields.pop("note", None)
    if note:
        card["note"] = (str(card.get("note") or "") + " | " + note).strip(" |")[-2000:]
    if "pr_overdue" not in fields:
        card.pop("pr_overdue", None)
    card.update(fields)
    if card.get("owner"):
        card["unowned_since"] = None
    elif not card.get("unowned_since"):
        card["unowned_since"] = stamp(at)
    age = minutes_since(card.get("unowned_since"), at)
    if not card.get("owner") and age is not None and age >= env_minutes("RED_MAIN_ESCALATE_MIN", 30).total_seconds() // 60:
        if not card.get("escalated"):
            card.update({"escalated": stamp(at), "priority": "P0",
                         "blocker": f"UNOWNED {age} min: red main with no live lane. Lead to take it."})
    card["updated"] = stamp(at)


def _write_back(updates: dict, at: datetime.datetime):
    def mutate(d):
        cards = {c["id"]: c for c in board.live_red_cards(d)}
        for cid, fields in updates.items():
            if cid in cards and cards[cid].get("episode") == fields.pop("_episode"):
                _merge(cards[cid], fields, at)
        return bool(updates)
    return mutate


def cycle() -> list[str]:
    """Run one cycle; returns the AMBER lines about checks that could not run."""
    at = now()
    with store.single_run() as mine:
        if not mine:
            return ["AMBER red-main watcher: previous cycle still running"]
        results, problems = scan(at)
        store.update_jobs(lambda d: board.reconcile(d, results, at))
        grace = int(env_minutes("RED_MAIN_PR_GRACE_MIN", 10).total_seconds() // 60)
        updates, budget = {}, int(os.environ.get("RED_MAIN_MAX_NEW_LANES", "2"))
        cards = sorted(board.live_red_cards(store.read_jobs()), key=lambda c: str(c.get("red_since")), reverse=True)
        for card in cards:   # newest red first: a fresh break is the one blocking today's jobs
            fields = actions.run(card, at, grace, may_launch=budget > 0)
            budget -= 1 if fields.get("lane") else 0
            if fields or not card.get("owner") or card.get("pr_overdue"):
                updates[card["id"]] = {**fields, "_episode": card.get("episode")}
        if updates:
            store.update_jobs(_write_back(updates, at))
        store.save_state("red-main-watch.json", {"at": stamp(at), "problems": problems,
                                                  "states": {r: s for r, (s, _) in results.items()}})
    return problems
