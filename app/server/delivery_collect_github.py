"""RA-8100 read-only GitHub readers for the delivery collector (split from delivery_collect).

GitHub only through ``ticket_sweeper_io.github_get``; every read is counted on the ``Tick`` and
refused for out-of-scope or skipped repos before any request. One-way import: this module
imports from ``delivery_collect``; ``delivery_collect`` never imports this module.
"""
from __future__ import annotations

from . import ticket_sweeper_io
from .delivery_collect import _REPO, _SHA, MissingCommit, Tick, Unknown, _skipped


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


def _paged(repo: str, path: str, tick: Tick, key: str | None = None) -> list[dict]:
    """Every page of a GitHub list, whole or raise (same rule as ``_all_check_runs``)."""
    items: list[dict] = []
    for page in range(1, 11):
        data = _get(repo, f"{path}per_page=100&page={page}", tick)
        batch = data.get(key) if key and isinstance(data, dict) else data
        total = data.get("total_count") if key and isinstance(data, dict) else None
        if not isinstance(batch, list) or not all(isinstance(b, dict) for b in batch) \
                or (key and not isinstance(total, int)):
            raise Unknown("malformed_list")
        items.extend(batch)
        if (len(items) >= total or not batch) if key else len(batch) < 100:
            if key and len(items) < total:
                raise Unknown("list_short")
            return items
    raise Unknown("list_too_long")


def _sha(value: object, missing: str) -> str:
    if value in (None, ""):
        raise MissingCommit(missing)
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise Unknown("malformed_sha")
    return value.lower()


def _author(pr: dict) -> tuple[str | None, str | None]:
    user = pr.get("user") if isinstance(pr.get("user"), dict) else {}
    return user.get("login"), user.get("type")


def open_prs(repo: str, *, tick: Tick) -> list[dict]:
    """Every open PR in a swept repo, as minimal facts (no titles or bodies)."""
    out = []
    for pr in _paged(repo, "/pulls?state=open&", tick):
        login, kind = _author(pr)
        out.append({"number": pr.get("number"), "draft": pr.get("draft") is True,
                    "created_at": pr.get("created_at"), "author_login": login, "author_type": kind,
                    "head_sha": (pr.get("head") or {}).get("sha") or ""})
    return out


def _pull_facts(pr: object) -> dict:
    if not isinstance(pr, dict) or pr.get("state") not in ("open", "closed") \
            or not isinstance(pr.get("merged"), bool):
        raise Unknown("malformed_pull")
    state = "merged" if pr["merged"] else pr["state"]
    login, kind = _author(pr)
    return {"state": state, "draft": pr.get("draft") is True, "created_at": pr.get("created_at"),
            "merged_at": pr.get("merged_at"), "author_login": login, "author_type": kind,
            "head_sha": (pr.get("head") or {}).get("sha") or "",
            "merge_sha": pr.get("merge_commit_sha") if pr["merged"] else None}


def pr_evidence(repo: str, n: int, *, tick: Tick) -> dict:
    """One PR's head, merge, checks, status and reviews; raises Unknown or MissingCommit."""
    number = int(n)
    facts = {**_pull_facts(_get(repo, f"/pulls/{number}", tick)), "repo": repo, "number": number}
    if facts["state"] == "merged":
        facts["merge_sha"] = _sha(facts["merge_sha"], "no_merge_sha")
        _get(repo, f"/commits/{facts['merge_sha']}", tick, missing_on_404=True, not_found="merge_not_found")
    if facts["state"] != "open":  # merged read its merge commit above; closed-unmerged has no deciding commit
        return facts
    sha = facts["head_sha"] = _sha(facts["head_sha"], "empty_head")
    _get(repo, f"/commits/{sha}", tick, missing_on_404=True)
    facts["check_runs"] = [{"status": r.get("status"), "conclusion": r.get("conclusion"),
                            "completed_at": r.get("completed_at")}
                           for r in _paged(repo, f"/commits/{sha}/check-runs?", tick, "check_runs")]
    status = _get(repo, f"/commits/{sha}/status", tick)
    if not isinstance(status, dict) or not isinstance(status.get("state"), str) \
            or not isinstance(status.get("total_count"), int):
        raise Unknown("malformed_status")
    facts["status"] = {"state": status["state"], "total_count": status["total_count"]}
    facts["reviews"] = [{"login": _author(r)[0], "state": r.get("state"), "commit_id": r.get("commit_id"),
                         "submitted_at": r.get("submitted_at")}
                        for r in _paged(repo, f"/pulls/{number}/reviews?", tick)]
    return facts


def compare_status(repo: str, base: str, head: str, *, tick: Tick) -> str:
    """GitHub compare ``base...head`` status; the stage decides what counts as contained."""
    data = _get(repo, f"/compare/{_sha(base, 'no_base')}...{_sha(head, 'no_head')}", tick)
    status = data.get("status") if isinstance(data, dict) else None
    if status not in ("identical", "ahead", "behind", "diverged"):
        raise Unknown("malformed_compare")
    return status
