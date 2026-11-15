"""RA-8100 D55: the longer checks of ``delivery_invariants`` (its rows name them; the rule in words is there).

PURE: the field domains only. Each takes an answer and what was asked (``a, q``), a whole state (``s``), a
state and its summary (``s, m``) or one stored record (``r``), and returns whether the rule holds. A
check may raise on a value outside its domain: ``delivery_invariants._broken`` counts that as broken.
"""
from __future__ import annotations

from .delivery_collect_fields import instant, sha

LABEL = {(False, False): "identical", (True, False): "ahead", (False, True): "behind", (True, True): "diverged"}
REFUSED = ("unknown", "missing_commit")
OPEN = ("building", "review_wait", "approval_wait", "done")
TOP = ("founder", "critical")
# The finding a refused record is always stored with (``delivery_stage._unknown`` raises it in the same step).
REFUSAL_CODE = {"unknown": "EVIDENCE_UNKNOWN", "missing_commit": "MISSING_COMMIT"}
_SOURCE_TIME = ("startedAt", "pr_created_at", "local_first_seen")  # ``delivery_stage_facts.source_time``
_CHECKED = ("pr_created_at", "check_completed_at")
# stage -> the sources its age is ever taken from (``delivery_stage``: ``_open_row``, ``_merged_row``, ``_unknown``)
AGE_SOURCES = {"merged": ("merged_at",), "done": ("completedAt",), "approval_wait": ("review_submitted_at",),
               "building": _CHECKED, "review_wait": _CHECKED, "unknown": _SOURCE_TIME, "missing_commit": _SOURCE_TIME}


def merge_base(a: dict, q: dict) -> bool:
    """The merge base is the one the status implies for the two commits asked."""
    found, base, head = sha(a["merge_base_commit"]["sha"]), sha(q["base"]), sha(q["head"])
    return {"identical": found == base == head, "ahead": found == base and base != head,
            "behind": found == head and base != head, "diverged": found not in (base, head)}[a["status"]]


def listed(a: dict, q: dict) -> bool:
    """ahead_by, total_commits and the list count the same distinct commits; none is the base or merge base."""
    shas = [sha(c["sha"]) for c in a["commits"]]
    outside = {sha(q["base"]), sha(a["merge_base_commit"]["sha"])}
    return a["ahead_by"] == a["total_commits"] == len(shas) == len(set(shas)) and not outside.intersection(shas)


def not_before(later: object, earlier: object) -> bool:
    """``later`` is not before ``earlier``. No ``later`` holds; a ``later`` with no ``earlier`` does not."""
    one, two = instant(later), instant(earlier)
    return later is None or (one is not None and two is not None and one >= two)


def tallies(m: dict) -> bool:
    """The two tallies count the same findings, and the top list is empty exactly when none is top."""
    top = sum(m["by_severity"].get(level, 0) for level in TOP)
    return sum(m["by_severity"].values()) == sum(m["by_code"].values()) \
        and (top == 0) == (not m["founder_or_critical"]) and len(m["founder_or_critical"]) <= top


def tallied(s: dict, m: dict) -> bool:
    """Every finding the tick tallied is a stored alert it raised (last seen at last_tick). A failed tick's
    tallies are partial (``LIMITS`` h)."""
    raised = [a for a in s["alerts"].values() if a["last_seen"] == s["last_tick"]]
    return "error" in m or (
        all(n <= sum(a["code"] == code for a in raised) for code, n in m["by_code"].items())
        and all(n <= sum(a["severity"] == level for a in raised) for level, n in m["by_severity"].items())
        and set(m["founder_or_critical"]) <= {a["ref"] for a in raised if a["severity"] in TOP})


def alerted(s: dict) -> bool:
    """Every refused record has its own stored alert: the code of its stage, under its id."""
    raised = {(a["mission_id"], a["code"]) for a in s["alerts"].values()}
    return all((r["id"], REFUSAL_CODE[r["stage"]]) in raised
               for r in s["missions"].values() if r["kind"] != "repo" and r["stage"] in REFUSED)


def names_itself(r: dict) -> bool:
    if r["kind"] == "mission":
        return r["ref"] == r["id"]
    if r["kind"] == "repo":
        return r["id"] == f"repo:{r['repo']}" and r["ref"] == r["repo"]
    (pull,) = r["prs"]  # an orphan record is exactly one pull
    return r["id"] == f"pr:{pull['repo']}#{pull['number']}" and r["ref"] == f"{pull['repo']}#{pull['number']}" \
        and pull["repo"] == r["repo"]


def fits_pulls(r: dict) -> bool:
    """A placed stage is one its pulls allow: merged with a merged pull and none open; any other with
    exactly one open pull and none merged; never beside a pull whose read failed."""
    states = [pull["state"] for pull in r["prs"]]
    opened, merged, failed = (states.count(kind) for kind in ("open", "merged", "error"))
    if r["stage"] in REFUSED:
        return True
    return failed == 0 and ((merged > 0 and opened == 0) if r["stage"] == "merged" else (opened == 1 and merged == 0))


def waiting(r: dict) -> bool:
    """Waiting for review or approval means green checks; approval means the approved head IS the head."""
    approved = r["reviewed_head_sha"] is not None and r["reviewed_head_sha"] == r["pr_head_sha"]
    return {"review_wait": r["tests_passed"] and not approved,
            "approval_wait": r["tests_passed"] and approved}.get(r["stage"], True)
