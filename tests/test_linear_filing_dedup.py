"""tests/test_linear_filing_dedup.py — 2026-06-10 dupe-storm regression coverage.

Three fixes, three failure modes that filled the RA backlog with duplicates:

  * scout.py `_existing_scout_titles` declared `$projectId: String!` where
    Linear's IDComparator expects `ID` — every dedup query 400'd, the
    exception was swallowed into an empty set, and scout filed blind on every
    cycle (RA-5663/5664/5665 each got up to 6 copies). Fixed: `ID!` + the
    fetch now fails CLOSED (returns None → cycle skips creation).
  * production_coordinator `_file_linear_ticket` had no dedup at all — every
    still-failed asset was re-filed on each daily run (RA-5649 got 4 copies).
    Fixed: `find_open_issue_by_title` guard before `propose_idea`.
  * margot_tools gained `find_open_issue_by_title` — exact-title, open-states
    lookup shared by automated filers.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server.agents import scout  # noqa: E402
from swarm import margot_tools, production_coordinator  # noqa: E402


# ── margot_tools.find_open_issue_by_title ─────────────────────────────────────

def test_find_open_issue_returns_identifier(monkeypatch):
    captured: dict = {}

    def fake_gql(query, variables=None, **kw):
        captured["query"] = query
        captured["variables"] = variables
        return {"data": {"issues": {"nodes": [{"identifier": "RA-5649"}]}}}

    monkeypatch.setattr(margot_tools, "_resolve_team_id", lambda team: "team-uuid")
    monkeypatch.setattr(margot_tools, "_linear_gql", fake_gql)

    assert margot_tools.find_open_issue_by_title("[Production] synthex — product demo 60s") == "RA-5649"
    # ID! is load-bearing: String! fails Linear's IDComparator validation.
    assert "$teamId: ID!" in captured["query"]
    assert captured["variables"]["title"] == "[Production] synthex — product demo 60s"
    # Done/Canceled must NOT block a re-file — only open state types count.
    for state_type in ("triage", "backlog", "unstarted", "started"):
        assert state_type in captured["query"]
    assert "completed" not in captured["query"]
    assert "canceled" not in captured["query"]


def test_find_open_issue_none_when_no_match(monkeypatch):
    monkeypatch.setattr(margot_tools, "_resolve_team_id", lambda team: "team-uuid")
    monkeypatch.setattr(margot_tools, "_linear_gql",
                        lambda q, v=None, **kw: {"data": {"issues": {"nodes": []}}})
    assert margot_tools.find_open_issue_by_title("anything") is None


def test_find_open_issue_fail_open_on_error(monkeypatch):
    monkeypatch.setattr(margot_tools, "_resolve_team_id", lambda team: "team-uuid")
    monkeypatch.setattr(margot_tools, "_linear_gql",
                        lambda q, v=None, **kw: {"error": "request_failed"})
    assert margot_tools.find_open_issue_by_title("anything") is None


# ── production_coordinator._file_linear_ticket dedup ──────────────────────────

def _job() -> production_coordinator.ProductionJob:
    return production_coordinator.ProductionJob(
        business_id="synthex",
        content_type="videos",
        asset_id="product_demo_60s",
        skill="remotion-orchestrator",
        brief="brief",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def test_file_ticket_skips_when_open_ticket_exists(monkeypatch):
    monkeypatch.setattr(margot_tools, "find_open_issue_by_title", lambda title, **kw: "RA-5649")

    def explode(**kw):  # pragma: no cover - the assertion IS the call
        raise AssertionError("propose_idea must not be called when an open ticket exists")

    monkeypatch.setattr(margot_tools, "propose_idea", explode)
    assert production_coordinator._file_linear_ticket(_job()) == "RA-5649"


def test_file_ticket_files_when_no_open_ticket(monkeypatch):
    monkeypatch.setattr(margot_tools, "find_open_issue_by_title", lambda title, **kw: None)
    seen: dict = {}

    def fake_propose(title, description="", **kw):
        seen["title"] = title
        return {"status": "created", "identifier": "RA-9999"}

    monkeypatch.setattr(margot_tools, "propose_idea", fake_propose)
    assert production_coordinator._file_linear_ticket(_job()) == "RA-9999"
    assert seen["title"] == "[Production] synthex — product demo 60s"


# ── scout fail-closed dedup ───────────────────────────────────────────────────

def test_scout_query_uses_id_type():
    import inspect
    src = inspect.getsource(scout._existing_scout_titles)
    assert "$projectId: ID!" in src
    assert "$projectId: String!" not in src


def test_scout_titles_none_on_fetch_failure(monkeypatch):
    def boom(*a, **kw):
        raise OSError("HTTP Error 400: Bad Request")

    monkeypatch.setattr(scout.urllib.request, "urlopen", boom)
    assert scout._existing_scout_titles("lin_api_test") is None


def test_scout_cycle_fails_closed_when_dedup_unavailable(monkeypatch):
    finding = {
        "source": "github",
        "title": "some repo",
        "description": "desc",
        "url": "https://example.com/x",
    }
    monkeypatch.setattr(scout, "fetch_github_findings", lambda: [dict(finding)])
    monkeypatch.setattr(scout, "fetch_arxiv_findings", lambda: [])
    monkeypatch.setattr(scout, "fetch_hn_findings", lambda: [])
    monkeypatch.setattr(scout, "_load_seen", lambda: {})
    monkeypatch.setattr(scout, "_save_seen", lambda seen: None)
    monkeypatch.setattr(scout, "_score_finding", lambda t, d: (5, ["dim"]))
    monkeypatch.setattr(scout, "_get_or_create_scout_label", lambda key: None)
    monkeypatch.setattr(scout, "_existing_scout_titles", lambda key: None)

    def explode(*a, **kw):  # pragma: no cover - the assertion IS the call
        raise AssertionError("must not create issues when dedup is unavailable")

    monkeypatch.setattr(scout, "_create_linear_issue", explode)
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")

    result = scout.run_scout_cycle(dry_run=False)
    assert result["issues_created"] == []


def test_scout_cycle_still_files_when_dedup_healthy(monkeypatch):
    finding = {
        "source": "github",
        "title": "fresh repo",
        "description": "desc",
        "url": "https://example.com/y",
    }
    monkeypatch.setattr(scout, "fetch_github_findings", lambda: [dict(finding)])
    monkeypatch.setattr(scout, "fetch_arxiv_findings", lambda: [])
    monkeypatch.setattr(scout, "fetch_hn_findings", lambda: [])
    monkeypatch.setattr(scout, "_load_seen", lambda: {})
    monkeypatch.setattr(scout, "_save_seen", lambda seen: None)
    monkeypatch.setattr(scout, "_score_finding", lambda t, d: (5, ["dim"]))
    monkeypatch.setattr(scout, "_get_or_create_scout_label", lambda key: None)
    monkeypatch.setattr(scout, "_existing_scout_titles", lambda key: set())
    monkeypatch.setattr(scout, "_create_linear_issue", lambda f, lbl, key: "RA-7777")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")

    result = scout.run_scout_cycle(dry_run=False)
    assert result["issues_created"] == ["RA-7777"]
