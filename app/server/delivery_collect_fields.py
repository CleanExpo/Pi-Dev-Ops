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


def linear_links(issue: object) -> bool:
    """The link fields ``pr_refs`` reads: description text or null; each attachment url text or null.
    The attachment list's own wholeness (``hasNextPage``) stays with ``pr_refs``."""
    if not isinstance(issue, dict) or not maybe(issue.get("description"), lambda v: isinstance(v, str)):
        return False
    conn = issue.get("attachments")
    nodes = conn.get("nodes") if isinstance(conn, dict) else None
    if not isinstance(nodes, list):
        return True  # not whole: ``pr_refs`` returns None and the links are incomplete
    return all(not isinstance(n, dict) or maybe(n.get("url"), lambda v: isinstance(v, str)) for n in nodes)
