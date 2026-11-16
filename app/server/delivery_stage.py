"""RA-8100 delivery classifier: evidence -> Snapshot -> ``assess`` + reconcile codes (spec section 9).

PURE. No network, no file, no collector call, no ``Tick``. The tick reads everything and passes plain
data in; the only ambient input is ``TAO_DELIVERY_HUMAN_REVIEWERS``, read from ``os.environ`` on each
call. Policy findings come from ``delivery_closure.assess`` unfiltered; every key comes from
``delivery_closure.finding_key``. Records and findings are plain JSON-serialisable dicts.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .delivery_closure import Finding, Snapshot, Stage, assess, finding_key
from .delivery_invariants import reading
from .delivery_stage_facts import (
    Unclassifiable, all_contained, checks_state, commit_of, iso, item_state, parse_ts, pr_list, review_verdicts,
    sha_or_none, source_time,
)

_DAY = timedelta(hours=24)
_SNAPSHOT_FIELDS = frozenset({"tests_passed", "pr_head_sha", "reviewed_head_sha", "merge_sha", "deployed_sha",
                              "verified_sha"})

# next_owner: "owner_or_SPM" / "owner" resolve to the mission's assignee, else "SPM"; other values are literal.
RECONCILE_CODES: dict[str, dict] = {
    "MISSING_COMMIT": {"severity": "escalation", "next_owner": "owner_or_SPM",
                       "message": "The head or merge commit cannot be read ({reason}); nothing here counts "
                                  "as progress."},
    "EVIDENCE_UNKNOWN": {"severity": "escalation", "next_owner": "owner_or_SPM",
                         "message": "Evidence did not arrive whole ({reason}); this is unknown, not healthy."},
    "EVIDENCE_UNKNOWN_24H": {"severity": "founder", "next_owner": "founder",
                             "message": "Unknown for at least 24 hours by source time."},
    "UNOWNED_24H": {"severity": "founder", "next_owner": "founder",
                    "message": "No named owner, at least 24 hours old by source time."},
    "STALE_REVIEW_SHA": {"severity": "reminder", "next_owner": "owner",
                         "message": "The approval is on an older commit; the current head is unreviewed."},
    "NO_DEPLOY_SOURCE": {"severity": "info", "next_owner": "SPM",
                         "message": "No deployment source; {n} merged missions cannot be verified live."},
    "LIVE_UNCONFIRMED": {"severity": "info", "next_owner": "SPM",
                         "message": "Latest READY production deployment is {sha}; serving is not confirmed."},
    "FALSE_DONE": {"owned_by": "delivery_closure"},
    "LIVE_CANNOT_VERIFY": {"owned_by": "delivery_closure"},
}

# The only input for live provability (R3-1). One reviewed edit here upgrades a repo; nothing is stored.
LIVE_SOURCE: dict[str, str] = {
    "cleanexpo/pi-dev-ops": "provable",
    "cleanexpo/restoreassist": "live_unconfirmed", "cleanexpo/synthex": "live_unconfirmed",
    "cleanexpo/unite-group": "live_unconfirmed",
    "cleanexpo/dr-sandbox": "none", "cleanexpo/dr-nrpg": "none", "cleanexpo/nrpg-onboarding-framework": "none",
    "cleanexpo/nodejs-starter-v1": "none", "cleanexpo/oh-my-codex": "none", "cleanexpo/carsi": "none",
    "cleanexpo/skills-library": "none", "cleanexpo/ato": "none",
}


def live_kind(repo: str) -> str:
    """provable, live_unconfirmed or none; case-insensitive; a repo missing from the table is none."""
    return LIVE_SOURCE.get(repo.lower(), "none") if isinstance(repo, str) else "none"


def human_reviewers() -> frozenset[str]:
    """Founder-owned allow-list of GitHub logins, trimmed and lower-cased; unset means empty."""
    raw = os.environ.get("TAO_DELIVERY_HUMAN_REVIEWERS", "")
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


@dataclass
class _Ctx:
    rid: str
    kind: str
    ref: str
    repo: str
    project_id: str
    issue: dict | None
    prs: list | None
    owner: str | None
    primary: dict | None = None
    extra: dict = field(default_factory=dict)


def _context(issue: dict | None, prs: list[dict] | None, repo: str, project_id: str) -> _Ctx:
    items = prs if isinstance(prs, list) else None
    if isinstance(issue, dict):
        rid = str(issue.get("identifier") or issue.get("id") or "unknown")
        assignee = issue.get("assignee")
        name = assignee.get("name") if isinstance(assignee, dict) else None
        owner = name if isinstance(name, str) and name.strip() else None
        ctx = _Ctx(rid, "mission", rid, repo, project_id, issue, items, owner)
    else:
        first = items[0] if items and isinstance(items[0], dict) else {}
        number = first.get("number")
        ctx = _Ctx(f"pr:{repo}#{number}", "orphan_pr", f"{repo}#{number}", repo, project_id, None, items, None)
    if items and len(items) == 1 and isinstance(items[0], dict):
        ctx.primary = items[0]
    return ctx


def _record(ctx: _Ctx, stage: str, **fields: object) -> dict:
    record = {"id": ctx.rid, "kind": ctx.kind, "project_id": ctx.project_id, "repo": ctx.repo, "ref": ctx.ref,
              "stage": stage, "reason": None, "owner": ctx.owner, "since": None, "age_source": None,
              "counted": None, "prs": pr_list(ctx.prs, ctx.repo), "pr_head_sha": None, "reviewed_head_sha": None,
              "authorised_head_sha": None, "merge_sha": None, "deployed_sha": None, "verified_sha": None,
              "tests_passed": False, "acceptance_passed": False,
              "live_source_provable": live_kind(ctx.repo) == "provable", "approval_identity_unverified": False}
    record.update({k: v for k, v in fields.items() if k in record and k != "authorised_head_sha"})
    return record


def _url(ctx: _Ctx) -> str | None:
    number = ctx.primary.get("number") if isinstance(ctx.primary, dict) else None
    if not isinstance(number, int) or isinstance(number, bool):
        return None
    return f"https://github.com/{ctx.primary.get('repo') or ctx.repo}/pull/{number}"


def _finding(ctx: _Ctx, key: str, code: str, severity: str, next_owner: str, message: str,
             since: str | None, age_source: str | None) -> dict:
    return {"key": key, "mission_id": ctx.rid, "code": code, "severity": severity, "next_owner": next_owner,
            "message": message, "ref": ctx.ref, "repo": ctx.repo, "since": since, "age_source": age_source,
            "url": _url(ctx)}


def _from_policy(ctx: _Ctx, found: Finding, since: str, age_source: str) -> dict:
    """The one converter for ``assess`` output: nothing is dropped, filtered or rewritten."""
    return _finding(ctx, found.key, found.code, found.severity, found.next_owner, found.message, since,
                    age_source)


def _coded(ctx: _Ctx, code: str, stage: str, head: str | None, since: str | None, age_source: str | None,
           **fmt: object) -> dict:
    row = RECONCILE_CODES[code]
    owner = (ctx.owner or "SPM") if row["next_owner"] in ("owner", "owner_or_SPM") else row["next_owner"]
    return _finding(ctx, finding_key(ctx.rid, stage, head, code), code, row["severity"], owner,
                    row["message"].format(**fmt), since, age_source)


def _aware(now: datetime) -> datetime | None:
    return now if now.tzinfo is not None and now.utcoffset() is not None else None


def _unknown(ctx: _Ctx, exc: Unclassifiable, now: datetime, first_seen: float | None) -> tuple[dict, list[dict]]:
    """UNKNOWN or MISSING_COMMIT: never through ``assess``; ages from source time (rule 1)."""
    if isinstance(exc.item, dict):
        ctx.primary = exc.item
    head = sha_or_none(ctx.primary.get("head_sha")) if isinstance(ctx.primary, dict) else None
    aware = _aware(now)
    source, age_source = source_time(ctx.issue, ctx.prs, aware or now.replace(tzinfo=timezone.utc),
                                     first_seen)
    since = iso(source)
    code = "MISSING_COMMIT" if exc.stage == "missing_commit" else "EVIDENCE_UNKNOWN"
    found = [_coded(ctx, code, "unknown", head, since, age_source, reason=exc.reason)]
    if aware is not None and aware - source >= _DAY:
        found.append(_coded(ctx, "EVIDENCE_UNKNOWN_24H", "unknown", head, since, age_source))
    record = _record(ctx, exc.stage, reason=exc.reason, since=since, age_source=age_source, pr_head_sha=head)
    return record, found


def _finish(ctx: _Ctx, now: datetime, stage: Stage, since: datetime, age_source: str,
            **fields: object) -> tuple[dict, list[dict]]:
    """Snapshot -> ``assess`` -> findings, plus STALE_REVIEW_SHA and UNOWNED_24H beside the policy's own."""
    snap = Snapshot(issue_id=ctx.rid, project_id=ctx.project_id, stage=stage, stage_since=since,
                    owner=ctx.owner, live_source_provable=live_kind(ctx.repo) == "provable",
                    **{k: v for k, v in fields.items() if k in _SNAPSHOT_FIELDS})
    try:
        policy = assess(snap, now)
    except ValueError:
        raise Unclassifiable("bad_timestamp") from None
    text = iso(since)
    found = [_from_policy(ctx, f, text, age_source) for f in policy]
    if ctx.extra.get("stale"):
        found.append(_coded(ctx, "STALE_REVIEW_SHA", "review_wait", snap.pr_head_sha, text, age_source))
    if any(f.code == "UNOWNED" for f in policy):
        source, source_name = source_time(ctx.issue, [ctx.primary or {}], now, None)  # the one guarded owner
        if now - source >= _DAY:
            found.append(_coded(ctx, "UNOWNED_24H", stage.value, snap.pr_head_sha, iso(source), source_name))
    return _record(ctx, stage.value, since=text, age_source=age_source, **fields), found


