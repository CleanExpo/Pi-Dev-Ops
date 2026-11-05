"""Is a repo's default branch red? (RA-8174)

Red = the latest COMPLETED run of any active workflow on the default branch failed.
That covers push CI and scheduled jobs alike (the Unite-Group Nexus Heartbeat failed
daily for 11 days because the old checks only looked at PR rollups). Runs still in
progress prove nothing, a failed read is UNKNOWN, and pull_request runs are ignored.
"""
from __future__ import annotations

import datetime
import json
import os

from red_main.common import FAIL, OK, UNKNOWN, gh, gh_json, org, parse_time

FAILED = {"failure", "timed_out", "startup_failure", "action_required"}
PASSED = {"success", "neutral", "skipped", "cancelled", "stale"}
RUN_LIMIT = 100
RUN_FIELDS = "workflowName,workflowDatabaseId,conclusion,status,createdAt,headSha,event,url"


def configured_repos() -> list[tuple[str, str]] | None:
    """RED_MAIN_REPOS="Org/A@main,Org/B" pins the list (tests, one-repo runs)."""
    raw = os.environ.get("RED_MAIN_REPOS", "").strip()
    if not raw:
        return None
    out = []
    for item in (x.strip() for x in raw.split(",") if x.strip()):
        name, _, branch = item.partition("@")
        out.append((name, branch or "main"))
    return out


def list_repos(at: datetime.datetime) -> tuple[list[tuple[str, str]] | None, str]:
    """(repo, default branch) for every live repo pushed within RED_MAIN_ACTIVE_DAYS."""
    pinned = configured_repos()
    if pinned is not None:
        return pinned, ""
    data, why = gh_json("repo", "list", org(), "--limit", "500", "--no-archived",
                        "--json", "nameWithOwner,defaultBranchRef,pushedAt")
    if not isinstance(data, list):
        return None, why or "repo list was not a list"
    cutoff = at - datetime.timedelta(days=int(os.environ.get("RED_MAIN_ACTIVE_DAYS", "60")))
    out = []
    for r in data:
        branch = ((r or {}).get("defaultBranchRef") or {}).get("name")
        pushed = parse_time(str((r or {}).get("pushedAt") or "").split(".")[0].rstrip("Z") + "Z")
        if branch and pushed and pushed >= cutoff and isinstance(r.get("nameWithOwner"), str):
            out.append((r["nameWithOwner"], branch))
    return out, ""


def _readable(run) -> bool:
    return (isinstance(run, dict) and isinstance(run.get("workflowDatabaseId"), int)
            and isinstance(run.get("workflowName"), str) and isinstance(run.get("status"), str)
            and isinstance(run.get("createdAt"), str))


def latest_failures(runs: list) -> tuple[list[dict] | None, str]:
    """Per workflow, the latest completed run; return the failing ones (newest-first input)."""
    seen, red = {}, []
    for run in runs:
        if not _readable(run):
            return None, f"run entry not readable: {str(run)[:80]}"
        if str(run.get("event", "")).startswith("pull_request") or run["status"] != "completed":
            continue
        wid = run["workflowDatabaseId"]
        if wid in seen:
            if seen[wid] is not None and run.get("conclusion") in FAILED:
                seen[wid]["since"] = run["createdAt"]   # walk back the failing streak
            elif seen[wid] is not None:
                seen[wid] = None   # streak ended; stop extending `since`
            continue
        conclusion = run.get("conclusion")
        if conclusion not in FAILED | PASSED:
            return None, f"{run['workflowName']} has unreadable conclusion {conclusion!r}"
        if conclusion in FAILED:
            entry = {"id": wid, "name": run["workflowName"], "url": run.get("url", ""),
                     "sha": str(run.get("headSha", ""))[:8], "since": run["createdAt"], "last": run["createdAt"]}
            seen[wid] = entry
            red.append(entry)
        else:
            seen[wid] = None
    return [{k: v for k, v in e.items()} for e in red], ""


