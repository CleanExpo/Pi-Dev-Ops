#!/usr/bin/env python3
"""linear_evidence_audit.py — flag Done tickets that carry no merge evidence.

The no-false-complete gate: any issue moved to a completed state without a
linked GitHub PR/commit attachment (Linear's GitHub integration auto-attaches
them when a PR references the identifier) gets an `unverified-complete` label
and one audit comment asking for the PR link or the `no-code-change` label.

Report-only automation: it never reopens or reassigns. Idempotent — the
comment carries a marker string and is posted at most once per issue; the
label is looked up before being applied.

Usage:
    LINEAR_API_KEY=lin_api_... python3 scripts/linear_evidence_audit.py \
        [--hours 26] [--dry-run] [--project-ids id1,id2]

Default projects: RestoreAssist + RestoreAssist V2 (RA team).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import urllib.request

log = logging.getLogger("linear_evidence_audit")

LINEAR_API_URL = "https://api.linear.app/graphql"
AUDIT_MARKER = "[evidence-audit]"
SUSPECT_LABEL = "unverified-complete"
EXEMPT_LABEL = "no-code-change"
DEFAULT_PROJECT_IDS = [
    "3c78358a-b558-4029-b47d-367a65beea7b",  # RestoreAssist (RA)
    "8027986f-e10d-4d46-9061-a3809e5dc8c3",  # RestoreAssist V2 (RA)
    "f45212be-3259-4bfb-89b1-54c122c939a7",  # Pi-Dev-Ops (RA)
    "3125c6e4-b729-48d4-a718-400a2b83ddc5",  # Synthex (SYN)
    "20538e04-ba27-467d-b632-1fb346063089",  # CARSI (GP)
    "b62d9b14-9d9c-46c7-a3f4-05fbd49550ff",  # Unite-Group (UNI)
    "40c7dc3d-35ff-4e2c-ac1e-f903c1f5c856",  # CCW CRM (UNI)
    "ba150052-ff1c-4750-a0bc-7a8261d4d72b",  # DR-NRPG Contractor Go-Live (DR)
    "ec4e8059-988f-495e-8ba7-38af44073cec",  # DR-NRPG Ops (DR)
    "d2c1d63b-1e85-424d-9278-efff15b0d46b",  # Disaster Recovery Website (DR)
]


def gql(api_key: str, query: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        LINEAR_API_URL, data=payload,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise RuntimeError(f"Linear GraphQL error: {body['errors']}")
    return body["data"]


def recently_completed(api_key: str, project_ids: list[str], since: dt.datetime) -> list[dict]:
    query = """
    query($filter: IssueFilter!, $after: String) {
      issues(filter: $filter, first: 100, after: $after) {
        nodes {
          id identifier title completedAt
          team { id }
          labels { nodes { name } }
          attachments { nodes { url } }
          comments { nodes { body } }
        }
        pageInfo { hasNextPage endCursor }
      }
    }"""
    flt = {
        "project": {"id": {"in": project_ids}},
        "completedAt": {"gt": since.isoformat()},
    }
    nodes, after = [], None
    while True:
        data = gql(api_key, query, {"filter": flt, "after": after})["issues"]
        nodes += data["nodes"]
        if not data["pageInfo"]["hasNextPage"]:
            break
        after = data["pageInfo"]["endCursor"]
    return nodes


def has_merge_evidence(issue: dict) -> bool:
    return any("github.com" in (a["url"] or "") for a in issue["attachments"]["nodes"])


def is_exempt(issue: dict) -> bool:
    return any(l["name"] == EXEMPT_LABEL for l in issue["labels"]["nodes"])


def already_flagged(issue: dict) -> bool:
    return any(AUDIT_MARKER in (c["body"] or "") for c in issue["comments"]["nodes"])


def ensure_label(api_key: str, team_id: str, name: str) -> str:
    data = gql(api_key, """
      query($teamId: String!) {
        team(id: $teamId) { labels(first: 250) { nodes { id name } } }
      }""", {"teamId": team_id})
    for lbl in data["team"]["labels"]["nodes"]:
        if lbl["name"] == name:
            return lbl["id"]
    data = gql(api_key, """
      mutation($input: IssueLabelCreateInput!) {
        issueLabelCreate(input: $input) { issueLabel { id } }
      }""", {"input": {"teamId": team_id, "name": name, "color": "#e05d44"}})
    return data["issueLabelCreate"]["issueLabel"]["id"]


def flag(api_key: str, issue: dict, label_id: str) -> None:
    existing = [l["name"] for l in issue["labels"]["nodes"]]
    if SUSPECT_LABEL not in existing:
        gql(api_key, """
          mutation($id: String!, $labelId: String!) {
            issueAddLabel(id: $id, labelId: $labelId) { success }
          }""", {"id": issue["id"], "labelId": label_id})
    comment = (
        f"{AUDIT_MARKER} This issue moved to Done with **no linked PR or commit**. "
        f"Evidence is required for completed work: attach the merged PR "
        f"(reference `{issue['identifier']}` in the PR title/body), or apply the "
        f"`{EXEMPT_LABEL}` label if this was legitimately non-code work. "
        f"Until then the completion claim is unverified."
    )
    gql(api_key, """
      mutation($input: CommentCreateInput!) {
        commentCreate(input: $input) { success }
      }""", {"input": {"issueId": issue["id"], "body": comment}})


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=26)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--project-ids", default=",".join(DEFAULT_PROJECT_IDS))
    args = ap.parse_args()

    api_key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not api_key:
        log.error("LINEAR_API_KEY not set")
        return 1

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=args.hours)
    issues = recently_completed(api_key, args.project_ids.split(","), since)
    suspects = [
        i for i in issues
        if not has_merge_evidence(i) and not is_exempt(i) and not already_flagged(i)
    ]
    log.info("completed in window: %d | new unevidenced: %d", len(issues), len(suspects))

    if not suspects:
        return 0
    if args.dry_run:
        for i in suspects:
            log.info("DRY-RUN would flag %s — %s", i["identifier"], i["title"][:70])
        return 0

    label_cache: dict[str, str] = {}
    for i in suspects:
        team_id = i["team"]["id"]
        if team_id not in label_cache:
            label_cache[team_id] = ensure_label(api_key, team_id, SUSPECT_LABEL)
        flag(api_key, i, label_cache[team_id])
        log.info("flagged %s — %s", i["identifier"], i["title"][:70])
    return 0


if __name__ == "__main__":
    sys.exit(main())
