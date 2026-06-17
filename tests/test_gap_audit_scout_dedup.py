"""tests/test_gap_audit_scout_dedup.py — RA-6756 idempotency regression coverage.

Proves that repeated runs of gap_audit and scout:
  - Enrich existing canonical issues (comment + cleanup label) instead of creating
    duplicates when the category (GAP-AUDIT) or source URL (SCOUT) matches.
  - Respect completed/cancelled canonical issues — resolved work is not regenerated.
  - Route below-threshold scout findings to the research inbox, not Linear.
  - Are idempotent: a second run with identical findings produces zero new tickets.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server.agents import board_meeting as bm  # noqa: E402
from app.server.agents import scout  # noqa: E402


# ── GAP-AUDIT deduplication ───────────────────────────────────────────────────

_ITEM_MULTI_BRANCH = {
    "severity": "high",
    "category": "multi-branch reads",
    "claim": "spec claims GitHub reads branches",
    "reality": "no multi-branch loop found",
    "file": "dashboard/lib/github.ts",
    "recommendation": "Add branch comparison logic",
}

_ITEM_LINEAR_SYNC = {
    "severity": "high",
    "category": "Linear two-way sync",
    "claim": "spec claims Linear two-way sync",
    "reality": "no outbound Linear calls found",
    "file": "app/server/webhook.py",
    "recommendation": "Add issueUpdate calls",
}


def _stub_gap_audit_phase(monkeypatch, *, items: list[dict], canonical: dict):
    """Wire monkeypatches so run_gap_audit_phase exercises the dedup path."""
    # Skip spec.md read and claude calls — inject discrepancies directly
    monkeypatch.setattr(bm, "_extract_spec_claims", lambda text: ["✅ claim"])
    monkeypatch.setattr(bm, "_call_claude_for_discrepancies", lambda *a, **kw: items)
    monkeypatch.setattr(bm, "_fetch_gap_audit_canonical", lambda: canonical)

    def _fake_read(path):
        class _FakePath:
            def exists(self): return True
            def read_text(self, **kw): return "✅ spec content"
        return _FakePath()

    # Patch spec path existence
    monkeypatch.setattr(bm, "_HARNESS_ROOT", Path("/tmp/harness-test"))
    # Make board meetings dir writable for the JSON output
    import os, tempfile
    tmp = tempfile.mkdtemp()
    harness = Path(tmp) / ".harness"
    harness.mkdir()
    (harness / "board-meetings").mkdir()
    (harness / "spec.md").write_text("✅ some claim", encoding="utf-8")
    monkeypatch.setattr(bm, "_HARNESS_ROOT", harness)
    monkeypatch.setattr(bm, "_REPO_ROOT", Path(tmp))


def test_gap_audit_enriches_open_canonical(monkeypatch, tmp_path):
    """Second run comments on the existing open issue rather than creating a new one."""
    created_calls: list[str] = []
    comment_calls: list[tuple] = []
    label_calls: list[tuple] = []

    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")
    monkeypatch.setattr(bm, "_linear_create_issue", lambda t, d, p: created_calls.append(t) or "RA-FAIL")
    monkeypatch.setattr(bm, "_linear_comment", lambda iid, body: comment_calls.append((iid, body)) or True)
    monkeypatch.setattr(bm, "_linear_apply_label", lambda iid, lid: label_calls.append((iid, lid)) or True)
    monkeypatch.setattr(bm, "_get_or_create_label", lambda name: "label-uuid-cleanup")
    # Only return a finding for the "multi-branch reads" audit target
    monkeypatch.setattr(
        bm, "_call_claude_for_discrepancies",
        lambda sc, target, fc, **kw: [_ITEM_MULTI_BRANCH] if target["category"] == "multi-branch reads" else [],
    )
    monkeypatch.setattr(bm, "_fetch_gap_audit_canonical", lambda: {
        "multi-branch reads": {"id": "uuid-123", "identifier": "RA-100", "state_type": "started"},
    })
    monkeypatch.setattr(bm, "_extract_spec_claims", lambda text: ["✅ claim"])

    # Stand up a minimal harness tree
    harness = tmp_path / ".harness"
    harness.mkdir()
    (harness / "board-meetings").mkdir()
    (harness / "spec.md").write_text("✅ spec claim", encoding="utf-8")
    monkeypatch.setattr(bm, "_HARNESS_ROOT", harness)
    monkeypatch.setattr(bm, "_REPO_ROOT", tmp_path)

    result = bm.run_gap_audit_phase(dry_run=False)

    assert created_calls == [], "Must NOT create new ticket when canonical exists"
    assert len(comment_calls) == 1, "Must add exactly one comment to existing issue"
    assert comment_calls[0][0] == "uuid-123"
    assert "re-detected" in comment_calls[0][1].lower()
    assert len(label_calls) == 1, "Must apply cleanup label"
    assert label_calls[0] == ("uuid-123", "label-uuid-cleanup")
    assert result["summary"]["linear_tickets_created"] == []


def test_gap_audit_skips_completed_canonical(monkeypatch, tmp_path):
    """Completed/cancelled canonical issues are not re-filed."""
    created_calls: list[str] = []
    comment_calls: list = []

    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")
    monkeypatch.setattr(bm, "_linear_create_issue", lambda t, d, p: created_calls.append(t) or "RA-FAIL")
    monkeypatch.setattr(bm, "_linear_comment", lambda iid, body: comment_calls.append(iid) or True)
    monkeypatch.setattr(bm, "_get_or_create_label", lambda name: "label-uuid")
    monkeypatch.setattr(bm, "_linear_apply_label", lambda iid, lid: True)
    monkeypatch.setattr(
        bm, "_call_claude_for_discrepancies",
        lambda sc, target, fc, **kw: [_ITEM_MULTI_BRANCH] if target["category"] == "multi-branch reads" else [],
    )
    monkeypatch.setattr(bm, "_fetch_gap_audit_canonical", lambda: {
        "multi-branch reads": {"id": "uuid-done", "identifier": "RA-50", "state_type": "completed"},
    })
    monkeypatch.setattr(bm, "_extract_spec_claims", lambda text: ["✅ claim"])

    harness = tmp_path / ".harness"
    harness.mkdir()
    (harness / "board-meetings").mkdir()
    (harness / "spec.md").write_text("✅ content", encoding="utf-8")
    monkeypatch.setattr(bm, "_HARNESS_ROOT", harness)
    monkeypatch.setattr(bm, "_REPO_ROOT", tmp_path)

    result = bm.run_gap_audit_phase(dry_run=False)

    assert created_calls == [], "Must NOT re-create a completed canonical"
    assert comment_calls == [], "Must NOT comment on completed canonical"
    assert result["summary"]["linear_tickets_created"] == []


def test_gap_audit_creates_new_when_no_canonical(monkeypatch, tmp_path):
    """No canonical → creates a new ticket (existing behaviour preserved)."""
    created_calls: list[str] = []

    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")
    monkeypatch.setattr(bm, "_linear_create_issue", lambda t, d, p: created_calls.append(t) or "RA-900")
    monkeypatch.setattr(bm, "_get_or_create_label", lambda name: "label-uuid")
    monkeypatch.setattr(bm, "_linear_apply_label", lambda iid, lid: True)
    monkeypatch.setattr(
        bm, "_call_claude_for_discrepancies",
        lambda sc, target, fc, **kw: [_ITEM_MULTI_BRANCH] if target["category"] == "multi-branch reads" else [],
    )
    monkeypatch.setattr(bm, "_fetch_gap_audit_canonical", lambda: {})  # empty map
    monkeypatch.setattr(bm, "_extract_spec_claims", lambda text: ["✅ claim"])

    harness = tmp_path / ".harness"
    harness.mkdir()
    (harness / "board-meetings").mkdir()
    (harness / "spec.md").write_text("✅ content", encoding="utf-8")
    monkeypatch.setattr(bm, "_HARNESS_ROOT", harness)
    monkeypatch.setattr(bm, "_REPO_ROOT", tmp_path)

    result = bm.run_gap_audit_phase(dry_run=False)

    assert len(created_calls) == 1, "Must create a ticket when no canonical exists"
    assert "[GAP-AUDIT]" in created_calls[0]
    assert result["summary"]["linear_tickets_created"] == ["RA-900"]


def test_gap_audit_idempotent_two_runs(monkeypatch, tmp_path):
    """Simulates two consecutive runs: first creates, second enriches — zero new tickets."""
    canonical_store: dict[str, Any] = {}

    def fake_create(title, description, priority):
        cat_match = title.split("] ", 1)[-1].split(":")[0].strip().lower()
        canonical_store[cat_match] = {"id": "uuid-new", "identifier": "RA-200", "state_type": "unstarted"}
        return "RA-200"

    comment_calls: list = []
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")
    monkeypatch.setattr(bm, "_linear_create_issue", fake_create)
    monkeypatch.setattr(bm, "_linear_comment", lambda iid, body: comment_calls.append(iid) or True)
    monkeypatch.setattr(bm, "_get_or_create_label", lambda name: "lbl")
    monkeypatch.setattr(bm, "_linear_apply_label", lambda iid, lid: True)
    monkeypatch.setattr(
        bm, "_call_claude_for_discrepancies",
        lambda sc, target, fc, **kw: [_ITEM_MULTI_BRANCH] if target["category"] == "multi-branch reads" else [],
    )
    monkeypatch.setattr(bm, "_fetch_gap_audit_canonical", lambda: dict(canonical_store))
    monkeypatch.setattr(bm, "_extract_spec_claims", lambda text: ["✅ claim"])

    harness = tmp_path / ".harness"
    harness.mkdir()
    (harness / "board-meetings").mkdir()
    (harness / "spec.md").write_text("✅ content", encoding="utf-8")
    monkeypatch.setattr(bm, "_HARNESS_ROOT", harness)
    monkeypatch.setattr(bm, "_REPO_ROOT", tmp_path)

    # Run 1 — canonical map is empty → creates ticket
    r1 = bm.run_gap_audit_phase(dry_run=False)
    assert r1["summary"]["linear_tickets_created"] == ["RA-200"]

    # Run 2 — canonical map now has the category → enriches instead
    r2 = bm.run_gap_audit_phase(dry_run=False)
    assert r2["summary"]["linear_tickets_created"] == [], "Second run must not create new tickets"
    assert len(comment_calls) == 1, "Second run must enrich existing issue"


# ── SCOUT deduplication ───────────────────────────────────────────────────────

_FINDING = {
    "source": "github",
    "title": "some-org/agent-framework",
    "url": "https://github.com/some-org/agent-framework",
    "description": "A framework for building agents",
    "relevance_score": 3,
    "matched_dims": ["tool_availability"],
    "_id": "abc123",
}


def _stub_scout_sources(monkeypatch, findings: list[dict]) -> None:
    monkeypatch.setattr(scout, "fetch_github_findings", lambda: list(findings))
    monkeypatch.setattr(scout, "fetch_arxiv_findings", lambda: [])
    monkeypatch.setattr(scout, "fetch_hn_findings", lambda: [])
    monkeypatch.setattr(scout, "_load_seen", lambda: [])
    monkeypatch.setattr(scout, "_save_seen", lambda seen: None)
    monkeypatch.setattr(scout, "_score_finding", lambda t, d: (findings[0]["relevance_score"], findings[0]["matched_dims"]))


def test_scout_url_dedup_enriches_open_issue(monkeypatch):
    """When a [SCOUT] issue exists for the same URL, scout enriches it with a comment."""
    enrich_calls: list[tuple] = []
    label_calls: list[tuple] = []

    _stub_scout_sources(monkeypatch, [dict(_FINDING)])
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")
    monkeypatch.setattr(scout, "_get_or_create_scout_label", lambda key: "scout-lbl")
    monkeypatch.setattr(scout, "_get_or_create_cleanup_label", lambda key: "cleanup-lbl")
    monkeypatch.setattr(scout, "_existing_scout_titles", lambda key: set())
    monkeypatch.setattr(scout, "_existing_scout_canonical", lambda key: {
        "https://github.com/some-org/agent-framework": {
            "id": "uuid-scout-open",
            "identifier": "RA-300",
            "state_type": "unstarted",
        },
    })
    monkeypatch.setattr(scout, "_enrich_scout_issue",
                        lambda iid, f, key: enrich_calls.append((iid, f)) or True)
    monkeypatch.setattr(scout, "_apply_label_to_issue",
                        lambda iid, lid, key: label_calls.append((iid, lid)) or True)

    def explode(*a, **kw):  # pragma: no cover
        raise AssertionError("_create_linear_issue must not be called on URL match")
    monkeypatch.setattr(scout, "_create_linear_issue", explode)

    result = scout.run_scout_cycle(dry_run=False)

    assert result["issues_created"] == []
    assert result["skipped_existing"] == 1
    assert len(enrich_calls) == 1
    assert enrich_calls[0][0] == "uuid-scout-open"
    assert len(label_calls) == 1
    assert label_calls[0] == ("uuid-scout-open", "cleanup-lbl")


def test_scout_url_dedup_skips_terminal_issue(monkeypatch):
    """Completed/cancelled URL match → finding is dropped, no enrichment, no creation."""
    enrich_calls: list = []

    _stub_scout_sources(monkeypatch, [dict(_FINDING)])
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")
    monkeypatch.setattr(scout, "_get_or_create_scout_label", lambda key: None)
    monkeypatch.setattr(scout, "_get_or_create_cleanup_label", lambda key: None)
    monkeypatch.setattr(scout, "_existing_scout_titles", lambda key: set())
    monkeypatch.setattr(scout, "_existing_scout_canonical", lambda key: {
        "https://github.com/some-org/agent-framework": {
            "id": "uuid-done",
            "identifier": "RA-200",
            "state_type": "completed",
        },
    })
    monkeypatch.setattr(scout, "_enrich_scout_issue",
                        lambda iid, f, key: enrich_calls.append(iid) or True)

    def explode(*a, **kw):  # pragma: no cover
        raise AssertionError("Must not file when URL matches a terminal issue")
    monkeypatch.setattr(scout, "_create_linear_issue", explode)

    result = scout.run_scout_cycle(dry_run=False)
    assert result["issues_created"] == []
    assert enrich_calls == [], "Must NOT enrich a completed issue"
    assert result["skipped_existing"] == 1


def test_scout_below_threshold_routes_to_inbox(monkeypatch, tmp_path):
    """Findings below _RELEVANCE_THRESHOLD go to the research inbox, not Linear."""
    low_finding = dict(_FINDING)
    low_finding["relevance_score"] = 1
    low_finding["matched_dims"] = ["observability"]

    _stub_scout_sources(monkeypatch, [low_finding])
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")
    monkeypatch.setattr(scout, "_get_or_create_scout_label", lambda key: None)
    monkeypatch.setattr(scout, "_get_or_create_cleanup_label", lambda key: None)
    monkeypatch.setattr(scout, "_existing_scout_titles", lambda key: set())
    monkeypatch.setattr(scout, "_existing_scout_canonical", lambda key: {})
    monkeypatch.setattr(scout, "_score_finding", lambda t, d: (1, ["observability"]))

    # Redirect the inbox to tmp_path
    inbox = tmp_path / "scout-research-inbox.jsonl"
    monkeypatch.setattr(scout, "_RESEARCH_INBOX", inbox)
    monkeypatch.setattr(scout, "_HARNESS", tmp_path)

    def explode(*a, **kw):  # pragma: no cover
        raise AssertionError("Below-threshold must not be filed to Linear")
    monkeypatch.setattr(scout, "_create_linear_issue", explode)

    result = scout.run_scout_cycle(dry_run=False)

    assert result["issues_created"] == [], "Below-threshold must not create Linear tickets"
    assert inbox.exists(), "Research inbox must be written"
    entries = [json.loads(line) for line in inbox.read_text().splitlines() if line.strip()]
    assert len(entries) == 1
    assert entries[0]["url"] == low_finding["url"]
    assert entries[0]["relevance_score"] == 1


def test_scout_canonical_url_fetch_failure_fails_closed(monkeypatch):
    """When _existing_scout_canonical returns None, the cycle still checks _existing_scout_titles.
    If _existing_scout_titles also fails (None), no issues are created (fail-closed)."""
    _stub_scout_sources(monkeypatch, [dict(_FINDING)])
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")
    monkeypatch.setattr(scout, "_get_or_create_scout_label", lambda key: None)
    monkeypatch.setattr(scout, "_get_or_create_cleanup_label", lambda key: None)
    monkeypatch.setattr(scout, "_existing_scout_titles", lambda key: None)  # fail-closed
    monkeypatch.setattr(scout, "_existing_scout_canonical", lambda key: None)

    def explode(*a, **kw):  # pragma: no cover
        raise AssertionError("Must not create when dedup is unavailable")
    monkeypatch.setattr(scout, "_create_linear_issue", explode)

    result = scout.run_scout_cycle(dry_run=False)
    assert result["issues_created"] == []


def test_scout_cleanup_label_applied_on_enrich(monkeypatch):
    """Cleanup label is applied to the enriched issue."""
    label_calls: list[tuple] = []

    _stub_scout_sources(monkeypatch, [dict(_FINDING)])
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")
    monkeypatch.setattr(scout, "_get_or_create_scout_label", lambda key: "scout-lbl")
    monkeypatch.setattr(scout, "_get_or_create_cleanup_label", lambda key: "cleanup-lbl-999")
    monkeypatch.setattr(scout, "_existing_scout_titles", lambda key: set())
    monkeypatch.setattr(scout, "_existing_scout_canonical", lambda key: {
        "https://github.com/some-org/agent-framework": {
            "id": "uuid-open",
            "identifier": "RA-400",
            "state_type": "backlog",
        },
    })
    monkeypatch.setattr(scout, "_enrich_scout_issue", lambda iid, f, key: True)
    monkeypatch.setattr(scout, "_apply_label_to_issue",
                        lambda iid, lid, key: label_calls.append((iid, lid)) or True)

    scout.run_scout_cycle(dry_run=False)

    assert any(lid == "cleanup-lbl-999" for _, lid in label_calls), \
        "cleanup label must be applied when enriching"


# ── _existing_scout_canonical unit tests ─────────────────────────────────────

def test_existing_scout_canonical_parses_url(monkeypatch):
    """_existing_scout_canonical returns URL → {id, identifier, state_type} map."""
    desc = "**Source:** GITHUB\n**URL:** https://github.com/test/repo\n**Relevance Score:** 4/5\n"

    def fake_urlopen(req, timeout=15):
        class _Resp:
            def read(self):
                return json.dumps({"data": {"issues": {"nodes": [
                    {
                        "id": "uuid-abc",
                        "identifier": "RA-111",
                        "title": "[SCOUT] GITHUB: test/repo",
                        "description": desc,
                        "state": {"type": "unstarted"},
                    }
                ]}}}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass
        return _Resp()

    monkeypatch.setattr(scout.urllib.request, "urlopen", fake_urlopen)
    result = scout._existing_scout_canonical("lin_api_test")

    assert result is not None
    assert "https://github.com/test/repo" in result
    entry = result["https://github.com/test/repo"]
    assert entry["identifier"] == "RA-111"
    assert entry["state_type"] == "unstarted"


def test_existing_scout_canonical_none_on_failure(monkeypatch):
    """Returns None on HTTP error so caller can fail-closed."""
    def boom(*a, **kw):
        raise OSError("connection refused")
    monkeypatch.setattr(scout.urllib.request, "urlopen", boom)
    assert scout._existing_scout_canonical("lin_api_test") is None