def _active_ids(repo: str) -> tuple[set | None, str]:
    ok, out, why = gh("workflow", "list", "-R", repo, "--all", "--limit", "200", "--json", "id,state")
    if not ok:
        return None, why
    if not out.strip():
        return set(), ""   # gh prints nothing (exit 0) for a repo with no workflows
    try:
        data = json.loads(out)
    except ValueError:
        return None, f"gh output not JSON: {out.strip()[:80]!r}"
    if not isinstance(data, list):
        return None, why or "workflow list was not a list"
    if len(data) >= 200:   # a full page may hide the failing workflow: never conclude green from it
        return None, "workflow list hit the 200 limit"
    for w in data:   # review r1: one malformed row must not drop a failing workflow and read as green
        if not (isinstance(w, dict) and isinstance(w.get("id"), int) and isinstance(w.get("state"), str)):
            return None, f"workflow list entry not readable: {str(w)[:80]}"
    return {w["id"] for w in data if w["state"] == "active"}, ""


def completed_ids(runs: list) -> set:
    """Workflows whose latest completed (non-PR) run is on this page."""
    return {r["workflowDatabaseId"] for r in runs
            if r.get("status") == "completed" and not str(r.get("event", "")).startswith("pull_request")}


def _unseen_red(repo: str, branch: str, wid: int, cache: dict, at: datetime.datetime):
    """(red entry or None, reason) for an active workflow the run page did not reach.

    Review r2: a busy workflow can fill the 100-run page and hide an older failing
    one (a daily job), so every active workflow needs its own latest completed run.
    The answer is cached: a newer run of that workflow would appear on the page, so
    an off-page result only changes when a long run finishes late (TTL covers that).
    """
    key, ttl = f"{repo}#{wid}", int(os.environ.get("RED_MAIN_UNSEEN_TTL_MIN", "360"))
    hit = cache.get(key)
    checked = parse_time((hit or {}).get("at"))
    if hit is not None and checked is not None and at - checked < datetime.timedelta(minutes=ttl):
        return hit.get("red"), ""
    runs, why = gh_json("run", "list", "-R", repo, "--branch", branch, "--workflow", str(wid),
                        "--limit", "20", "--json", RUN_FIELDS)
    if not isinstance(runs, list):
        return None, f"workflow {wid} runs could not be read: {why or 'not a list'}"
    red, why = latest_failures(runs)
    if red is None:
        return None, why
    cache[key] = {"at": at.strftime("%Y-%m-%dT%H:%M%z"), "red": red[0] if red else None}
    return cache[key]["red"], ""


def _current(entry: dict, at: datetime.datetime) -> bool:
    """A failure counts while its latest failing run is recent. A one-shot or manual job
    that last failed months ago is history, not a red main (RED_MAIN_STALE_DAYS, default 7;
    a daily job failing for 11 days is still current because its last run is recent)."""
    last = parse_time(entry.get("last") or entry.get("since"))
    days = int(os.environ.get("RED_MAIN_STALE_DAYS", "7"))
    return last is not None and at - last <= datetime.timedelta(days=days)


def repo_state(repo: str, branch: str, cache: dict | None = None,
               at: datetime.datetime | None = None) -> tuple[str, dict]:
    """(OK | FAIL | UNKNOWN, info). info: failing workflows, or the reason it is unknown."""
    cache = {} if cache is None else cache
    at = at or datetime.datetime.now().astimezone()
    runs, why = gh_json("run", "list", "-R", repo, "--branch", branch, "--limit", str(RUN_LIMIT),
                        "--json", RUN_FIELDS)
    if not isinstance(runs, list):
        return UNKNOWN, {"reason": f"{repo} runs on {branch} could not be read: {why or 'not a list'}"}
    red, why = latest_failures(runs)
    if red is None:
        return UNKNOWN, {"reason": f"{repo}: {why}"}
    active, why = _active_ids(repo)
    if active is None:
        return UNKNOWN, {"reason": f"{repo} workflow list could not be read: {why}"}
    red = [r for r in red if r["id"] in active]
    unseen = active - completed_ids(runs) if len(runs) >= RUN_LIMIT else set()   # a short page is complete
    for wid in sorted(unseen):
        entry, why = _unseen_red(repo, branch, wid, cache, at)
        if why:
            return UNKNOWN, {"reason": f"{repo}: {why}"}
        if entry:
            red.append(entry)
    red = [r for r in red if _current(r, at)]
    if not red:
        return OK, {}
    return FAIL, {"failing": red, "since": min(r["since"] for r in red), "branch": branch}