def _open_row(ctx: _Ctx, pr: dict, issue_state: str, now: datetime) -> tuple[dict, list[dict]]:
    """Rows 4, 5 and 7 to 11 for the one open PR."""
    ctx.primary = pr
    head = commit_of(pr, "open")
    checks, newest = checks_state(pr)
    verdicts = review_verdicts(pr, head, human_reviewers())
    created = parse_ts(pr.get("created_at"))
    base = {"pr_head_sha": head, "tests_passed": checks == "green",
            "reviewed_head_sha": sha_or_none((verdicts.approval or verdicts.stale or {}).get("commit_id")),
            "approval_identity_unverified": verdicts.unverified}
    if issue_state == "completed":
        return _finish(ctx, now, Stage.DONE, parse_ts(ctx.issue.get("completedAt")), "completedAt", **base)
    if pr.get("draft") is True:
        return _finish(ctx, now, Stage.BUILDING, created, "pr_created_at", **base)
    if checks == "not_green" or verdicts.blocked:
        since, source = (newest, "check_completed_at") if newest and newest > created else \
            (created, "pr_created_at")
        return _finish(ctx, now, Stage.BUILDING, since, source, **base)
    if checks == "none":
        raise Unclassifiable("no_ci", item=pr, verdict=True)
    if verdicts.approval is not None:
        return _finish(ctx, now, Stage.APPROVAL_WAIT, parse_ts(verdicts.approval.get("submitted_at")),
                       "review_submitted_at", **base)
    ctx.extra["stale"] = verdicts.stale is not None
    since, source = (newest, "check_completed_at") if newest else (created, "pr_created_at")
    return _finish(ctx, now, Stage.REVIEW_WAIT, since, source, **base)


