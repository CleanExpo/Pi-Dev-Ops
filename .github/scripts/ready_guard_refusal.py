"""RA-8212: when a GitHub refusal to draft a PR may fail a PR ready guard run.

Every guard run sweeps all open PRs, but on a pull_request event the result shows as a check
on ONE PR. When GitHub refuses to draft some OTHER PR (FORBIDDEN on convertPullRequestToDraft:
the token cannot do it), that is printed as a warning and does not fail the run. A refusal on
the triggering PR itself still fails, as does any other error. Sweep runs (schedule, push,
workflow_run, check_suite) have no triggering PR, so a refusal there is a warning too.
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
    if draft_refused(e) and number != trigger:
        print("::warning::#{} should be a draft but GitHub refused to draft it (token lacks the "
              "permission, RA-8212); not failing this run for another PR.".format(number))
        return False
    print("  ERROR acting on #{}: {}".format(number, e), file=sys.stderr)
    return True
