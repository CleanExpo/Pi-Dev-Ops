"""Re-run a PR's failed pr-ready-guard run once that PR is green, so its check can clear.

When a PR is marked ready while its checks still run, the pull_request run tries to draft it.
GitHub may refuse (RA-8212); the run then fails on purpose, and that red check is the hold.
Nothing else ever re-judges that PR-scoped check, so without this the PR stays blocked until
a human re-runs it (observed 08/11/2026 on #1000 and #1001). A sweep that finds the PR green
calls this; the re-run judges the PR again on its own check. Needs `actions: write`.

Only the newest pull_request run for the head commit is considered, only when it finished
red, and never past MAX_ATTEMPTS, so a run that keeps failing for another reason cannot
bill a re-run on every sweep. A cancelled run is exempt from the cap: the workflow's
concurrency group cancels a queued re-run whenever a newer run queues, which costs nothing
and would otherwise use up the attempts and dead-end the PR again. A refused re-run warns:
it must not turn some other PR's check red. Standard library only.
"""
from __future__ import annotations

import urllib.error
from typing import Callable

API = "https://api.github.com"
WORKFLOW = "pr-ready-guard.yml"
RED = {"failure", "cancelled", "timed_out", "startup_failure", "action_required"}
MAX_ATTEMPTS = 3


def rerun_stale_guard_run(call: Callable, token: str, repo: str, number: int, head_sha: str) -> bool:
    url = "{}/repos/{}/actions/workflows/{}/runs?event=pull_request&head_sha={}&per_page=100".format(
        API, repo, WORKFLOW, head_sha)
    runs = call(token, "GET", url).get("workflow_runs") or []
    if not runs:
        return False
    newest = max(runs, key=lambda r: r["id"])
    if newest.get("status") != "completed" or newest.get("conclusion") not in RED:
        return False
    if newest["conclusion"] != "cancelled" and (newest.get("run_attempt") or 1) >= MAX_ATTEMPTS:
        print("::warning::#{} is green but its pr-ready-guard run {} already failed {} times; not "
              "re-running it again. Re-run it by hand once the cause is fixed.".format(
                  number, newest["id"], newest.get("run_attempt")))
        return False
    try:
        call(token, "POST", "{}/repos/{}/actions/runs/{}/rerun".format(API, repo, newest["id"]))
    except urllib.error.HTTPError as e:
        print("::warning::#{} is green but GitHub refused to re-run its pr-ready-guard run {} "
              "({} {}); it stays red until re-run by hand.".format(number, newest["id"], e.code, e.reason))
        return False
    print("  #{} is green: re-running its failed pr-ready-guard run {}".format(number, newest["id"]))
    return True
