"""RA-8100 delivery reconcile: per-mission links and evidence, orphan PRs, per-repo findings.

Read-only. GitHub and Vercel only through the collector; a link outside the registry is
counted and dropped before any GitHub call, and its repo and number are never recorded.
A subject (mission, orphan PR or repo) whose own reads all arrived whole is proven through ``Run.prove``
(the only way its alerts can retire); one that did not is reported through ``Run.hold``.
"""
from __future__ import annotations

from typing import Any

from . import delivery_collect as collect
from . import delivery_collect_github as collect_github
from . import delivery_stage, ticket_sweeper_io
from .delivery_collect_fields import linear_links
from .delivery_stage_facts import read_whole

_NO_LIVE: dict[str, Any] = {"revision": None, "compare": {}}


def open_prs(repo: str, tick: Any) -> list[dict]:
    """The open-PR sweep for one repo (raises the collector's ``Unknown``)."""
    return collect_github.open_prs(repo, tick=tick)


def _evidence(run: Any, repo: str, number: int) -> dict:
    """One linked PR's facts, or an error item. ``BudgetExhausted`` propagates."""
    try:
        return collect_github.pr_evidence(repo, number, tick=run.tick)
    except collect.BudgetExhausted:
        raise
    except collect.MissingCommit as exc:
        kind, reason = "missing_commit", exc.reason
    except collect.Unknown as exc:
        kind, reason = "unknown", exc.reason
    return _error_item(run, repo, number, kind, reason)


def _error_item(run: Any, repo: str, number: int, kind: str, reason: str) -> dict:
    """The one shape of a linked PR whose read failed; the classifier turns it into UNKNOWN or MISSING_COMMIT."""
    swept = run.sweep.get(repo.lower(), {}).get(number) or {}
    return {"repo": repo, "number": number, "error": kind, "reason": reason,
            "created_at": swept.get("created_at")}


def _live(run: Any, entry: dict, prs: list[dict] | None) -> dict[str, Any]:
    """Own-revision compare for each merged PR that is itself in the provable repo; Unknown is None.
    A PR in another repo is never compared: the own revision says nothing about that repo."""
    compare: dict[str, str | None] = {}
    failed: dict[str, str] = {}
    if run.own and prs and delivery_stage.live_kind(entry["repo"]) == "provable":
        for item in prs:
            own_repo = delivery_stage.live_kind(str(item.get("repo"))) == "provable"
            sha = item.get("merge_sha") if item.get("state") == "merged" and own_repo else None
            if not isinstance(sha, str) or sha in compare:
                continue
            try:
                compare[sha] = collect_github.compare_status(item["repo"], sha, run.own, tick=run.tick)
            except collect.BudgetExhausted:
                raise
            except collect.Unknown as exc:
                compare[sha] = None
                failed[sha] = exc.reason
    return {"revision": run.own, "compare": compare, "failed": failed}


def _compare_failed(run: Any, prs: list[dict] | None, live: dict[str, Any]) -> list[dict] | None:
    """A merged PR whose compare read failed is an error item: the mission's read was not whole (row 1)."""
    failed = live.get("failed") or {}
    if not failed or prs is None:
        return prs
    return [_error_item(run, p["repo"], p["number"], "unknown", f"compare_{failed[p['merge_sha']]}")
            if p.get("merge_sha") in failed else p for p in prs]


def _refs(run: Any, issue: dict) -> list[tuple[str, int]] | None:
    """The mission's in-scope PR links; None when its link list did not arrive whole."""
    try:
        if not linear_links(issue):  # the link fields' domain, checked before ``pr_refs`` reads them
            raise collect.Unknown("malformed_links")
        refs = ticket_sweeper_io.pr_refs(issue)
        kept, dropped = collect.in_scope(refs, run.registry.allowed) if refs is not None else ([], 0)
    except (collect.Unknown, TypeError, AttributeError):  # a link field that is not text, or a bad ref
        refs = None
    if refs is None:
        run.cut("links", str(issue.get("identifier")), "links_incomplete")  # D48: the tick is incomplete
        return None
    run.summary["refs_outside_scope"] += dropped
    run.linked.update((repo.lower(), n) for repo, n in kept)
    return kept


def _read_whole(input_ok: bool, prs: list[dict] | None, live: dict[str, Any]) -> bool:
    """THE hold fact, fail closed: the classifier accepted its input (``delivery_stage.judge``), the link
    list arrived whole, every pull read succeeded (``read_whole``) and every compare answered."""
    return input_ok and prs is not None and all(read_whole(p) for p in prs) \
        and None not in live["compare"].values()


