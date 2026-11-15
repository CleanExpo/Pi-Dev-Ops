"""RA-8100 D55: THE one list of relationships BETWEEN fields (founder ruling D55).

A field can be valid alone while two fields contradict each other: ``identical`` for two different
commits, ``complete`` beside a cut mission. Field domains stay with ``delivery_collect_fields`` (outside
answers) and ``delivery_reconcile_schema`` (the state file); every rule that needs TWO fields of one
answer, or of the one state file, is a row here and nowhere else. PURE: standard library and the field
domains only. A row is (name, the rule in words, the check). A check that raises is a broken rule.

``ANSWERS``: one entry per outside answer. The reader calls ``answer_problem`` and raises the entry's
reason code, so a contradictory answer fails the read; it is never evidence.
``STATE``: the state file. ``schema.problems`` calls ``state_problems``, and ``store.save`` and
``store.load`` both call ``schema.problems``: a contradictory state is never written, and one found on
disk is ``state_unreadable``. Every row relates fields INSIDE the file only (see ``LIMITS``, f).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .delivery_collect_fields import count, instant, sha

Row = tuple[str, str, Callable[..., bool]]

# What this list does NOT relate, each with its reason. A rule missing from the rows and from here is a gap.
LIMITS: tuple[str, ...] = (
    "a. Stored times against a clock that moved backward (last_complete or last_seen later than last_tick): "
    "a held entry keeps its older, later time, so the writer cannot guarantee the order.",
    "b. An alert against its record (the key formula, ref, repo, severity for its code): alerts outlive "
    "their record by THE RULE in the store, and the tile shows alerts only.",
    "c. Compare's total_commits against ahead_by: GitHub's page does not define what they count "
    "(EVIDENCE-API-DOCS, DC). The list length is checked against total_commits instead.",
    "d. A check run's status against its conclusion: the response schema does not state one. The "
    "classifier counts only status completed with conclusion success as green.",
    "e. A Linear issue's state type against startedAt and completedAt: judged per mission by the "
    "classifier (spec row 1), where a bad time is that mission's UNKNOWN, not a failed page.",
    "f. Anything a reviewed table decides (live_source_provable against LIVE_SOURCE): an edit to the "
    "table would turn every stored file unreadable.",
    "g. The pages of one paged read (count, duplicates, cursor): wholeness, owned by ``_paged`` and "
    "``fetch_missions``.",
    "h. A failed tick's counters (summary carries ``error``): partial by design; the tile shows the error.",
    "i. last_tick against the reader's clock: needs the time of reading, so the tile owns it "
    "(``delivery_reconcile_status.build``: ``state_from_future``).",
    "j. An entry older than a complete tick: THE RULE in the store keeps a subject neither proven whole nor "
    "known out of scope (D33), so an old entry beside ``complete`` is the rule working, not a contradiction.",
)

_LABEL = {(False, False): "identical", (True, False): "ahead", (False, True): "behind", (True, True): "diverged"}


def _merge_base(a: dict, q: dict) -> bool:
    found, base, head = sha(a["merge_base_commit"]["sha"]), sha(q["base"]), sha(q["head"])
    return {"identical": found == base == head, "ahead": found == base and base != head,
            "behind": found == head and base != head, "diverged": found not in (base, head)}[a["status"]]


def _after(a: dict, later: str, earlier: str) -> bool:
    """``later`` is not before ``earlier``; a time outside its domain is the field check's to refuse."""
    one, two = instant(a.get(later)), instant(a.get(earlier))
    return one is None or two is None or one >= two


