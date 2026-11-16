"""RA-8100 D55: THE one list of relationships BETWEEN fields (founder ruling D55).

A field can be valid alone while two fields contradict each other: ``identical`` for two different
commits, ``complete`` beside a cut mission. Field domains stay with ``delivery_collect_fields`` (outside
answers) and ``delivery_reconcile_schema`` (the state file); every rule that needs TWO fields is a row
here and nowhere else. PURE. A row is (name, the fields it relates, the rule in words, the check); the
longer checks live in ``delivery_invariant_checks``. A check that raises is a broken rule.

``ANSWERS``: one entry per outside answer. The reader calls ``answer_problem`` and raises the entry's
reason code, so a contradictory answer fails the read; it is never evidence.
``STATE``: the state file. ``schema.problems`` calls ``state_problems``, and ``store.save`` and
``store.load`` both call ``schema.problems``: a contradictory state is never written, and one found on
disk is ``state_unreadable``.
``READINGS``: one fact read from two fields; nothing is refused, a disagreement takes the cautious reading.
SCOPE (founder ruling D56): the list answers for what the tile shows and what a stage claims (verified,
approved, green, complete). What it leaves out on purpose is in ``LIMITS``.
COMPLETENESS IS CHECKED, NOT CLAIMED: every field read from an outside answer (the field inventory) and
every key of every stored dict (the schema) must be named by a row or by ``ALONE`` with its reason, and
a row must name exactly the fields its check reads (tests/test_delivery_invariant_coverage.py).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import delivery_invariant_checks as chk
from .delivery_collect_fields import count, instant, sha

Row = tuple[str, str, str, Callable[..., bool]]

# Relationships this list deliberately does NOT check, each with its reason.
LIMITS: tuple[str, ...] = (
    "a. Stored times against a clock that moved backward (last_complete or last_seen later than last_tick): "
    "a held entry keeps its older, later time, so the writer cannot guarantee the order.",
    "b. An alert against its record beyond a refused record's own alert (the key formula, ref, repo, the "
    "severity for its code): alerts outlive their record by THE RULE in the store.",
    "c. What GitHub means by ahead_by, behind_by and total_commits: its page does not define them "
    "(EVIDENCE-API-DOCS, DC). The rows require them to agree with each other and with the list; a real "
    "answer that does not is refused (compare_mismatch), never verified.",
    "d. A check run's completed_at against the pull's times: a run may finish before its pull is opened.",
    "e. A Linear issue's state type against startedAt and completedAt: judged per mission by the "
    "classifier (spec row 1), where a bad time is that mission's UNKNOWN, not a failed page.",
    "f. Anything a reviewed table decides (live_source_provable against LIVE_SOURCE, a finding's severity "
    "and owner for its code): an edit to the table would turn every stored file unreadable.",
    "g. The pages of one paged read (count, duplicates, cursor): wholeness, owned by ``_paged`` and "
    "``fetch_missions``.",
    "h. A failed tick's counters (summary carries ``error``): partial by design; the tile shows the error.",
    "i. last_tick against the reader's clock: needs the time of reading, so the tile owns it "
    "(``delivery_reconcile_status.build``: ``state_from_future``).",
    "j. An entry older than a complete tick: THE RULE in the store keeps a subject neither proven whole nor "
    "known out of scope (D33), so an old entry beside ``complete`` is the rule working, not a contradiction.",
    "k. Any outside time against the tick's clock (a review, merge, check or deployment dated in the "
    "future): the clock is this machine's and may be wrong; a time is related only to times of the same pull. "
    "A stored since is such a time: it may be later than last_tick.",
    "l. A summary's per-tick counters against what is stored: they tally what that tick read, and a held "
    "subject is not counted again.",
    "m. Which pull a stored head or merge SHA belongs to: a record stores only repo, number and state per pull.",
    "n. A repo record's merged_unverifiable against the stored merged records (D56): a per-tick tally like l, "
    "and the tile does not show it.",
    "o. RAILWAY_GIT_COMMIT_SHA against BUILD_REVISION (D56): two names for one setting; the first set is used.",
    "p. A stored alert's code, message, owner and link against anything but its own domain: an alert never "
    "says healthy, and its text comes from a reviewed table (f).",
)

# Fields no row relates, by reason. A field in neither a row nor here fails the coverage test.
ALONE: dict[str, str] = {
    "identity: compared with what was asked, by its row of delivery_collect_fields.IDENTITY":
        "pull.number pull.base pull.base.repo pull.base.repo.full_name commit.sha check_run.head_sha status.sha "
        "status.repository status.repository.full_name review.pull_request_url compare.base_commit "
        "compare.base_commit.sha pulls_list.base pulls_list.base.repo pulls_list.base.repo.full_name "
        "linear_page.project linear_page.project.id",
    "wholeness of a list or page: owned by _paged, _page and fetch_missions (LIMITS g)":
        "pulls_list.number check_runs.check_runs check_runs.total_count check_run.id review.id "
        "linear_page.project.issues linear_page.project.issues.nodes linear_page.project.issues.pageInfo.hasNextPage "
        "linear_page.project.issues.pageInfo.endCursor linear_links.attachments linear_links.attachments.nodes "
        "linear_links.attachments.pageInfo.hasNextPage vercel.deployments",
    "a fact handed to the classifier as read: it is judged per mission against OTHER answers (the head, the "
    "allow-list, the clock), not against a field of its own answer (LIMITS d, e, k)":
        "pulls_list.draft pulls_list.created_at pulls_list.head pulls_list.head.sha pulls_list.user "
        "pull.draft pull.head pull.head.sha pull.user pull_merged.merge_commit_sha pull_merged.merged_at review.user review.user.login "
        "review.commit_id linear_issue.id linear_issue.identifier linear_issue.state "
        "linear_issue.state.type linear_issue.startedAt linear_issue.completedAt linear_issue.assignee "
        "linear_issue.assignee.name linear_links.description linear_links.attachments.nodes.url vercel.state "
        "vercel.created vercel.target vercel.meta vercel.meta.githubCommitSha env.RAILWAY_GIT_COMMIT_SHA "
        "env.BUILD_REVISION",
    "read for its own domain only; no decision uses it (a review counts by its login against the allow-list)":
        "review.user.type",
    "stored: one fixed value, or the selector of the record's shape (the schema's domain)":
        "state.version record.kind record.counted record.authorised_head_sha record.acceptance_passed repo.kind "
        "repo.stage repo.counted",
    "stored: carried as read, or decided by a reviewed table; no other stored field bounds it (LIMITS b, f)":
        "record.project_id record.owner alert.key alert.next_owner alert.message "
        "alert.repo alert.url",
    "stored: a per-tick tally of what that tick read (LIMITS l)":
        "summary.missions summary.skipped_repos summary.unqueryable_projects summary.refs_outside_scope "
        "summary.bot_prs summary.closed_unmerged summary.started_without_pr summary.completed_without_pr "
        "summary.vercel_unreadable summary.budget_left",
}

ANSWERS: dict[str, dict[str, Any]] = {
    "compare": {"code": "compare_mismatch", "rows": (
        ("compare_fields", "compare.ahead_by compare.behind_by compare.total_commits compare.merge_base_commit "
         "compare.merge_base_commit.sha compare.commits compare.commits.sha",
         "ahead_by, behind_by and total_commits are counts; merge_base_commit and every listed commit name a SHA",
         lambda a, q: count(a["ahead_by"]) and count(a["behind_by"]) and count(a["total_commits"])
         and sha(a["merge_base_commit"]["sha"]) is not None and isinstance(a["commits"], list)
         and all(sha(c["sha"]) is not None for c in a["commits"])),
        ("compare_label", "compare.status compare.ahead_by compare.behind_by",
         "status is the one the two counts give: identical 0/0, ahead n/0, behind 0/n, diverged n/n",
         lambda a, q: a["status"] == chk.LABEL[(a["ahead_by"] > 0, a["behind_by"] > 0)]),
        ("compare_list_whole", "compare.ahead_by compare.total_commits compare.commits compare.commits.sha "
         "compare.merge_base_commit compare.merge_base_commit.sha",
         "ahead_by, total_commits and the length of the list are one number (GitHub stops listing at 250), no "
         "commit is listed twice, and neither the base asked nor the merge base is in the list", chk.listed),
        ("compare_ends_on_head", "compare.commits compare.commits.sha", "a listed range ends on the head asked",
         lambda a, q: not a["commits"] or sha(a["commits"][-1]["sha"]) == sha(q["head"])),
        ("compare_merge_base", "compare.status compare.merge_base_commit compare.merge_base_commit.sha",
         "the merge base agrees with the status and with BOTH commits asked: identical only when base and head "
         "asked are one commit; ahead, the base; behind, the head; diverged, neither", chk.merge_base),
    )},
    "pull": {"code": "malformed_pull", "rows": (
        ("pull_merged_has_time", "pull.merged pull.merged_at", "merged is true exactly when merged_at is set",
         lambda a, q: a["merged"] == (a["merged_at"] is not None)),
        ("pull_merged_is_closed", "pull.merged pull.state", "a merged pull is closed",
         lambda a, q: not a["merged"] or a["state"] == "closed"),
        ("pull_merged_after_created", "pull.merged_at pull.created_at", "a pull is not merged before it was created",
         lambda a, q: chk.not_before(a["merged_at"], a["created_at"])),
    )},
    "pulls_list": {"code": "malformed_pull", "rows": (
        ("listed_pull_is_open", "pulls_list.state pulls_list.merged pulls_list.merged_at",
         "an item of the open list says open, is not merged and has no merge time (the list may omit both)",
         lambda a, q: a["state"] == "open" and a.get("merged") is not True and a.get("merged_at") is None),
    )},
    "status": {"code": "malformed_status", "rows": (
        ("status_none_is_pending", "status.state status.total_count",
         "a combined status with no statuses is pending (GitHub: pending 'if there are no statuses'), never "
         "success or failure", lambda a, q: a["total_count"] != 0 or a["state"] == "pending"),
    )},
    "review": {"code": "malformed_review", "rows": (
        ("review_submitted_unless_pending", "review.state review.submitted_at",
         "only a PENDING review has no submitted_at",
         lambda a, q: a.get("submitted_at") is not None or a["state"] == "PENDING"),
        ("review_not_before_its_pull", "review.submitted_at",
         "a review is not submitted before its pull was created (the pull's created_at is passed as asked)",
         lambda a, q: chk.not_before(a.get("submitted_at"), q["created"])),
    )},
    "check_run": {"code": "malformed_check_run", "rows": (
        ("check_run_finished_together", "check_run.status check_run.conclusion check_run.completed_at",
         "a run is completed exactly when it has a conclusion, and exactly when it has a completed_at",
         lambda a, q: (a["status"] == "completed") == (a["conclusion"] is not None) == (a["completed_at"] is not None)),
    )},
    "commit": {"why": "one field is read (sha); its identity row owns it"},
    "linear_issue": {"why": "LIMITS e"},
    "vercel": {"why": "each deployment's fields are read alone (state, target, created, commit SHA)"},
}


def _summary(check: Callable[[dict, dict], bool]) -> Callable[[dict], bool]:
    """A summary rule: it holds for a state with no summary (no tick has run)."""
    return lambda s: s["summary"] is None or check(s, s["summary"])


def _each(pick: Callable[[dict], list], check: Callable[[dict], bool]) -> Callable[[dict], bool]:
    return lambda s: all(check(entry) for entry in pick(s))


def _records(*kinds: str) -> Callable[[dict], list]:
    return lambda s: [r for r in s["missions"].values() if r["kind"] in kinds]


def _all(s: dict) -> list:
    return [*s["missions"].values(), *s["alerts"].values()]


_PLACED = _records("mission", "orphan_pr")
_SEEN = " ".join(f"{kind}.{name}" for kind in ("record", "repo", "alert") for name in ("first_seen", "last_seen"))

STATE: tuple[Row, ...] = (
    ("never_run_is_empty", "state.last_tick state.summary state.missions state.alerts state.checkpoint "
     "checkpoint.last_complete",
     "no tick has run exactly when there is no summary, and then nothing is stored: no record, no alert, no "
     "checkpoint",
     lambda s: (s["last_tick"] is None) == (s["summary"] is None) and (s["last_tick"] is not None or not (
         s["missions"] or s["alerts"] or s["checkpoint"]["last_complete"] is not None))),
    ("complete_has_no_reason", "summary.complete summary.incomplete summary.error",
     "the tick is complete exactly when it names no cut (incomplete is empty) and no error: complete beside a "
     "reason, or incomplete with none, is a contradiction",
     _summary(lambda s, m: m["complete"] == (not m["incomplete"] and "error" not in m))),
    ("complete_is_checkpointed", "summary.complete checkpoint.last_complete state.last_tick",
     "a complete tick is the last complete one: last_complete is last_tick",
     _summary(lambda s, m: not m["complete"] or s["checkpoint"]["last_complete"] == s["last_tick"])),
    ("tick_at_is_last_tick", "summary.tick_at state.last_tick", "the summary's tick_at and last_tick are the same instant",
     _summary(lambda s, m: abs(instant(m["tick_at"]).timestamp() - s["last_tick"]) < 0.001)),
    ("held_ids_cover_the_count", "summary.not_refreshed summary.not_refreshed_ids summary.error",
     "no held id is listed twice, and (on a tick with no error) not_refreshed counts no more subjects than "
     "not_refreshed_ids names",
     _summary(lambda s, m: len(set(m["not_refreshed_ids"])) == len(m["not_refreshed_ids"])
              and ("error" in m or m["not_refreshed"] <= len(m["not_refreshed_ids"])))),
    ("tallies_agree", "summary.by_severity summary.by_code summary.founder_or_critical",
     "by_severity and by_code count the same findings, and founder_or_critical is empty exactly when no finding "
     "is founder or critical", _summary(lambda s, m: chk.tallies(m))),
    ("tallies_are_stored_alerts", "summary.by_severity summary.by_code summary.founder_or_critical summary.error "
     "alert.code alert.severity alert.ref alert.last_seen state.last_tick",
     "on a tick with no error, every finding tallied (by code, by severity, in the top list by ref) is a stored "
     "alert that tick raised: one last seen at last_tick", _summary(chk.tallied)),
    ("seen_in_order", f"{_SEEN} record.refreshed_at",
     "nothing is last seen before it was first seen, or refreshed after it was last seen",
     _each(_all, lambda e: e["first_seen"] <= e["last_seen"] and e.get("refreshed_at", e["last_seen"]) <= e["last_seen"])),
    ("alert_counted_once_is_new", "alert.count alert.first_seen alert.last_seen",
     "an alert raised once was first and last seen at the same time",
     _each(lambda s: list(s["alerts"].values()), lambda a: a["count"] > 1 or a["first_seen"] == a["last_seen"])),
    ("record_names_itself", "record.id record.ref record.repo record.prs pr.repo pr.number repo.id repo.ref "
     "repo.repo",
     "a mission's ref is its id; an orphan's id and ref name its one pull; a repo record's id and ref name its repo",
     _each(_records("mission", "orphan_pr", "repo"), chk.names_itself)),
    ("refused_has_a_reason", "record.stage record.reason",
     "a record carries a reason exactly when its stage is unknown or missing_commit",
     _each(_PLACED, lambda r: (r["stage"] in chk.REFUSED) == (r["reason"] is not None))),
    ("refused_has_its_alert", "record.stage record.id alert.mission_id alert.code",
     "a record at stage unknown or missing_commit is stored with its own alert (EVIDENCE_UNKNOWN or "
     "MISSING_COMMIT under its id): a refused record is never silent", chk.alerted),
    ("stage_fits_its_pulls", "record.stage record.prs pr.state",
     "stage merged has a merged pull and no open one; building, review_wait, approval_wait and done have exactly "
     "one open pull and no merged one; neither stands beside a pull whose read failed", _each(_PLACED, chk.fits_pulls)),
    ("orphan_is_never_past_building", "record.stage record.tests_passed record.reviewed_head_sha "
     "record.approval_identity_unverified",
     "a pull no mission links is building or refused, and carries no check or review result",
     _each(_records("orphan_pr"), lambda r: r["stage"] in ("building", *chk.REFUSED) and not (
         r["tests_passed"] or r["reviewed_head_sha"] is not None or r["approval_identity_unverified"]))),
    ("merge_fields_agree", "record.stage record.merge_sha record.deployed_sha record.verified_sha "
     "record.live_source_provable",
     "merge_sha is set exactly at stage merged; deployed_sha and verified_sha are set together, only to the "
     "merge_sha, and only where the live source is provable",
     _each(_PLACED, lambda r: (r["merge_sha"] is not None) == (r["stage"] == "merged")
           and r["deployed_sha"] == r["verified_sha"]
           and (r["verified_sha"] is None or (r["verified_sha"] == r["merge_sha"] and r["live_source_provable"])))),
    ("review_fields_need_an_open_pull", "record.stage record.tests_passed record.reviewed_head_sha "
     "record.approval_identity_unverified record.pr_head_sha",
     "a stage with an open pull names its head SHA, and tests_passed, reviewed_head_sha and "
     "approval_identity_unverified are set only at such a stage",
     _each(_PLACED, lambda r: r["pr_head_sha"] is not None if r["stage"] in chk.OPEN else not (
         r["tests_passed"] or r["reviewed_head_sha"] is not None or r["approval_identity_unverified"]))),
    ("waiting_is_green_and_reviewed", "record.stage record.tests_passed record.reviewed_head_sha record.pr_head_sha",
     "review_wait and approval_wait have green checks; approval_wait has an approved head that IS the pull's "
     "head; review_wait has none on the head", _each(_PLACED, chk.waiting)),
    ("age_source_fits_stage", "record.stage record.age_source",
     "a record's age comes from a source its stage uses: merged_at for merged, completedAt for done, "
     "review_submitted_at for approval_wait, the pull or its checks for building and review_wait, the source "
     "time for a refused record", _each(_PLACED, lambda r: r["age_source"] in chk.AGE_SOURCES[r["stage"]])),
    ("since_has_its_source", "record.since record.age_source alert.since alert.age_source",
     "since and age_source are set together or not at all, and a mission or orphan record always has both",
     lambda s: all((e["since"] is None) == (e["age_source"] is None) for e in [*_PLACED(s), *s["alerts"].values()])
     and all(r["since"] is not None for r in _PLACED(s))),
    ("repo_live_fields_agree", "repo.live_source repo.live_unconfirmed repo.merged_unverifiable",
     "a repo record names an unconfirmed live SHA only when its source is live_unconfirmed, and a provable repo "
     "has no unverifiable merge",
     _each(_records("repo"), lambda r: (r["live_unconfirmed"] is None or r["live_source"] == "live_unconfirmed")
           and (r["live_source"] != "provable" or r["merged_unverifiable"] == 0))),
)


def _broken(rows: tuple[Row, ...], *args: Any) -> list[str]:
    out = []
    for name, _fields, _rule, holds in rows:
        try:
            ok = holds(*args) is True
        except (TypeError, KeyError, AttributeError, ValueError, IndexError, OverflowError):
            ok = False  # a rule that cannot be evaluated is not a rule that holds
        if not ok:
            out.append(name)
    return out


READINGS: tuple[Row, ...] = (
    ("author_is_bot", "pulls_list.user.login pulls_list.user.type pull.user.login pull.user.type",
     "an author is a bot only when the type says Bot AND the login ends with [bot]; where the two disagree "
     "the pull is a person's: it is placed and reported, never counted away (D56)",
     lambda u: u["type"] == "Bot" and u["login"].endswith("[bot]")),
)


def reading(name: str, *args: Any) -> bool:
    """Whether the named row of ``READINGS`` holds; a value it cannot be read from is False."""
    (row,) = (row for row in READINGS if row[0] == name)  # an unknown name is a programming error
    return not _broken((row,), *args)


def answer_broken(kind: str, answer: object, **asked: object) -> list[str]:
    """The names of the rows of ``kind`` this answer breaks (empty: its fields agree)."""
    return _broken(ANSWERS[kind].get("rows", ()), answer, asked)


def answer_problem(kind: str, answer: object, **asked: object) -> str | None:
    """The reason code of ``kind`` when the answer's fields contradict each other or what was asked."""
    return ANSWERS[kind]["code"] if answer_broken(kind, answer, **asked) else None


def state_problems(state: dict) -> list[str]:
    """``invariant:<name>`` for every broken row. Call only on a state whose every field is in its domain."""
    return [f"invariant:{name}" for name in _broken(STATE, state)]
