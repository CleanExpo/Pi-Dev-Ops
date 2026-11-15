"""RA-8100 delivery reconcile: per-mission links and evidence, orphan PRs, per-repo findings.

Read-only. GitHub and Vercel only through the collector; a link outside the registry is
counted and dropped before any GitHub call, and its repo and number are never recorded.
A per-mission budget cut leaves that mission's stored record in place (``not_refreshed``).
"""
from __future__ import annotations

from typing import Any

from . import delivery_collect as collect
from . import delivery_collect_github as collect_github
from . import delivery_stage, ticket_sweeper_io

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
    swept = run.sweep.get(repo.lower(), {}).get(number) or {}
    return {"repo": repo, "number": number, "error": kind, "reason": reason,
            "created_at": swept.get("created_at")}


def _live(run: Any, entry: dict, prs: list[dict] | None) -> dict[str, Any]:
    """Own-revision compare for each merged PR of a mission in a provable repo; Unknown is None."""
    compare: dict[str, str | None] = {}
    if run.own and prs and delivery_stage.live_kind(entry["repo"]) == "provable":
        for item in prs:
            sha = item.get("merge_sha") if item.get("state") == "merged" else None
            if not isinstance(sha, str) or sha in compare:
                continue
            try:
                compare[sha] = collect_github.compare_status(item["repo"], sha, run.own, tick=run.tick)
            except collect.BudgetExhausted:
                raise
            except collect.Unknown:
                compare[sha] = None
    return {"revision": run.own, "compare": compare}


def _linked_prs(run: Any, issue: dict) -> list[dict] | None:
    """The mission's in-scope PR evidence; None when its link list did not arrive whole."""
    refs = ticket_sweeper_io.pr_refs(issue)
    if refs is None:
        run.links_whole = False
        return None
    kept, dropped = collect.in_scope(refs, run.registry.allowed)
    run.summary["refs_outside_scope"] += dropped
    run.linked.update((repo.lower(), int(n)) for repo, n in kept)
    return [_evidence(run, repo, int(n)) for repo, n in kept]


def mission(run: Any, entry: dict, issue: dict) -> None:
    """Classify one mission, or keep its stored record when the budget cut its reads."""
    rid = str(issue.get("identifier"))
    try:
        prs = _linked_prs(run, issue)
        live = _live(run, entry, prs)
    except collect.BudgetExhausted:
        run.keep_stored(rid)
        return
    old = run.stored(rid) or {}
    record, found = delivery_stage.classify(issue, prs, live, run.now, repo=entry["repo"],
                                            project_id=entry["id"], first_seen=old.get("first_seen"))
    run.take(record, found)


def orphans(run: Any) -> None:
    """Open PRs no mission links. Only when every Linear read was whole; else keep stored ones."""
    if not (run.linear_whole and run.links_whole):
        for rec in run.state.get("missions", {}).values():
            if isinstance(rec, dict) and rec.get("kind") == "orphan_pr":
                run.records.append(rec)
                run.summary["not_refreshed_ids"].append(rec.get("id"))  # its alerts stay shown
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


def _vercel_sha(run: Any, repo: str) -> str | None:
    entry = next((e for e in run.registry.entries
                  if e["repo"].lower() == repo.lower() and e.get("vercel_project_id")), None)
    if entry is None:
        return None
    try:
        return collect.vercel_latest_ready(entry, tick=run.tick)
    except collect.Unknown:
        run.summary["vercel_unreadable"] += 1
        return None


def repos(run: Any) -> None:
    """One record and its info finding per in-scope repo (rule 8)."""
    done: set[str] = set()
    for entry in run.registry.entries:
        repo = entry["repo"]
        if repo.lower() in done:
            continue
        done.add(repo.lower())
        merged = sum(1 for r in run.records if r.get("kind") == "mission" and r.get("stage") == "merged"
                     and str(r.get("repo", "")).lower() == repo.lower() and r.get("live_source_provable") is False)
        record, found = delivery_stage.repo_findings(repo, merged, _vercel_sha(run, repo))
        run.records.append(record)
        run.findings.extend(found)