def _merged_row(ctx: _Ctx, merged: list[dict], live: dict, now: datetime) -> tuple[dict, list[dict]]:
    """Row 6: every remaining PR merged; the newest one names the merge and head SHAs."""
    shas = [commit_of(m, "merged") for m in merged]
    times = [parse_ts(m.get("merged_at")) for m in merged]
    newest = max(range(len(merged)), key=lambda i: times[i])
    ctx.primary = merged[newest]
    fields = {"merge_sha": shas[newest], "pr_head_sha": sha_or_none(merged[newest].get("head_sha"))}
    if live_kind(ctx.repo) == "provable" and all_contained(live, shas):
        fields["deployed_sha"] = fields["verified_sha"] = shas[newest]
    return _finish(ctx, now, Stage.MERGED, times[newest], "merged_at", **fields)


def _orphan(ctx: _Ctx, now: datetime) -> tuple[dict, list[dict]]:
    """Rows 13 and 14: an open PR no mission links. Row 4 comes first: no head SHA is MISSING_COMMIT."""
    if len(ctx.prs) != 1:
        raise Unclassifiable("bad_input")
    head = commit_of(ctx.primary, "open")
    if reading("author_is_bot", {"login": ctx.primary.get("author_login"), "type": ctx.primary.get("author_type")}):
        return _record(ctx, "counted", counted="bot_prs"), []
    created = parse_ts(ctx.primary.get("created_at"))
    return _finish(ctx, now, Stage.BUILDING, created, "pr_created_at", pr_head_sha=head)


