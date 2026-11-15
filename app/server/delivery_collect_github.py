"""RA-8100 read-only GitHub readers for the delivery collector (split from delivery_collect).

GitHub only through ``ticket_sweeper_io.github_get``; every read is counted on the ``Tick`` and
refused for out-of-scope or skipped repos before any request. One-way import: this module
imports from ``delivery_collect``; ``delivery_collect`` never imports this module.
"""
from __future__ import annotations

from . import ticket_sweeper_io
from .delivery_collect import _REPO, MissingCommit, Tick, Unknown, _skipped
from .delivery_collect_fields import (
    CHECK_CONCLUSIONS, CHECK_STATUSES, COMPARE_STATUSES, PULL_STATES, REVIEW_STATES, STATUS_STATES, USER_TYPES,
    count, flag, is_instant, login, maybe, member, no_commit, positive_int, sha,
)


def _get(repo: str, path: str, tick: Tick, *, missing_on_404: bool = False,
         not_found: str = "head_not_found") -> object:
    """One counted GitHub GET for an in-scope repo; errors become reason codes."""
    if not _REPO.fullmatch(repo) or _skipped(repo) or repo.lower() not in tick.allowed:
        raise Unknown("out_of_scope")
    tick.spend("github")
    try:
        return ticket_sweeper_io.github_get(f"/repos/{repo}{path}")
    except Exception as exc:  # noqa: BLE001 — recorded by type name only
        code = getattr(exc, "code", None)
        if missing_on_404 and code == 404:
            raise MissingCommit(not_found) from None
        raise Unknown(f"http_{code}" if isinstance(code, int) else f"error_{type(exc).__name__}") from None


def _page(data: object, key: str | None, identity: str, item: str) -> tuple[list[dict], object]:
    """One page's items and ``total_count``; every item must carry a valid identity."""
    batch = data.get(key) if key and isinstance(data, dict) else data
    total = data.get("total_count") if key and isinstance(data, dict) else None
    if not isinstance(batch, list) or not all(isinstance(b, dict) for b in batch) \
            or (key and not count(total)):
        raise Unknown("malformed_list")
    if not all(positive_int(b.get(identity)) for b in batch):
        raise Unknown(f"malformed_{item}")
    return batch, total


# The one owner of "this paged list is whole": identity, duplicates and the count are checked here
# for every list, so no caller can get a list without them. ``identity`` has no default on purpose.
def _paged(repo: str, path: str, tick: Tick, *, identity: str, item: str, key: str | None = None) -> list[dict]:
    """Every page of a GitHub list, whole or raise. Ends on a short page; a counted list must then
    hold exactly ``total_count`` distinct items, the same total on every page."""
    items: list[dict] = []
    seen: set[int] = set()
    first: object = None
    for page in range(1, 11):
        batch, total = _page(_get(repo, f"{path}per_page=100&page={page}", tick), key, identity, item)
        if page > 1 and total != first:
            raise Unknown("total_changed")  # the list moved between pages
        first = total
        ids = [b[identity] for b in batch]
        if len(set(ids)) < len(ids) or seen.intersection(ids):
            raise Unknown(f"duplicate_{item}")  # a shifted page may have skipped one
        seen.update(ids)
        items.extend(batch)
        if len(batch) < 100:
            if key and len(seen) != total:
                raise Unknown("list_short" if len(seen) < total else "list_over")
            return items
    raise Unknown("list_too_long")


# The one owner of "this is a commit SHA" for every GitHub path (list and single item alike).
def _sha(value: object, missing: str) -> str:
    """Absent, null or empty: ``MissingCommit(missing)`` (spec row 4). Present but not 40-hex: Unknown."""
    if no_commit(value):
        raise MissingCommit(missing)
    checked = sha(value)
    if checked is None:
        raise Unknown("malformed_sha")
    return checked


def _head(pr: dict) -> str | None:
    """The head SHA, or None when the pull names no head commit (the consumer reports MISSING_COMMIT)."""
    head = pr.get("head")
    if not isinstance(head, (dict, type(None))):
        raise Unknown("malformed_pull")
    value = head.get("sha") if isinstance(head, dict) else None
    return None if no_commit(value) else _sha(value, "empty_head")


# One owner for the item rule: every item of every GitHub list is checked here, and one malformed
# item fails the whole read with a reason code. Callers never filter; they use what is returned.
def _author(item: dict, code: str) -> tuple[str | None, str | None]:
    user = item.get("user")
    if user is None:
        return None, None  # no author: never a bot, so never counted away
    if not isinstance(user, dict) or not login(user.get("login")) or not member(user.get("type"), USER_TYPES):
        raise Unknown(code)
    return user["login"], user["type"]


