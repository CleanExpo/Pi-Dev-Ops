"""Is a repo's default branch red? (RA-8174)

Red = the latest COMPLETED run of any active workflow on the default branch failed.
That covers push CI and scheduled jobs alike (the Unite-Group Nexus Heartbeat failed
daily for 11 days because the old checks only looked at PR rollups). Runs still in
progress prove nothing, a failed read is UNKNOWN, and pull_request runs are ignored.
"""
from __future__ import annotations

import datetime
import os

from red_main.common import FAIL, OK, UNKNOWN, gh_json, org, parse_time

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
                     "sha": str(run.get("headSha", ""))[:8], "since": run["createdAt"]}
            seen[wid] = entry
            red.append(entry)
        else:
            seen[wid] = None
    return [{k: v for k, v in e.items()} for e in red], ""


def _active_ids(repo: str) -> tuple[set | None, str]:
    data, why = gh_json("workflow", "list", "-R", repo, "--all", "--limit", "200", "--json", "id,state")
    if not isinstance(data, list):
        return None, why or "workflow list was not a list"
    return {w.get("id") for w in data if isinstance(w, dict) and w.get("state") == "active"}, ""


def repo_state(repo: str, branch: str) -> tuple[str, dict]:
    """(OK | FAIL | UNKNOWN, info). info: failing workflows, or the reason it is unknown."""
    runs, why = gh_json("run", "list", "-R", repo, "--branch", branch, "--limit", str(RUN_LIMIT),
                        "--json", RUN_FIELDS)
    if not isinstance(runs, list):
        return UNKNOWN, {"reason": f"{repo} runs on {branch} could not be read: {why or 'not a list'}"}
    red, why = latest_failures(runs)
    if red is None:
        return UNKNOWN, {"reason": f"{repo}: {why}"}
    if not red:
        return OK, {}
    active, why = _active_ids(repo)
    if active is None:
        return UNKNOWN, {"reason": f"{repo} workflow list could not be read: {why}"}
    red = [r for r in red if r["id"] in active]
    if not red:
        return OK, {}
    since = min(r["since"] for r in red)
    return FAIL, {"failing": red, "since": since, "branch": branch}