ANSWERS: dict[str, dict[str, Any]] = {
    "compare": {"code": "compare_mismatch", "rows": (
        ("compare_fields", "ahead_by, behind_by and total_commits are counts; merge_base_commit and every listed "
         "commit name a SHA",
         lambda a, q: count(a["ahead_by"]) and count(a["behind_by"]) and count(a["total_commits"])
         and sha(a["merge_base_commit"]["sha"]) is not None and isinstance(a["commits"], list)
         and all(sha(c["sha"]) is not None for c in a["commits"])),
        ("compare_label", "status is the one the two counts give: identical 0/0, ahead n/0, behind 0/n, diverged n/n",
         lambda a, q: a["status"] == _LABEL[(a["ahead_by"] > 0, a["behind_by"] > 0)]),
        ("compare_list_whole", "commits are listed exactly when the head is ahead, and the list is whole: its "
         "length is total_commits (GitHub stops at 250)",
         lambda a, q: (a["ahead_by"] > 0) == bool(a["commits"]) and a["total_commits"] == len(a["commits"])),
        ("compare_ends_on_head", "a listed range ends on the head asked",
         lambda a, q: not a["commits"] or sha(a["commits"][-1]["sha"]) == sha(q["head"])),
        ("compare_merge_base", "the merge base agrees with the status and with BOTH commits asked: identical only "
         "when base and head asked are one commit; ahead, the base; behind, the head; diverged, neither",
         _merge_base),
    )},
    "pull": {"code": "malformed_pull", "rows": (
        ("pull_merged_has_time", "merged is true exactly when merged_at is set",
         lambda a, q: a["merged"] == (a["merged_at"] is not None)),
        ("pull_merged_is_closed", "a merged pull is closed", lambda a, q: not a["merged"] or a["state"] == "closed"),
        ("pull_merged_after_created", "a pull is not merged before it was created",
         lambda a, q: _after(a, "merged_at", "created_at")),
    )},
    "pulls_list": {"code": "malformed_pull", "rows": (
        ("listed_pull_is_open", "an item of the open list says open and is not merged (the list may omit merged)",
         lambda a, q: a["state"] == "open" and a.get("merged") is not True),
    )},
    "status": {"code": "malformed_status", "rows": (
        ("status_none_is_pending", "a combined status with no statuses is pending (GitHub: pending 'if there are "
         "no statuses'), never success or failure",
         lambda a, q: a["total_count"] != 0 or a["state"] == "pending"),
    )},
    "review": {"code": "malformed_review", "rows": (
        ("review_submitted_unless_pending", "only a PENDING review has no submitted_at",
         lambda a, q: a.get("submitted_at") is not None or a["state"] == "PENDING"),
    )},
    "commit": {"why": "one field is read (sha); its identity row owns it"},
    "check_run": {"why": "LIMITS d"},
    "linear_issue": {"why": "LIMITS e"},
    "vercel": {"why": "each deployment's fields are read alone (state, target, created, commit SHA)"},
}

_REFUSED = ("unknown", "missing_commit")
_OPEN = ("building", "review_wait", "approval_wait", "done")


def _summary(check: Callable[[dict, dict], bool]) -> Callable[[dict], bool]:
    """A summary rule: it holds for a state with no summary (no tick has run)."""
    return lambda s: s["summary"] is None or check(s, s["summary"])


def _each(pick: Callable[[dict], list], check: Callable[[dict], bool]) -> Callable[[dict], bool]:
    return lambda s: all(check(entry) for entry in pick(s))


def _records(*kinds: str) -> Callable[[dict], list]:
    return lambda s: [r for r in s["missions"].values() if r["kind"] in kinds]


def _all(s: dict) -> list:
    return [*s["missions"].values(), *s["alerts"].values()]


def _top(m: dict) -> bool:
    top = m["by_severity"].get("founder", 0) + m["by_severity"].get("critical", 0)
    return sum(m["by_severity"].values()) == sum(m["by_code"].values()) \
        and (top == 0) == (not m["founder_or_critical"]) and len(m["founder_or_critical"]) <= top


def _names_itself(r: dict) -> bool:
    if r["kind"] == "mission":
        return r["ref"] == r["id"]
    if r["kind"] == "repo":
        return r["id"] == f"repo:{r['repo']}" and r["ref"] == r["repo"]
    (pull,) = r["prs"]  # an orphan record is exactly one pull
    return r["id"] == f"pr:{pull['repo']}#{pull['number']}" and r["ref"] == f"{pull['repo']}#{pull['number']}" \
        and pull["repo"] == r["repo"]