def _pull_common(pr: dict) -> dict:
    """The fields every pull read relies on, checked; raises ``malformed_pull`` or ``malformed_sha``."""
    if not flag(pr.get("draft")) or not is_instant(pr.get("created_at")):
        raise Unknown("malformed_pull")
    login_, kind = _author(pr, "malformed_pull")
    return {"draft": pr["draft"], "created_at": pr["created_at"], "author_login": login_, "author_type": kind,
            "head_sha": _head(pr)}


def open_prs(repo: str, *, tick: Tick) -> list[dict]:
    """Every open PR in a swept repo, as minimal facts (no titles or bodies). Whole or raise."""
    return [{"number": pr["number"], **_pull_common(pr)}
            for pr in _paged(repo, "/pulls?state=open&", tick, identity="number", item="pull")]


def _pull_facts(pr: object, number: int) -> dict:
    if not isinstance(pr, dict) or not member(pr.get("state"), PULL_STATES) or not flag(pr.get("merged")) \
            or not maybe(pr.get("merged_at"), is_instant):
        raise Unknown("malformed_pull")
    if pr["merged"] and (pr["state"] != "closed" or pr.get("merged_at") is None):
        raise Unknown("malformed_pull")  # a merge with no time, or an open merged pull, is not a merge read
    if not positive_int(pr.get("number")) or pr["number"] != number:
        raise Unknown("pull_mismatch")  # an answer about another pull is not this pull's evidence
    return {**_pull_common(pr), "state": "merged" if pr["merged"] else pr["state"],
            "merged_at": pr.get("merged_at"), "merge_sha": pr.get("merge_commit_sha") if pr["merged"] else None}


def _check_run(run: dict) -> dict:
    if not member(run.get("status"), CHECK_STATUSES) or not maybe(run.get("conclusion"),
                                                                    lambda v: member(v, CHECK_CONCLUSIONS)) \
            or not maybe(run.get("completed_at"), is_instant):
        raise Unknown("malformed_check_run")
    return {"status": run["status"], "conclusion": run.get("conclusion"), "completed_at": run.get("completed_at")}


def _review(review: dict) -> dict:
    """A review must name its login: a nameless verdict could hide another reviewer's block."""
    name = _author(review, "malformed_review")[0]
    state, when = review.get("state"), review.get("submitted_at")
    if not name or not member(state, REVIEW_STATES) or not maybe(review.get("commit_id"), sha) \
            or not (is_instant(when) or (when is None and state == "PENDING")):
        raise Unknown("malformed_review")
    return {"login": name, "state": state, "commit_id": sha(review.get("commit_id")),
            "submitted_at": review.get("submitted_at")}


def _commit(repo: str, commit: str, tick: Tick, not_found: str) -> None:
    """The commit exists and the answer names it; any other answer is not proof it exists."""
    data = _get(repo, f"/commits/{commit}", tick, missing_on_404=True, not_found=not_found)
    named = data.get("sha") if isinstance(data, dict) else None
    if sha(named) != commit:
        raise Unknown("commit_mismatch")


def _status(data: object) -> dict:
    """Combined status: only ``state`` and ``total_count`` are used, never the paged ``statuses``."""
    if not isinstance(data, dict) or not member(data.get("state"), STATUS_STATES) or not count(data.get("total_count")):
        raise Unknown("malformed_status")
    return {"state": data["state"], "total_count": data["total_count"]}


def pr_evidence(repo: str, n: int, *, tick: Tick) -> dict:
    """One PR's head, merge, checks, status and reviews; raises Unknown or MissingCommit."""
    number = int(n)
    facts = {**_pull_facts(_get(repo, f"/pulls/{number}", tick), number), "repo": repo, "number": number}
    if facts["state"] == "merged":
        facts["merge_sha"] = _sha(facts["merge_sha"], "no_merge_sha")
        _commit(repo, facts["merge_sha"], tick, "merge_not_found")
    if facts["state"] != "open":  # merged read its merge commit above; closed-unmerged has no deciding commit
        return facts
    head = facts["head_sha"] = _sha(facts["head_sha"], "empty_head")
    _commit(repo, head, tick, "head_not_found")
    facts["check_runs"] = [_check_run(r) for r in _paged(repo, f"/commits/{head}/check-runs?", tick, identity="id",
                                                         item="check_run", key="check_runs")]
    facts["status"] = _status(_get(repo, f"/commits/{head}/status", tick))
    facts["reviews"] = [_review(r) for r in _paged(repo, f"/pulls/{number}/reviews?", tick, identity="id",
                                                   item="review")]
    return facts


def compare_status(repo: str, base: str, head: str, *, tick: Tick) -> str:
    """GitHub compare ``base...head`` status; the stage decides what counts as contained."""
    data = _get(repo, f"/compare/{_sha(base, 'no_base')}...{_sha(head, 'no_head')}", tick)
    status = data.get("status") if isinstance(data, dict) else None
    if not member(status, COMPARE_STATUSES):
        raise Unknown("malformed_compare")
    return status
