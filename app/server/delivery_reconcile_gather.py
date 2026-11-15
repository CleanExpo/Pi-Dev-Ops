"""RA-8100 delivery reconcile: the read-and-classify phase of one tick.

Read-only. Linear, GitHub and Vercel are reached only through the collector's functions,
links only through ``ticket_sweeper_io.pr_refs``. Records and findings are plain dicts for
``delivery_reconcile_store.apply_tick``; the summary carries identifiers, counts and reason
codes only. No issue description, attachment text or out-of-scope repo is ever recorded.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from . import delivery_collect as collect
from . import delivery_reconcile_links as links

logger = logging.getLogger("pi-ceo.delivery_reconcile")

LOOKBACK = timedelta(days=14)
_COUNTED = ("bot_prs", "closed_unmerged", "started_without_pr", "completed_without_pr")
_TOP = ("founder", "critical")


def new_summary(now: datetime) -> dict[str, Any]:
    """Every summary key, zeroed. The status tile reads these names."""
    return {"tick_at": now.astimezone(timezone.utc).isoformat(), "complete": False, "missions": 0,
            "by_severity": {}, "by_code": {}, "founder_or_critical": [], "skipped_repos": [],
            "unqueryable_projects": [], "refs_outside_scope": 0, "bot_prs": 0, "closed_unmerged": 0,
            "started_without_pr": 0, "completed_without_pr": 0, "not_refreshed": 0, "not_refreshed_ids": [],
            "vercel_unreadable": 0, "incomplete": {}, "budget_left": None}


@dataclass
class Run:
    """One tick's working set; ``links`` and the orphan pass share it."""

    state: dict[str, Any]
    registry: collect.Registry
    api_key: str
    now: datetime
    summary: dict[str, Any]
    tick: Any = None
    records: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    sweep: dict[str, dict[int, dict]] = field(default_factory=dict)
    linked: set[tuple[str, int]] = field(default_factory=set)
    linear_whole: bool = True
    sweep_whole: bool = True
    links_whole: bool = True
    own: str | None = None

    def stored(self, rid: str) -> dict | None:
        rec = self.state.get("missions", {}).get(rid)
        return rec if isinstance(rec, dict) else None

    def take(self, record: dict, found: list[dict]) -> None:
        """Tally a counted row, or keep a freshly classified record and its findings."""
        counted = record.get("counted")
        if counted:
            if counted in _COUNTED:
                self.summary[counted] += 1
            return
        record["refreshed_at"] = self.now.timestamp()
        self.records.append(record)
        self.findings.extend(found)

    def keep_stored(self, rid: str) -> None:
        """A mission not read this tick: its stored record is re-emitted unchanged."""
        self.summary["not_refreshed"] += 1
        old = self.stored(rid)
        if old is not None:
            self.records.append(old)
            self.summary["not_refreshed_ids"].append(rid)


def _read_missions(run: Run) -> list[tuple[dict, dict]]:
    """Every queryable entry's missions; a read that is not whole makes the tick incomplete."""
    since = (run.now - LOOKBACK).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    out: list[tuple[dict, dict]] = []
    seen: set[str] = set()
    for entry in run.registry.queryable:
        try:
            read = collect.fetch_missions(run.api_key, entry, tick=run.tick, since=since)
            issues, whole, reason = read.issues, read.complete, read.reason
        except collect.Unknown as exc:
            issues, whole, reason = [], False, exc.reason
        except Exception as exc:  # noqa: BLE001 — recorded by type name only
            issues, whole, reason = [], False, f"error_{type(exc).__name__}"
        if not whole:
            run.linear_whole = False
            run.summary["incomplete"][entry["id"]] = reason or "incomplete"
        for issue in issues:
            ident = issue.get("identifier") if isinstance(issue, dict) else None
            if isinstance(ident, str) and ident not in seen:
                seen.add(ident)
                out.append((entry, issue))
    return out


def _sweep(run: Run) -> None:
    """Every swept repo's open PRs; any failure makes the tick incomplete."""
    for repo in run.registry.swept:
        try:
            items = links.open_prs(repo, run.tick)
        except collect.Unknown as exc:
            run.sweep_whole = False
            run.summary["incomplete"][repo] = exc.reason
            continue
        run.sweep[repo.lower()] = {i["number"]: {**i, "repo": repo} for i in items
                                   if isinstance(i.get("number"), int) and not isinstance(i["number"], bool)}


def _oldest_first(run: Run, missions: list[tuple[dict, dict]]) -> list[tuple[dict, dict]]:
    """Missions never refreshed first, then by the stored record's ``refreshed_at``."""
    def when(pair: tuple[dict, dict]) -> tuple[int, float]:
        old = run.stored(str(pair[1]["identifier"])) or {}
        stamp = old.get("refreshed_at")
        ok = isinstance(stamp, (int, float)) and not isinstance(stamp, bool)
        return (1, float(stamp)) if ok else (0, 0.0)

    return sorted(missions, key=when)


def _tally(run: Run) -> None:
    by_sev: dict[str, int] = {}
    by_code: dict[str, int] = {}
    top: list[str] = []
    for fnd in run.findings:
        sev, code = str(fnd.get("severity")), str(fnd.get("code"))
        by_sev[sev] = by_sev.get(sev, 0) + 1
        by_code[code] = by_code.get(code, 0) + 1
        if sev in _TOP and fnd.get("ref") not in top:
            top.append(fnd.get("ref"))
    run.summary.update({"by_severity": by_sev, "by_code": by_code, "founder_or_critical": top,
                        "budget_left": dict(getattr(run.tick, "left", {}) or {})})


def gather(state: dict[str, Any], registry: collect.Registry, api_key: str, now: datetime,
           summary: dict[str, Any]) -> tuple[list[dict], list[dict], bool]:
    """Read and classify one tick. Returns (records, findings, complete); fills ``summary``."""
    run = Run(state, registry, api_key, now, summary, tick=collect.Tick(allowed=registry.allowed),
              own=collect.own_revision())
    missions = _read_missions(run)
    summary["missions"] = len(missions)
    _sweep(run)
    for entry, issue in _oldest_first(run, missions):
        links.mission(run, entry, issue)
    links.orphans(run)
    links.repos(run)
    _tally(run)
    return run.records, run.findings, run.linear_whole and run.sweep_whole
