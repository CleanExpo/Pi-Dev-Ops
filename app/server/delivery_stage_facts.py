"""RA-8100 pure helpers for the delivery classifier: timestamps, checks, review verdicts, PR states.

No network, no file, no collector call. Every problem with the evidence raises ``Unclassifiable``
carrying a reason code; the classifier turns it into UNKNOWN or MISSING_COMMIT for that one record.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .delivery_collect_fields import REVIEW_STATES, instant, sha

_VERDICTS = ("APPROVED", "CHANGES_REQUESTED")
_NO_EVIDENCE = frozenset({"neutral", "skipped"})  # a settled run that tested nothing


class Unclassifiable(Exception):
    """The evidence cannot place this record; ``stage`` is "unknown" or "missing_commit"."""

    def __init__(self, reason: str, stage: str = "unknown", item: dict | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.stage = stage
        self.item = item


def parse_ts(value: object) -> datetime:
    """A timezone-aware ISO-8601 instant in UTC (the collector's one owner); else ``bad_timestamp``."""
    parsed = instant(value)
    if parsed is None:
        raise Unclassifiable("bad_timestamp")
    return parsed


def iso(when: datetime) -> str:
    """ISO-8601 UTC text with a ``Z`` suffix."""
    return when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def sha_or_none(value: object) -> str | None:
    """A 40-hex SHA in lower case, else None (the collector's one owner)."""
    return sha(value)


def item_state(item: dict) -> str:
    """open, closed or merged for a facts dict or an error item; ``error`` for a failed read."""
    if "error" in item:
        if item.get("error") != "missing_commit":
            return "error"
        return "merged" if item.get("reason") == "no_merge_sha" else "open"
    state = item.get("state")
    if state not in ("open", "closed", "merged"):
        raise Unclassifiable("malformed_pr")
    return state


def commit_of(item: dict, state: str) -> str:
    """The head SHA of an open PR or the merge SHA of a merged one; raises MISSING_COMMIT."""
    if "error" in item:
        raise Unclassifiable(str(item.get("reason") or "missing_commit"), "missing_commit", item)
    value, missing = (item.get("head_sha"), "empty_head") if state == "open" else \
        (item.get("merge_sha"), "no_merge_sha")
    if value in (None, ""):
        raise Unclassifiable(missing, "missing_commit", item)
    sha = sha_or_none(value)
    if sha is None:
        raise Unclassifiable("malformed_sha")
    return sha


def checks_state(pr: dict) -> tuple[str, datetime | None]:
    """("green" | "not_green" | "none", newest check completed_at). A missing read is never empty."""
    runs, status = pr.get("check_runs"), pr.get("status")
    if not isinstance(runs, list) or not isinstance(status, dict) or not all(isinstance(r, dict) for r in runs):
        raise Unclassifiable("evidence_missing")
    total, state = status.get("total_count"), status.get("state")
    if not isinstance(total, int) or isinstance(total, bool) or not isinstance(state, str):
        raise Unclassifiable("malformed_status")
    done = [parse_ts(r["completed_at"]) for r in runs if r.get("completed_at") is not None]
    newest = max(done, default=None)
    tested = [r for r in runs if not (r.get("status") == "completed" and r.get("conclusion") in _NO_EVIDENCE)]
    if not tested and total == 0:  # no runs, or only skipped or neutral ones: no CI evidence
        return "none", newest
    runs_ok = all(r.get("status") == "completed" and r.get("conclusion") == "success" for r in tested)
    status_ok = state == "success" or total == 0
    return ("green" if runs_ok and status_ok else "not_green"), newest


@dataclass(frozen=True)
class Verdicts:
    blocked: bool               # some login's latest verdict is CHANGES_REQUESTED
    approval: dict | None       # newest allow-listed APPROVED verdict on the head
    stale: dict | None          # newest allow-listed APPROVED verdict on an older commit
    unverified: bool            # an APPROVED verdict on the head from a login not on the list


def _login(review: dict) -> str:
    login = review.get("login")
    return login.strip().lower() if isinstance(login, str) else ""


def review_verdicts(pr: dict, head: str, allowed: frozenset[str]) -> Verdicts:
    """Each login's latest APPROVED or CHANGES_REQUESTED review, by submitted time (spec line 136).
    Human identity comes only from ``allowed``; ``user.type`` is never read."""
    reviews = pr.get("reviews")
    if not isinstance(reviews, list) or not all(isinstance(r, dict) for r in reviews):
        raise Unclassifiable("evidence_missing")
    if any(r.get("state") not in REVIEW_STATES for r in reviews):
        raise Unclassifiable("bad_review_state")
    timed = sorted(((parse_ts(r.get("submitted_at")), i, r) for i, r in enumerate(reviews)
                    if r["state"] in _VERDICTS), key=lambda t: (t[0], t[1]))
    latest: dict[str, tuple[datetime, dict]] = {}
    for when, _, review in timed:
        latest[_login(review)] = (when, review)
    approvals = [(w, r) for w, r in latest.values() if r["state"] == "APPROVED"]
    listed = [(w, r) for w, r in approvals if _login(r) and _login(r) in allowed]
    on_head = [(w, r) for w, r in listed if sha_or_none(r.get("commit_id")) == head]
    older = [(w, r) for w, r in listed if sha_or_none(r.get("commit_id")) != head]
    unlisted = [r for w, r in approvals if not (_login(r) and _login(r) in allowed)]
    return Verdicts(blocked=any(r["state"] == "CHANGES_REQUESTED" for _, r in latest.values()),
                    approval=max(on_head, key=lambda t: t[0])[1] if on_head else None,
                    stale=max(older, key=lambda t: t[0])[1] if older else None,
                    unverified=any(sha_or_none(r.get("commit_id")) == head for r in unlisted))


def pr_list(prs: list | None, repo: str) -> list[dict]:
    """The record's ``prs``: ``{"repo", "number", "state"}`` only; a failed read is ``error``."""
    out = []
    for item in prs or []:
        if isinstance(item, dict):
            state = item.get("state") if item.get("state") in ("open", "closed", "merged") else \
                ("error" if "error" in item else "open")
            out.append({"repo": item.get("repo") or repo, "number": item.get("number"), "state": state})
    return out


def source_time(issue: dict | None, prs: list | None, fallback: datetime,
                first_seen: float | None) -> tuple[datetime, str]:
    """Rule 1: startedAt, else the linked PR's created_at, else stored first-seen, else ``fallback``.
    A source later than ``fallback`` (now) is an invalid clock, not a source: the next one is used."""
    def past(value: object) -> datetime | None:
        try:
            when = parse_ts(value)
        except Unclassifiable:
            return None
        return when if when <= fallback else None

    started = past((issue or {}).get("startedAt"))
    if started is not None:
        return started, "startedAt"
    created = [c for c in (past(i.get("created_at")) for i in prs or [] if isinstance(i, dict)) if c is not None]
    if created:
        return min(created), "pr_created_at"
    if isinstance(first_seen, (int, float)) and not isinstance(first_seen, bool):
        try:
            seen = datetime.fromtimestamp(first_seen, timezone.utc)
        except (ValueError, OverflowError, OSError):
            seen = None
        if seen is not None and seen <= fallback:
            return seen, "local_first_seen"
    return fallback, "local_first_seen"


def all_contained(live: object, shas: list[str]) -> bool:
    """Only the own revision's compare counts: ``identical`` or ``ahead`` for every merge SHA."""
    if not isinstance(live, dict) or sha_or_none(live.get("revision")) is None:
        return False
    compare = live.get("compare")
    if not isinstance(compare, dict):
        return False
    table = {str(k).lower(): v for k, v in compare.items()}
    return all(table.get(sha) in ("identical", "ahead") for sha in shas)
