#!/usr/bin/env python3
"""PR ready guard: no pull request sits in the ready state while red, pending or conflicting.

Standard library only. Talks to GitHub with GITHUB_TOKEN (or `gh auth token` locally).
Never merges, never pushes. See .github/workflows/pr-ready-guard.yml.

Usage: pr_ready_guard.py --repo OWNER/REPO [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

LABEL = "held-by-ready-guard"
MARKER = "<!-- pr-ready-guard -->"
OWN_CHECKS = {"pr-ready-guard"}  # this workflow's job name; ignored so it cannot block itself
FAIL_CONCLUSIONS = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE", "STALE"}
OK_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
API = "https://api.github.com"


@dataclass
class Check:
    name: str
    state: str  # "success" | "failure" | "pending"


@dataclass
class PR:
    number: int
    is_draft: bool
    labels: Set[str]
    mergeable: str  # MERGEABLE | CONFLICTING | UNKNOWN
    checks: List[Check] = field(default_factory=list)
    head_sha: str = ""
    node_id: str = ""


@dataclass
class Decision:
    action: str  # "draft" | "ready" | "leave"
    reasons: List[str] = field(default_factory=list)


def _judge(pr: PR) -> Dict[str, List[str]]:
    """Return the problems with a PR: failing, pending, conflict, unknown (all name lists)."""
    checks = [c for c in pr.checks if c.name not in OWN_CHECKS]
    return {
        "failing": sorted({c.name for c in checks if c.state == "failure"}),
        "pending": sorted({c.name for c in checks if c.state == "pending"}),
        "conflict": ["merge conflict with the base branch"] if pr.mergeable == "CONFLICTING" else [],
        "unknown": ["mergeability not computed yet"] if pr.mergeable == "UNKNOWN" else [],
        "judged": [c.name for c in checks],
    }


def decide(pr: PR) -> Decision:
    """Pure decision: should this PR be drafted, marked ready, or left alone?"""
    p = _judge(pr)
    bad = p["failing"] or p["pending"] or p["conflict"]
    reasons = (
        ["failing check: " + n for n in p["failing"]]
        + ["still running: " + n for n in p["pending"]]
        + p["conflict"]
    )
    if not pr.is_draft:
        return Decision("draft", reasons) if bad else Decision("leave")
    if LABEL not in pr.labels:
        return Decision("leave")  # intentional draft: never touched
    if bad or p["unknown"] or not p["judged"]:
        return Decision("leave", reasons or p["unknown"] or ["no checks reported yet"])
    return Decision("ready")


# ---------------------------------------------------------------- GitHub I/O

def get_token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def _call(token: str, method: str, url: str, body: Optional[dict] = None) -> dict:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "pr-ready-guard")
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed https host
        raw = r.read()
    return json.loads(raw) if raw else {}


def graphql(token: str, query: str, variables: dict) -> dict:
    out = _call(token, "POST", API + "/graphql", {"query": query, "variables": variables})
    if out.get("errors"):
        raise RuntimeError("GraphQL error: " + json.dumps(out["errors"]))
    return out["data"]


PR_LIST = """query($o:String!,$n:String!,$after:String){repository(owner:$o,name:$n){
pullRequests(states:OPEN,first:50,after:$after){pageInfo{hasNextPage endCursor}
nodes{id number isDraft mergeable headRefOid labels(first:50){nodes{name}}}}}}"""

MERGEABLE = "query($id:ID!){node(id:$id){... on PullRequest{mergeable}}}"

CHECKS = """query($id:ID!,$after:String){node(id:$id){... on PullRequest{commits(last:1){nodes{commit{
statusCheckRollup{contexts(first:100,after:$after){pageInfo{hasNextPage endCursor}nodes{__typename
... on CheckRun{name status conclusion} ... on StatusContext{context state}
}}}}}}}}}"""


def classify(node: dict) -> Check:
    if node["__typename"] == "CheckRun":
        if node["status"] != "COMPLETED":
            return Check(node["name"], "pending")
        c = node.get("conclusion") or ""
        return Check(node["name"], "failure" if c in FAIL_CONCLUSIONS or c not in OK_CONCLUSIONS else "success")
    s = node["state"]
    state = {"SUCCESS": "success", "PENDING": "pending", "EXPECTED": "pending"}.get(s, "failure")
    return Check(node["context"], state)


def fetch_checks(token: str, node_id: str) -> List[Check]:
    out: List[Check] = []
    after = None
    while True:
        d = graphql(token, CHECKS, {"id": node_id, "after": after})
        commits = d["node"]["commits"]["nodes"]
        rollup = commits[0]["commit"]["statusCheckRollup"] if commits else None
        if not rollup:
            return out
        ctx = rollup["contexts"]
        out += [classify(n) for n in ctx["nodes"]]
        if not ctx["pageInfo"]["hasNextPage"]:
            return out
        after = ctx["pageInfo"]["endCursor"]


def fetch_prs(token: str, repo: str) -> List[PR]:
    owner, name = repo.split("/")
    prs: List[PR] = []
    after = None
    while True:
        page = graphql(token, PR_LIST, {"o": owner, "n": name, "after": after})["repository"]["pullRequests"]
        for n in page["nodes"]:
            prs.append(PR(n["number"], n["isDraft"], {x["name"] for x in n["labels"]["nodes"]},
                          n["mergeable"], [], n["headRefOid"], n["id"]))
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    for pr in prs:
        if pr.mergeable == "UNKNOWN":  # GitHub computes lazily; ask once more for this PR
            time.sleep(3)
            pr.mergeable = graphql(token, MERGEABLE, {"id": pr.node_id})["node"]["mergeable"]
        pr.checks = fetch_checks(token, pr.node_id)
    return prs


# ---------------------------------------------------------------- actions

def render_comment(action: str, reasons: List[str], sha: str) -> str:
    if action == "draft":
        head = "Held as a draft by the PR ready guard. It will be marked ready again on its own once the problems below are gone."
    else:
        head = "Released by the PR ready guard: every check passed and it merges cleanly."
    body = "\n".join("- " + r for r in reasons) if reasons else "- all checks green, no conflicts"
    return "{}\n{}\n\n{}\n\nChecked commit: `{}`".format(MARKER, head, body, sha)


def upsert_comment(token: str, repo: str, number: int, text: str) -> None:
    url = "{}/repos/{}/issues/{}/comments?per_page=100".format(API, repo, number)
    existing = [c for c in _call(token, "GET", url) if MARKER in c.get("body", "") and c["user"]["type"] == "Bot"]
    if existing and existing[0]["body"] == text:
        return  # unchanged: do not churn the comment
    if existing:
        _call(token, "PATCH", "{}/repos/{}/issues/comments/{}".format(API, repo, existing[0]["id"]), {"body": text})
    else:
        _call(token, "POST", "{}/repos/{}/issues/{}/comments".format(API, repo, number), {"body": text})


def ensure_label(token: str, repo: str) -> None:
    try:
        _call(token, "POST", "{}/repos/{}/labels".format(API, repo),
              {"name": LABEL, "color": "B60205", "description": "Drafted by the PR ready guard until checks pass"})
    except urllib.error.HTTPError as e:  # 422 = already exists
        if e.code != 422:
            raise


def to_draft(token: str, repo: str, pr: PR, d: Decision) -> None:
    ensure_label(token, repo)
    _call(token, "POST", "{}/repos/{}/issues/{}/labels".format(API, repo, pr.number), {"labels": [LABEL]})
    try:
        graphql(token, "mutation($id:ID!){convertPullRequestToDraft(input:{pullRequestId:$id}){pullRequest{isDraft}}}",
                {"id": pr.node_id})
    except Exception:
        _call(token, "DELETE", "{}/repos/{}/issues/{}/labels/{}".format(API, repo, pr.number, LABEL))
        raise
    upsert_comment(token, repo, pr.number, render_comment("draft", d.reasons, pr.head_sha))


def to_ready(token: str, repo: str, pr: PR) -> None:
    graphql(token, "mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id}){pullRequest{isDraft}}}",
            {"id": pr.node_id})
    _call(token, "DELETE", "{}/repos/{}/issues/{}/labels/{}".format(API, repo, pr.number, LABEL))
    upsert_comment(token, repo, pr.number, render_comment("ready", [], pr.head_sha))


def run(repo: str, dry_run: bool) -> int:
    token = get_token()
    failures = 0
    for pr in fetch_prs(token, repo):
        d = decide(pr)
        state = "draft" if pr.is_draft else "ready"
        held = " +label" if LABEL in pr.labels else ""
        print("{}#{} [{}{}] -> {}{}".format(repo, pr.number, state, held, d.action.upper(),
                                            " (" + "; ".join(d.reasons) + ")" if d.reasons else ""))
        if dry_run:
            continue
        try:
            if d.action == "draft":
                to_draft(token, repo, pr, d)
            elif d.action == "ready":
                to_ready(token, repo, pr)
            elif pr.is_draft and LABEL in pr.labels and d.reasons:  # still held: keep the one comment current
                upsert_comment(token, repo, pr.number, render_comment("draft", d.reasons, pr.head_sha))
        except Exception as e:  # keep going so one bad PR cannot hide the rest
            failures += 1
            print("  ERROR acting on #{}: {}".format(pr.number, e), file=sys.stderr)
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dry-run", action="store_true", help="print decisions, change nothing")
    a = ap.parse_args()
    return run(a.repo, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
