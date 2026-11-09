"""When a GitHub refusal or another PR's error may fail a PR ready guard run.

Every guard run sweeps all open PRs, but on a pull_request event the result shows as a check
on ONE PR. GitHub refusing convertPullRequestToDraft (FORBIDDEN: the token cannot do it) is a
warning, never a failed check — including on the PR that triggered the run. Any other error
on some OTHER PR is also a warning: this check's pass/fail reflects only the triggering PR.
A non-permission error on the triggering PR itself still fails. Sweep runs (schedule, push,
workflow_run, check_suite) have no triggering PR, so a refusal there is a warning too; other
errors on a sweep still fail that run.
Standard library only.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional


class GraphQLError(RuntimeError):
    def __init__(self, errors: list) -> None:
        super().__init__("GraphQL error: " + json.dumps(errors))
        self.errors = errors


def triggering_pr() -> Optional[int]:
    """The PR whose check this run reports on (pull_request events only), else None."""
    path = os.environ.get("GITHUB_EVENT_PATH")
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request" or not path:
        return None
    with open(path) as f:
        return json.load(f)["pull_request"]["number"]


def draft_refused(e: Exception) -> bool:
    """True only when EVERY error is GitHub refusing convertPullRequestToDraft for lack of permission."""
    return isinstance(e, GraphQLError) and bool(e.errors) and all(
        x.get("type") == "FORBIDDEN" and "convertPullRequestToDraft" in (x.get("path") or []) for x in e.errors)


def counts_as_failure(e: Exception, number: int, trigger: Optional[int]) -> bool:
    if draft_refused(e):
        print("::warning::#{} should be a draft but GitHub refused convertPullRequestToDraft "
              "(FORBIDDEN: Resource not accessible by integration). The workflow requests "
              "pull-requests: write; not failing this check for a permission the token was "
              "denied.".format(number))
        return False
    if trigger is not None and number != trigger:
        print("::warning::error on #{} while this check is for #{}; not failing this PR: {}".format(
            number, trigger, e))
        return False
    print("  ERROR acting on #{}: {}".format(number, e), file=sys.stderr)
    return True
