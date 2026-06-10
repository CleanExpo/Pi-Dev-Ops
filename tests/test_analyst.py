"""tests/test_analyst.py — Analyst direction layer smoke tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import analyst  # noqa: E402


@pytest.fixture
def wiki_tmp(tmp_path, monkeypatch):
    wiki = tmp_path / "Wiki"
    wiki.mkdir()
    (wiki / "index.md").write_text("# Index\n", encoding="utf-8")
    monkeypatch.setattr(analyst, "_wiki_dir", lambda: wiki)
    monkeypatch.setenv("TAO_ANALYST_ENABLED", "1")
    return wiki


def test_deliverable_is_complete_when_section11_present():
    d = analyst.AnalystDeliverable(
        question="Should we raise ad spend?",
        answer="Not until LTV:CAC recovers.",
        leading_alternative="Scale now — rejected due to CPA breach.",
        critical_unknowns=["Blended CPA trend last 14 days"],
        kill_switch="LTV:CAC above 5.0 for two consecutive weeks",
    )
    assert d.is_complete()
    md = d.to_markdown()
    assert "## Kill-switch" in md
    assert "LTV:CAC above 5.0" in md


def test_deterministic_deliverable_without_llm(wiki_tmp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        analyst,
        "_synthesise_deliverable",
        lambda *a, **k: analyst._deterministic_deliverable(*a, **k),
    )
    out = analyst.maybe_analyse_research(
        "CCW churn risk",
        "CCW detractors rose this week.",
        [{"topic": "wiki", "depth": "wiki", "summary": "Prior NPS was 42."}],
        turn_id="mt-test",
        repo_root=tmp_path,
    )
    assert out.is_complete()
    assert (wiki_tmp / "analyst").exists()
    notes = list((wiki_tmp / "analyst").glob("*.md"))
    assert len(notes) == 1
    ledger = tmp_path / analyst.ANALYST_LEDGER_REL
    assert ledger.exists()


def test_breach_review_clean_when_no_ledgers(tmp_path, monkeypatch):
    monkeypatch.setattr(analyst, "_collect_breaches", lambda _r: [])
    result = analyst.run_breach_review(repo_root=tmp_path)
    assert result["status"] == "clean"
    assert result["breaches"] == []


def test_breach_review_filed_when_breaches_present(wiki_tmp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        analyst,
        "_collect_breaches",
        lambda _r: [{"agent": "cmo", "metric": "ltv_cac_ratio", "severity": "warning", "note": "LTV:CAC 2.1"}],
    )
    result = analyst.run_breach_review(repo_root=tmp_path)
    assert result["status"] == "filed"
    assert len(result["breaches"]) == 1
    breach_notes = list((wiki_tmp / "analyst").glob("breach-review-*.md"))
    assert len(breach_notes) == 1


def test_should_run_breach_review_daily_cadence():
    assert analyst.should_run_breach_review({}) is True
    today = __import__("datetime").date.today().isoformat()
    assert analyst.should_run_breach_review({analyst.STATE_KEY: today}) is False


def test_aip_watcher_queues_new_block(tmp_path, monkeypatch):
    from swarm import aip_watcher  # noqa: E402

    wiki = tmp_path / "Wiki"
    wiki.mkdir()
    payload = {"kind": "PortfolioService", "id": "ra", "display_name": "RestoreAssist"}
    (wiki / "ra.md").write_text(f"---\ntype: wiki\n---\n\n```aip\n{json.dumps(payload)}\n```\n", encoding="utf-8")
    monkeypatch.setattr(aip_watcher, "_wiki_dir", lambda: wiki)

    state: dict = {}
    result = aip_watcher.run_daily(state, repo_root=tmp_path)
    assert result.entities_queued == 1
    assert result.pages_scanned == 1
    assert "aip://unite-group/PortfolioService/ra" in result.queued_uris

    queue = tmp_path / aip_watcher.QUEUE_REL
    assert queue.exists()
    row = json.loads(queue.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["uri"] == "aip://unite-group/PortfolioService/ra"


def test_aip_flush_upserts_queued_entity(tmp_path, monkeypatch):
    from swarm import aip_watcher  # noqa: E402

    root = tmp_path / "repo"
    root.mkdir()
    queue = root / aip_watcher.QUEUE_REL
    queue.parent.mkdir(parents=True)
    row = {
        "page": "ra.md",
        "uri": "aip://unite-group/PortfolioService/ra",
        "hash": "abc123",
        "payload": {"kind": "PortfolioService", "id": "ra", "display_name": "RestoreAssist"},
    }
    queue.write_text(json.dumps(row) + "\n", encoding="utf-8")

    monkeypatch.setenv("SUPABASE_UNITE_GROUP_SERVICE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_UNITE_GROUP_URL", "https://example.supabase.co")

    with patch.object(aip_watcher, "_upsert_entity") as upsert:
        result = aip_watcher.flush_queue(repo_root=root)

    assert result.flushed == 1
    assert not result.errors
    upsert.assert_called_once()
    assert queue.read_text(encoding="utf-8") == ""