STATE: tuple[Row, ...] = (
    ("never_run_is_empty", "no tick has run exactly when there is no summary, and then nothing is stored: no "
     "record, no alert, no checkpoint",
     lambda s: (s["last_tick"] is None) == (s["summary"] is None) and (s["last_tick"] is not None or not (
         s["missions"] or s["alerts"] or s["checkpoint"]["last_complete"] is not None))),
    ("complete_has_no_reason", "the tick is complete exactly when it names no cut (incomplete is empty) and no "
     "error: complete beside a reason, or incomplete with none, is a contradiction",
     _summary(lambda s, m: m["complete"] == (not m["incomplete"] and "error" not in m))),
    ("complete_is_checkpointed", "a complete tick is the last complete one: last_complete is last_tick",
     _summary(lambda s, m: not m["complete"] or s["checkpoint"]["last_complete"] == s["last_tick"])),
    ("tick_at_is_last_tick", "the summary's tick_at and last_tick are the same instant",
     _summary(lambda s, m: abs(instant(m["tick_at"]).timestamp() - s["last_tick"]) < 0.001)),
    ("held_ids_cover_the_count", "no held id is listed twice, and (on a tick with no error) not_refreshed counts "
     "no more subjects than not_refreshed_ids names",
     _summary(lambda s, m: len(set(m["not_refreshed_ids"])) == len(m["not_refreshed_ids"])
              and ("error" in m or m["not_refreshed"] <= len(m["not_refreshed_ids"])))),
    ("tallies_agree", "by_severity and by_code count the same findings, and founder_or_critical is empty exactly "
     "when no finding is founder or critical", _summary(lambda s, m: _top(m))),
    ("seen_in_order", "nothing is last seen before it was first seen, or refreshed after it was last seen",
     _each(_all, lambda e: e["first_seen"] <= e["last_seen"] and e.get("refreshed_at", e["last_seen"]) <= e["last_seen"])),
    ("alert_counted_once_is_new", "an alert raised once was first and last seen at the same time",
     _each(lambda s: list(s["alerts"].values()), lambda a: a["count"] > 1 or a["first_seen"] == a["last_seen"])),
    ("record_names_itself", "a mission's ref is its id; an orphan's id and ref name its one pull; a repo record's "
     "id and ref name its repo", _each(_records("mission", "orphan_pr", "repo"), _names_itself)),
    ("refused_has_a_reason", "a record carries a reason exactly when its stage is unknown or missing_commit",
     _each(_records("mission", "orphan_pr"), lambda r: (r["stage"] in _REFUSED) == (r["reason"] is not None))),
    ("merge_fields_agree", "merge_sha is set exactly at stage merged; deployed_sha and verified_sha are set "
     "together, only to the merge_sha, and only where the live source is provable",
     _each(_records("mission", "orphan_pr"), lambda r: (r["merge_sha"] is not None) == (r["stage"] == "merged")
           and r["deployed_sha"] == r["verified_sha"]
           and (r["verified_sha"] is None or (r["verified_sha"] == r["merge_sha"] and r["live_source_provable"])))),
    ("review_fields_need_an_open_pull", "tests_passed, reviewed_head_sha and approval_identity_unverified are set "
     "only at a stage with an open pull, beside its head SHA",
     _each(_records("mission", "orphan_pr"),
           lambda r: not (r["tests_passed"] or r["reviewed_head_sha"] is not None or r["approval_identity_unverified"])
           or (r["stage"] in _OPEN and r["pr_head_sha"] is not None))),
    ("since_has_its_source", "since and age_source are set together or not at all",
     _each(lambda s: [e for e in _all(s) if "since" in e], lambda e: (e["since"] is None) == (e["age_source"] is None))),
    ("repo_live_fields_agree", "a repo record names an unconfirmed live SHA only when its source is "
     "live_unconfirmed, and a provable repo has no unverifiable merge",
     _each(_records("repo"), lambda r: (r["live_unconfirmed"] is None or r["live_source"] == "live_unconfirmed")
           and (r["live_source"] != "provable" or r["merged_unverifiable"] == 0))),
)


def _broken(rows: tuple[Row, ...], *args: Any) -> list[str]:
    out = []
    for name, _rule, holds in rows:
        try:
            ok = holds(*args) is True
        except (TypeError, KeyError, AttributeError, ValueError, IndexError, OverflowError):
            ok = False  # a rule that cannot be evaluated is not a rule that holds
        if not ok:
            out.append(name)
    return out


def answer_broken(kind: str, answer: object, **asked: object) -> list[str]:
    """The names of the rows of ``kind`` this answer breaks (empty: its fields agree)."""
    return _broken(ANSWERS[kind].get("rows", ()), answer, asked)


def answer_problem(kind: str, answer: object, **asked: object) -> str | None:
    """The reason code of ``kind`` when the answer's fields contradict each other or what was asked."""
    return ANSWERS[kind]["code"] if answer_broken(kind, answer, **asked) else None


def state_problems(state: dict) -> list[str]:
    """``invariant:<name>`` for every broken row. Call only on a state whose every field is in its domain."""
    return [f"invariant:{name}" for name in _broken(STATE, state)]
