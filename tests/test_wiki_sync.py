"""tests/test_wiki_sync.py — wiki → Supabase sync smoke tests."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import wiki_sync  # noqa: E402


@pytest.fixture
def wiki_tmp(tmp_path, monkeypatch):
    wiki = tmp_path / "Wiki"
    wiki.mkdir()
    (wiki / "log.md").write_text("# Log\n", encoding="utf-8")
    (wiki / "topic.md").write_text("# Topic\n\n[[ccw]]\n", encoding="utf-8")
    monkeypatch.setattr(wiki_sync, "_wiki_dir", lambda: wiki)
    return wiki


def test_should_run_when_never_synced():
    assert wiki_sync.should_run({}) is True


def test_should_run_false_after_today_sync_no_log_change(wiki_tmp, tmp_path, monkeypatch):
    today = __import__("datetime").date.today().isoformat()
    monkeypatch.setattr(wiki_sync, "_repo_root", lambda _r=None: tmp_path)
    wiki_sync._save_marker_mtime(tmp_path, wiki_tmp.joinpath("log.md").stat().st_mtime)
    assert wiki_sync.should_run({wiki_sync.STATE_KEY: today}) is False


def test_run_sync_skips_when_no_supabase_key(wiki_tmp, tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_UNITE_GROUP_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_PI_CEO_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    result = wiki_sync.run_sync({}, repo_root=tmp_path)
    assert result.synced == 0
    assert result.error == "no Supabase service key in env"


def test_run_sync_upserts_changed_pages(wiki_tmp, tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_UNITE_GROUP_SERVICE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_UNITE_GROUP_URL", "https://example.supabase.co")

    with patch.object(wiki_sync, "_upsert_page") as upsert:
        result = wiki_sync.run_sync({}, repo_root=tmp_path)

    assert result.synced == 1
    assert result.skipped >= 1  # log.md skipped
    assert not result.errors
    upsert.assert_called_once()
    args = upsert.call_args[0]
    assert args[2] == "topic"
    assert args[3] == "Topic"