def mission(run: Any, entry: dict, issue: dict) -> None:
    """Classify one mission. A mission not read whole is held, and so is any stored orphan it links.
    Cut by the budget, or by the clock before its first read: never read, so its stored record stays
    (spec line 112). Any other failed or cut read: UNKNOWN with that reason (spec row 1)."""
    rid = str(issue.get("identifier"))
    refs = _refs(run, issue)
    left = dict(getattr(run.tick, "left", {}) or {})
    try:
        prs = None if refs is None else [_evidence(run, repo, n) for repo, n in refs]
        live = _live(run, entry, prs)
    except collect.BudgetExhausted as exc:
        if exc.reason != "clock" or dict(getattr(run.tick, "left", {}) or {}) == left:
            run.keep_stored(rid)
            run.claim(refs)
            return
        prs, live = [_error_item(run, repo, n, "unknown", "clock") for repo, n in refs or []], dict(_NO_LIVE)
    prs = _compare_failed(run, prs, live)
    old = run.stored(rid) or {}
    record, found, input_ok = delivery_stage.judge(issue, prs, live, run.now, repo=entry["repo"],
                                                   project_id=entry["id"], first_seen=old.get("first_seen"))
    run.take(record, found)
    if _read_whole(input_ok, prs, live):
        run.prove(rid)
    else:
        run.hold(rid)
        run.claim(refs)


def _hold_orphans(run: Any) -> bool:
    """Hold each stored orphan whose subject is not read whole: all of them when a Linear read or link
    list was not whole (any mission may link any PR), else those a not-whole mission links and those
    whose repo's open pulls were not listed whole this tick. A registry repo nobody swept (its sweep
    failed, or its project cannot be queried) was never read, so its orphans cannot be shown out of
    scope (``Run.unknown``): the same rule as a mission whose project was not read. Only a repo that
    left the registry (a local file, read whole) puts its orphans out of scope.
    Returns whether new orphans can be judged this tick."""
    trusted = run.uncut("linear", "links")
    known = {entry["repo"].lower() for entry in run.registry.entries}
    for rid, rec in run.state["missions"].items():
        repo = rid.lower().removeprefix("pr:").rpartition("#")[0]  # the id is ``pr:<repo>#<number>``
        if not (isinstance(rec, dict) and rec.get("kind") == "orphan_pr" and repo in known):
            continue
        listed = repo in run.sweep
        if not listed:
            run.unknown.add(rid)
        if not (trusted and listed) or rid.lower() in run.claimed:
            run.hold(rid)
    return trusted


def orphans(run: Any) -> None:
    """Open PRs no mission links, judged only when every Linear read and link list was whole."""
    if not _hold_orphans(run):
        return
    for repo_key, items in run.sweep.items():
        for number, item in items.items():
            if (repo_key, number) in run.linked:
                continue
            repo = item["repo"]
            old = run.stored(f"pr:{repo}#{number}") or {}
            record, found = delivery_stage.classify(None, [item], _NO_LIVE, run.now, repo=repo, project_id="",
                                                    first_seen=old.get("first_seen"))
            run.take(record, found)
            run.prove(f"pr:{repo}#{number}")  # its repo's sweep and every link list were read whole


def _vercel_sha(run: Any, repo: str) -> tuple[str | None, bool]:
    """(sha, read whole). No Vercel project to read is whole; a failed read is not."""
    entry = next((e for e in run.registry.entries
                  if e["repo"].lower() == repo.lower() and e.get("vercel_project_id")), None)
    if entry is None:
        return None, True
    try:
        return collect.vercel_latest_ready(entry, tick=run.tick), True
    except collect.Unknown:
        run.summary["vercel_unreadable"] += 1
        run.hold(f"repo:{repo}")  # the repo's stored live-unconfirmed record and alert stay
        return None, False


def _inputs_whole(run: Any, repo: str, missions: list[tuple[dict, dict]]) -> bool:
    """A repo's record is DERIVED from its missions' records, so its inputs are an ALLOW-list: every
    registry entry of the repo had its mission list read whole this tick (``Run.projects``; an entry that
    cannot be queried is never in it), and every mission of the repo, listed this tick or stored and not
    read, was proven whole (``Run.prove``). Nothing is worked out from a project or mission nobody read."""
    key = repo.lower()
    entries = all(entry["id"] in run.projects for entry in run.registry.entries if entry["repo"].lower() == key)
    listed = all(str(issue["identifier"]) in run.whole for entry, issue in missions if entry["repo"].lower() == key)
    unread = any(str((run.stored(rid) or {}).get("repo")).lower() == key for rid in run.unknown)
    return entries and listed and not unread


def repos(run: Any, missions: list[tuple[dict, dict]]) -> None:
    """One record and its info finding per in-scope repo (rule 8), emitted and proven only when every
    input it is derived from was read whole this tick; otherwise the repo is held (``Run.hold``) and its
    stored record and alert stay exactly as they were."""
    done: set[str] = set()
    for entry in run.registry.entries:
        repo = entry["repo"]
        if repo.lower() in done:
            continue
        done.add(repo.lower())
        if not _inputs_whole(run, repo, missions):
            run.hold(f"repo:{repo}")
            continue
        merged = sum(1 for r in run.records if r.get("kind") == "mission" and r.get("stage") == "merged"
                     and str(r.get("repo", "")).lower() == repo.lower() and r.get("live_source_provable") is False)
        sha, whole = _vercel_sha(run, repo) if delivery_stage.live_kind(repo) == "live_unconfirmed" else (None, True)
        if not whole:
            continue  # ``_vercel_sha`` held it: nothing is written over the stored record
        record, found = delivery_stage.repo_findings(repo, merged, sha)
        run.records.append(record)
        run.findings.extend(found)
        run.prove(record["id"])
