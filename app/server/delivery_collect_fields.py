"""RA-8100 B5e: the one owner of every outside field's domain (GitHub, Linear, Vercel).

PURE. Standard library only: no network, no file, no app import, no exception of its own. Each
domain has exactly one function here; the collector (single-item and list paths alike) and the
classifier call it and raise their own reason code. What null, absent or empty MEANS is decided by
the caller per field and recorded in FIELD-INVENTORY-B5e.md; this module only says "in the domain".
Every closed list is closed: a value GitHub, Linear or Vercel adds later is outside the domain and
fails the read, so it can never be read as passing, approved, complete or deployed.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

SHA = re.compile(r"[0-9a-fA-F]{40}")
_TS = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_LOGIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:\[bot\])?")
_LINEAR_ID = re.compile(r"[A-Za-z][A-Za-z0-9]{0,9}-[0-9]{1,9}")
_NODE_ID = re.compile(r"[\w-]{1,64}")
_TEXT_MAX = 256

PULL_STATES = frozenset({"open", "closed"})
CHECK_STATUSES = frozenset({"queued", "in_progress", "completed", "waiting", "requested", "pending"})
CHECK_CONCLUSIONS = frozenset({"success", "failure", "neutral", "cancelled", "skipped", "timed_out",
                               "action_required", "stale", "startup_failure"})
REVIEW_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"})
STATUS_STATES = frozenset({"success", "pending", "failure", "error"})
COMPARE_STATUSES = frozenset({"identical", "ahead", "behind", "diverged"})
USER_TYPES = frozenset({"User", "Bot", "Organization", "Mannequin"})
LINEAR_STATE_TYPES = frozenset({"triage", "backlog", "unstarted", "started", "completed", "canceled"})
VERCEL_STATES = frozenset({"BUILDING", "ERROR", "INITIALIZING", "QUEUED", "READY", "CANCELED", "DELETED"})


def sha(value: object) -> str | None:
    """A 40-hex commit SHA in lower case, else None (format only; the caller decides what absent means)."""
    return value.lower() if isinstance(value, str) and SHA.fullmatch(value) else None


def no_commit(value: object) -> bool:
    """Absent, null or empty: the field names no commit at all (spec row 4 for a head or merge SHA)."""
    return value is None or (isinstance(value, str) and value == "")


def instant(value: object) -> datetime | None:
    """An ISO-8601 date-time WITH a timezone that parses, in UTC; else None."""
    if not isinstance(value, str) or not _TS.match(value):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    try:
        return parsed.astimezone(timezone.utc)
    except OverflowError:  # valid text whose UTC instant is outside year 1..9999: not a usable time
        return None


def is_instant(value: object) -> bool:
    return instant(value) is not None


def positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def flag(value: object) -> bool:
    return isinstance(value, bool)


def member(value: object, allowed: frozenset[str]) -> bool:
    """In the closed list; a non-text value (even an unhashable one) is outside it."""
    return isinstance(value, str) and value in allowed


def login(value: object) -> bool:
    """A GitHub login: 1-39 letters, digits or dashes, not starting with a dash; ``[bot]`` allowed."""
    return isinstance(value, str) and _LOGIN.fullmatch(value) is not None


def linear_identifier(value: object) -> bool:
    """A Linear issue identifier such as ``RA-8100``."""
    return isinstance(value, str) and _LINEAR_ID.fullmatch(value) is not None


def node_id(value: object) -> bool:
    """An opaque API node id (Linear issue id): word characters and dashes, 1-64 long."""
    return isinstance(value, str) and _NODE_ID.fullmatch(value) is not None


def text(value: object) -> bool:
    """Bounded non-empty text (a display name or a cursor)."""
    return isinstance(value, str) and 0 < len(value) <= _TEXT_MAX and not value.isspace()


def maybe(value: object, check: object) -> bool:
    """Null, or in the domain ``check`` decides."""
    return value is None or bool(check(value))  # type: ignore[operator]


def present(item: object, key: str, check: object) -> bool:
    """A documented-nullable field: the key must be there (absent is a cut answer), its value null or in domain."""
    return isinstance(item, dict) and key in item and maybe(item[key], check)


def linear_links(issue: object) -> bool:
    """The link fields ``pr_refs`` reads: description text or null; each attachment url text or null.
    The attachment list's own wholeness (``hasNextPage``) stays with ``pr_refs``."""
    if not present(issue, "description", lambda v: isinstance(v, str)):
        return False
    conn = issue.get("attachments")
    nodes = conn.get("nodes") if isinstance(conn, dict) else None
    if not isinstance(nodes, list):
        return True  # not whole: ``pr_refs`` returns None and the links are incomplete
    return all(not isinstance(n, dict) or isinstance(n.get("url"), str) for n in nodes)  # Attachment.url: String!