def _classify(ctx: _Ctx, live: dict, now: datetime) -> tuple[dict, list[dict]]:
    """The classification table, first match wins (spec section 9)."""
    if _aware(now) is None:
        raise Unclassifiable("bad_timestamp")
    if ctx.prs is None:
        raise Unclassifiable("links_incomplete")
    if not all(isinstance(item, dict) for item in ctx.prs):
        raise Unclassifiable("bad_input")
    if ctx.kind == "orphan_pr":
        return _orphan(ctx, now)
    state = ctx.issue.get("state")
    state = state.get("type") if isinstance(state, dict) else None
    if state not in ("started", "completed"):
        raise Unclassifiable("bad_issue_state", verdict=isinstance(state, str))  # a valid state not placed
    for name in ("startedAt", "completedAt"):  # null: not started / not completed; present must parse (row 1)
        if ctx.issue.get(name) is not None:
            parse_ts(ctx.issue[name])
    if not ctx.prs:
        return _record(ctx, "counted", counted=f"{state}_without_pr"), []
    states = [item_state(item) for item in ctx.prs]
    for item, item_kind in zip(ctx.prs, states):
        if item_kind == "error":  # a failed read: never counted as a pull; its own kind and reason
            stage = "missing_commit" if item.get("error") == "missing_commit" else "unknown"
            raise Unclassifiable(str(item.get("reason") or "unknown"), stage, item=item)
    kept = [(item, s) for item, s in zip(ctx.prs, states) if s != "closed"]
    if not kept:
        return _record(ctx, "counted", counted="closed_unmerged"), []
    opened = [item for item, s in kept if s == "open"]
    merged = [item for item, s in kept if s == "merged"]
    if len(opened) > 1 or (opened and merged):
        raise Unclassifiable("multiple_prs", verdict=True)  # distinct pulls, every one read whole
    return _open_row(ctx, opened[0], state, now) if opened else _merged_row(ctx, merged, live, now)


def judge(issue: dict | None, prs: list[dict] | None, live: dict, now: datetime, *, repo: str,
          project_id: str, first_seen: float | None = None) -> tuple[dict, list[dict], bool]:
    """``classify`` plus whether its input was valid. Fails closed: False whenever the classifier refused
    its input; True only for a placed record or a refusal marked ``verdict``."""
    ctx = _context(issue, prs, repo, project_id)
    try:
        return (*_classify(ctx, live, now), True)
    except Unclassifiable as exc:
        return (*_unknown(ctx, exc, now, first_seen), exc.verdict)
    except (TypeError, ValueError, KeyError, AttributeError, IndexError):
        return (*_unknown(ctx, Unclassifiable("bad_input"), now, first_seen), False)


def classify(issue: dict | None, prs: list[dict] | None, live: dict, now: datetime, *,
             repo: str, project_id: str, first_seen: float | None = None) -> tuple[dict, list[dict]]:
    """One record and its findings for a mission (``issue``) or an orphan PR (``issue is None``).
    Never raises for bad input data: such a record is UNKNOWN with a reason code."""
    return judge(issue, prs, live, now, repo=repo, project_id=project_id, first_seen=first_seen)[:2]


def repo_findings(repo: str, merged_unverifiable: int, vercel_sha: str | None) -> tuple[dict, list[dict]]:
    """The per-repo record and its NO_DEPLOY_SOURCE or LIVE_UNCONFIRMED info finding (rule 8)."""
    kind, sha = live_kind(repo), sha_or_none(vercel_sha)
    ctx = _Ctx(f"repo:{repo}", "repo", repo, repo, "", None, None, None)
    record = {"id": ctx.rid, "kind": "repo", "repo": repo, "ref": repo, "stage": "repo", "live_source": kind,
              "live_unconfirmed": sha, "merged_unverifiable": merged_unverifiable, "counted": None}
    if kind == "none":
        return record, [_coded(ctx, "NO_DEPLOY_SOURCE", "repo", "", None, None, n=merged_unverifiable)]
    if kind == "live_unconfirmed" and sha:
        return record, [_coded(ctx, "LIVE_UNCONFIRMED", "repo", sha, None, None, sha=sha)]
    return record, []
