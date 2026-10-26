"""RA-8099 — deterministic delivery finish-line policy.

Pure decisions. Does not merge, deploy, change permissions, call an API or mark
Linear issues Done. Consumers supply verified GitHub, Linear and deployment
snapshots. A separate governed adapter must execute permitted follow-ups.

A build session ending is not the same thing as a delivery finishing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
from typing import Literal


class Stage(str, Enum):
    ACCEPTED = "accepted"
    BUILDING = "building"
    TESTED = "tested"
    REVIEW_WAIT = "review_wait"
    APPROVAL_WAIT = "approval_wait"
    MERGE_READY = "merge_ready"
    MERGED = "merged"
    DEPLOYING = "deploying"
    VERIFIED_LIVE = "verified_live"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


DeliveryKind = Literal["production", "artifact"]
Severity = Literal["info", "reminder", "escalation", "founder", "critical"]


@dataclass(frozen=True)
class Snapshot:
    """One promised deliverable with one owner and one verified release target.

    pr_head_sha is the reviewed candidate; merge_sha may differ due to a merge
    commit, and deployed/verified must match the merge revision exactly.
    """

    issue_id: str
    project_id: str
    stage: Stage
    stage_since: datetime
    owner: str | None = None
    delivery_kind: DeliveryKind = "production"
    acceptance_passed: bool = False
    tests_passed: bool = False
    pr_head_sha: str | None = None
    reviewed_head_sha: str | None = None
    authorised_head_sha: str | None = None
    merge_sha: str | None = None
    deployed_sha: str | None = None
    verified_sha: str | None = None
    delivered_artifact_receipt: str | None = None
    blocked_reason: str | None = None


@dataclass(frozen=True)
class Finding:
    issue_id: str
    code: str
    severity: Severity
    next_owner: str
    message: str
    key: str


REVIEW_STAGES = {Stage.REVIEW_WAIT}
def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("stage_since/now must contain a timezone")
    return value.astimezone(timezone.utc)


def can_finish(item: Snapshot) -> bool:
    """No inferred Done from CI, green reviewers, merge, or production alias."""
    if not item.acceptance_passed or not item.tests_passed:
        return False
    if not item.pr_head_sha or item.reviewed_head_sha != item.pr_head_sha:
        return False
    if item.authorised_head_sha != item.pr_head_sha:
        return False
    if item.delivery_kind == "artifact":
        return bool(item.delivered_artifact_receipt)
    return bool(
        item.merge_sha
        and item.deployed_sha == item.merge_sha
        and item.verified_sha == item.merge_sha
    )


def _finding(item: Snapshot, code: str, severity: Severity, owner: str, message: str) -> Finding:
    # Stable across repeated scans. Resets if the candidate revision or stage changes.
    key_src = f"{item.issue_id}|{item.stage.value}|{item.pr_head_sha or ''}|{code}"
    key = sha256(key_src.encode("utf-8")).hexdigest()[:24]
    return Finding(item.issue_id, code, severity, owner, message, key)


def assess(item: Snapshot, now: datetime, *, review_reminder_hours: int = 1,
           review_escalation_hours: int = 4, founder_escalation_hours: int = 24) -> tuple[Finding, ...]:
    """Prioritised advice. READ-ONLY; never self-authorises a release."""
    age = _utc(now) - _utc(item.stage_since)
    if age < timedelta(minutes=-5):
        return (_finding(item, "INVALID_CLOCK", "critical", "SPM",
                         "Stage timestamp is in the future; refuse to treat as fresh."),)
    if item.stage == Stage.DONE:
        if not can_finish(item):
            return (_finding(item, "FALSE_DONE", "critical", "SPM",
                             "Marked Done without an exact revision and acceptance receipt."),)
        return ()
    if item.stage in {Stage.CANCELLED, Stage.FAILED}:
        return ()  # Explicit recorded disposition, not successful completion.
    if item.stage == Stage.BLOCKED:
        return (_finding(item, "BLOCKED", "escalation", item.owner or "SPM",
                         item.blocked_reason or "Blocker has no recorded reason."),)
    if not item.owner:
        return (_finding(item, "UNOWNED", "escalation", "SPM",
                         "Every active deliverable needs a named accountable owner."),)
    if item.stage == Stage.VERIFIED_LIVE:
        if can_finish(item):
            return (_finding(item, "CLOSE_ELIGIBLE", "info", item.owner,
                             "Receipts allow a governed Done transition and project closure check."),)
        return (_finding(item, "UNVERIFIED_RELEASE", "critical", item.owner,
                         "Verified-live label is unsupported by current exact-SHA evidence."),)
    if item.stage == Stage.APPROVAL_WAIT:
        owner = "founder/Board"
        if age >= timedelta(hours=founder_escalation_hours):
            return (_finding(item, "HUMAN_APPROVAL_AGED", "founder", owner,
                             "Approval is still required; alert, do not bypass it."),)
        return ()  # A healthy pending human decision does not become auto approval.
    if item.stage in {Stage.MERGED, Stage.DEPLOYING}:
        if item.merge_sha and item.merge_sha == item.deployed_sha == item.verified_sha:
            return (_finding(item, "CHECK_ACCEPTANCE", "info", item.owner,
                             "Release revision verified; validate acceptance and close explicitly."),)
        if age >= timedelta(hours=founder_escalation_hours):
            return (_finding(item, "DEPLOY_UNVERIFIED_24H", "founder", item.owner,
                             "Merged for at least 24 hours without a matching verified live revision."),)
        if age >= timedelta(hours=review_escalation_hours):
            return (_finding(item, "DEPLOY_UNVERIFIED", "escalation", item.owner,
                             "Merged code has no matching verified live revision."),)
    if age >= timedelta(hours=founder_escalation_hours):
        return (_finding(item, "STALE_24H", "founder", item.owner,
                         "No confirmed stage transition for 24 hours; founder oversight required."),)
    if age >= timedelta(hours=review_escalation_hours):
        return (_finding(item, "STALE_4H", "escalation", item.owner,
                         "No confirmed stage transition for four hours; reassign/retry within policy."),)
    if age >= timedelta(hours=review_reminder_hours) and item.stage in REVIEW_STAGES:
        return (_finding(item, "REVIEW_REMINDER", "reminder", item.owner,
                         "Reviewer has not produced an accepted review receipt in one hour."),)
    return ()


def project_can_close(items: list[Snapshot], *, expected_issue_ids: set[str]) -> bool:
    """Finite project scope; excluded/cancelled issues need a separate approved amendment."""
    if not expected_issue_ids:
        return False
    by_id = {i.issue_id: i for i in items}
    if len(by_id) != len(items):
        return False  # Duplicate snapshots are ambiguous, never choose the last one.
    return all(issue_id in by_id and by_id[issue_id].stage == Stage.DONE
               and can_finish(by_id[issue_id]) for issue_id in expected_issue_ids)


def closure_queue(items: list[Snapshot], now: datetime) -> list[Finding]:
    """Existing aged work before new intake. Human approvals stay with humans."""
    ranked: list[tuple[int, float, Finding]] = []
    score = {"critical": 0, "founder": 1, "escalation": 2, "reminder": 3, "info": 4}
    for item in items:
        for finding in assess(item, now):
            age = max(0.0, (_utc(now) - _utc(item.stage_since)).total_seconds())
            ranked.append((score[finding.severity], -age, finding))
    return [row[2] for row in sorted(ranked, key=lambda row: (row[0], row[1], row[2].issue_id))]