# RA-8100 B6: THE ONE OWNER of "the answer names the thing that was asked". One row per outside request
# the collector makes; ``reader`` is the function that makes it (a test walks the source and fails on a
# request with no row). ``checks``: (answer path, asked key, kind); every one must hold or the read
# fails with ``code``. A row with no check carries ``why``: the written reason the answer has no identity.
IDENTITY: dict[str, dict] = {
    "pulls_list": {"reader": "open_prs", "asked": ("repo",), "code": "pulls_list_mismatch",
                   "checks": ((("base", "repo", "full_name"), "repo", "repo"),)},
    "pull": {"reader": "pr_evidence", "asked": ("number",), "checks": ((("number",), "number", "int"),),
             "code": "pull_mismatch"},
    "commit": {"reader": "_commit", "asked": ("sha",), "checks": ((("sha",), "sha", "sha"),), "code": "commit_mismatch"},
    "check_run": {"reader": "pr_evidence", "asked": ("head",), "checks": ((("head_sha",), "head", "sha"),),
                  "code": "check_run_mismatch"},
    "status": {"reader": "pr_evidence", "asked": ("head",), "checks": ((("sha",), "head", "sha"),),
               "code": "status_mismatch"},
    "review": {"reader": "pr_evidence", "asked": ("pull",), "code": "review_mismatch",
               "checks": ((("pull_request_url",), "pull", "suffix"),)},
    "compare": {"reader": "compare_status", "asked": ("base", "head"), "code": "compare_mismatch",
                "checks": ((("base_commit", "sha"), "base", "sha"), (("commits",), "head", "tail"))},
    "linear_issue": {"reader": "fetch_missions", "asked": ("project",), "code": "linear_project_mismatch",
                     "checks": ((("project", "id"), "project", "text"),)},
    "vercel": {"reader": "vercel_latest_ready", "asked": ("project", "team"), "checks": (), "code": None,
               "why": "a list filtered by projectId, target and state in the query; the repo's fixtures and "
                      "vercel_monitor read no field of a deployment item that names its project, so none is checked"},
}
_ABSENT = object()


def _at(answer: object, path: tuple[str, ...]) -> object:
    for part in path:
        if not isinstance(answer, dict) or part not in answer:
            return _ABSENT
        answer = answer[part]
    return answer


def _tail(answer: object, commits: object, head: object) -> bool:
    """Compare's head side. A real answer always carries ``commits``: absent, null or not a list of SHAs fails.
    When the base is behind the head (``ahead``/``diverged``) the list must be non-empty, end on the head asked,
    and be whole: ``total_commits`` absent, null or not the list length (GitHub stops at 250) cannot confirm it."""
    if not isinstance(commits, list) or not all(isinstance(c, dict) and sha(c.get("sha")) for c in commits):
        return False
    if not (isinstance(answer, dict) and answer.get("status") in ("ahead", "diverged")):
        return True  # behind or identical: the base already holds the head; an empty list is right
    total = answer.get("total_commits")  # always in a real answer; absent or null cannot show the list is whole
    return bool(commits) and count(total) and total == len(commits) and sha(commits[-1]["sha"]) == sha(head)


_KINDS = {
    "sha": lambda answer, value, want: sha(value) is not None and sha(value) == sha(want),
    "int": lambda answer, value, want: positive_int(value) and value == want,
    "repo": lambda answer, value, want: text(value) and isinstance(want, str) and value.lower() == want.lower(),
    "suffix": lambda answer, value, want: text(value) and isinstance(want, str) and bool(want)
    and value.lower().endswith(want.lower()),
    "text": lambda answer, value, want: text(value) and value == want,
    "tail": _tail,
}


def identity_mismatch(row: str, answer: object, **asked: object) -> str | None:
    """Apply one IDENTITY row: its reason code when the answer does not name what was asked, else None."""
    spec = IDENTITY[row]
    for path, key, kind in spec["checks"]:
        if not _KINDS[kind](answer, _at(answer, path), asked[key]):
            return spec["code"]
    return None


# THE one list of what the mission query asks for on each issue: field name to its arguments and
# sub-selection. ``delivery_collect`` builds the query's node selection from it and ``_node_ok`` requires
# every one of these keys in every node, so a field cannot be requested without being required: an absent
# key is a cut answer, never "null".
ISSUE_FIELDS: dict[str, str] = {
    "id": "", "identifier": "", "startedAt": "", "completedAt": "", "createdAt": "", "description": "",
    "state": " { type }", "assignee": " { name }",
    "attachments": "(first: 100) { pageInfo { hasNextPage } nodes { url } }",
}


def _node_ok(node: object) -> bool:
    """The issue fields a consumer reads are in their domain; a null assignee means unowned. ``startedAt`` and
    ``completedAt`` are judged per mission by the classifier (spec row 1: bad timestamp is that mission's UNKNOWN)."""
    if not isinstance(node, dict) or not all(name in node for name in ISSUE_FIELDS):
        return False  # a field the query asked for is absent: a cut answer
    if not node_id(node["id"]) or not linear_identifier(node["identifier"]):
        return False
    state, assignee = node.get("state"), node.get("assignee")
    return isinstance(state, dict) and member(state.get("type"), LINEAR_STATE_TYPES) \
        and (assignee is None or (isinstance(assignee, dict) and text(assignee.get("name"))))  # User.name: String!


def _issue_page(data: object) -> tuple[list[dict], str | None] | None:
    """(nodes, next cursor or None), or None when the page or any node in it is malformed."""
    project = data.get("project") if isinstance(data, dict) else None
    conn = project.get("issues") if isinstance(project, dict) else None
    page = conn.get("pageInfo") if isinstance(conn, dict) else None
    nodes = conn.get("nodes") if isinstance(page, dict) else None
    if not isinstance(nodes, list) or not flag(page.get("hasNextPage")) or not all(_node_ok(n) for n in nodes):
        return None
    cursor = page.get("endCursor") if page["hasNextPage"] else None
    if page["hasNextPage"] and not text(cursor):
        return None
    return nodes, cursor
