"""tests/test_pi_ceo_session_fts.py — RA-1991 regression coverage.

Validates:
  * build_index from a synthetic corpus produces searchable rows
  * rebuild_incremental skips unchanged sessions, re-indexes mutated
  * search returns BM25-ranked hits, snippet hilites the match
  * since/until filters work
  * Bad FTS5 queries fail soft (no traceback)
  * tool_use / tool_result blocks are extracted
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import pi_ceo_session_fts as fts  # noqa: E402


def _write_session(root: Path, name: str, turns: list[dict]) -> Path:
    """Helper — synthesise one conversation jsonl with the given turns."""
    proj_dir = root / "-test-project"
    proj_dir.mkdir(parents=True, exist_ok=True)
    path = proj_dir / f"{name}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for i, turn in enumerate(turns):
            rec = {
                "type": turn.get("role", "user"),
                "timestamp": turn.get("ts", "2026-05-05T10:00:00Z"),
                "message": {
                    "role": turn.get("role", "user"),
                    "content": turn.get("content"),
                },
            }
            f.write(json.dumps(rec) + "\n")
    return path


# ── build_index ──────────────────────────────────────────────────────────────


def test_build_index_basic(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [
        {"role": "user", "content": "Help me build a Slack bridge"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "Sure, let me help with the Slack bridge."},
        ]},
    ])
    db = tmp_path / "index.db"
    stats = fts.build_index(db_path=db, source_root=src)
    assert stats.error is None
    assert stats.sessions_indexed == 1
    assert stats.turns_indexed == 2
    assert db.exists()


def test_build_index_skips_empty_session(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    # Session with only non-text records
    proj = src / "-test"
    proj.mkdir()
    (proj / "empty.jsonl").write_text(
        '{"type": "queue-operation", "operation": "ping"}\n', encoding="utf-8",
    )
    db = tmp_path / "index.db"
    stats = fts.build_index(db_path=db, source_root=src)
    assert stats.sessions_indexed == 0
    assert stats.sessions_skipped == 1


def test_build_index_idempotent(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [
        {"role": "user", "content": "test query"},
    ])
    db = tmp_path / "index.db"
    s1 = fts.build_index(db_path=db, source_root=src)
    s2 = fts.build_index(db_path=db, source_root=src)
    assert s1.sessions_indexed == s2.sessions_indexed == 1
    assert s1.turns_indexed == s2.turns_indexed == 1


# ── search ───────────────────────────────────────────────────────────────────


def test_search_returns_bm25_ranked(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [
        {"role": "user", "content": "How do I build a Slack bridge?"},
        {"role": "assistant", "content": "Slack bridge requires a bot token."},
    ])
    _write_session(src, "def-456", [
        {"role": "user", "content": "Tell me about Discord webhooks."},
    ])
    db = tmp_path / "index.db"
    fts.build_index(db_path=db, source_root=src)
    hits = fts.search("Slack", db_path=db, limit=10)
    assert len(hits) == 2
    # Both hits should be from abc-123
    assert all(h.session_id.endswith("abc-123") for h in hits)
    # Snippet must contain «...» hilite delimiters
    assert any("«" in h.snippet for h in hits)


def test_search_with_phrase_query(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [
        {"role": "user", "content": "Tell me about Slack bridge architecture."},
    ])
    _write_session(src, "def-456", [
        {"role": "user", "content": "We discussed both Slack and a bridge for Discord."},
    ])
    db = tmp_path / "index.db"
    fts.build_index(db_path=db, source_root=src)
    # Phrase should rank abc-123 higher than def-456
    hits = fts.search('"Slack bridge"', db_path=db, limit=10)
    assert len(hits) >= 1
    assert hits[0].session_id.endswith("abc-123")


def test_search_no_hits(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [{"role": "user", "content": "hello"}])
    db = tmp_path / "index.db"
    fts.build_index(db_path=db, source_root=src)
    assert fts.search("nonexistentterm", db_path=db) == []


def test_search_bad_query_returns_empty(tmp_path):
    """FTS5 raises OperationalError on syntax errors — must fail soft."""
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [{"role": "user", "content": "hi"}])
    db = tmp_path / "index.db"
    fts.build_index(db_path=db, source_root=src)
    # Unclosed quote — bad FTS5 syntax
    assert fts.search('"unclosed', db_path=db) == []


def test_search_handles_hyphenated_terms(tmp_path):
    """RA-2002 / RA-1991 / etc. must work as bare queries — without
    auto-quoting, FTS5 treats `-` as a column-NOT operator and throws."""
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [
        {"role": "user", "content": "Building RA-2002 ideas bridge today."},
        {"role": "user", "content": "RA-1991 is unrelated."},
    ])
    db = tmp_path / "index.db"
    fts.build_index(db_path=db, source_root=src)
    hits = fts.search("RA-2002", db_path=db)
    assert len(hits) == 1
    assert "RA-2002" in hits[0].snippet or "«RA-2002»" in hits[0].snippet


def test_search_handles_colon_terms(tmp_path):
    """Bare terms with colons must not be parsed as column filters."""
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [
        {"role": "user", "content": "Use foo:bar config syntax for the gateway."},
    ])
    db = tmp_path / "index.db"
    fts.build_index(db_path=db, source_root=src)
    hits = fts.search("foo:bar", db_path=db)
    assert len(hits) == 1


def test_search_db_missing_returns_empty(tmp_path):
    db = tmp_path / "missing.db"
    assert fts.search("anything", db_path=db) == []


def test_search_since_until_filters(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [
        {"role": "user", "content": "old query", "ts": "2026-04-01T00:00:00Z"},
        {"role": "user", "content": "new query", "ts": "2026-05-05T00:00:00Z"},
    ])
    db = tmp_path / "index.db"
    fts.build_index(db_path=db, source_root=src)
    hits_all = fts.search("query", db_path=db)
    assert len(hits_all) == 2
    hits_since = fts.search("query", db_path=db, since="2026-05-01T00:00:00Z")
    assert len(hits_since) == 1
    assert "new" in hits_since[0].snippet
    hits_until = fts.search("query", db_path=db, until="2026-04-30T00:00:00Z")
    assert len(hits_until) == 1
    assert "old" in hits_until[0].snippet


# ── tool_use / tool_result extraction ────────────────────────────────────────


def test_tool_use_blocks_are_indexed(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [
        {"role": "assistant", "content": [
            {"type": "text", "text": "Reading the file."},
            {"type": "tool_use", "name": "Read",
             "input": {"file_path": "/tmp/foo.py"}},
        ]},
    ])
    db = tmp_path / "index.db"
    fts.build_index(db_path=db, source_root=src)
    # Search for the tool name should hit
    hits = fts.search("Read", db_path=db)
    assert len(hits) == 1
    # Search for the tool input path should also hit
    hits_path = fts.search("foo", db_path=db)
    assert len(hits_path) == 1


def test_tool_result_blocks_are_indexed(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [
        {"role": "user", "content": [
            {"type": "tool_result", "content": "FATAL ERROR: database connection refused"},
        ]},
    ])
    db = tmp_path / "index.db"
    fts.build_index(db_path=db, source_root=src)
    hits = fts.search("database", db_path=db)
    assert len(hits) == 1
    assert "database" in hits[0].snippet.lower() or "«database»" in hits[0].snippet.lower()


# ── rebuild_incremental ──────────────────────────────────────────────────────


def test_rebuild_incremental_skips_unchanged(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [{"role": "user", "content": "hi"}])
    db = tmp_path / "index.db"
    fts.build_index(db_path=db, source_root=src)
    # Run incremental — should skip the (unchanged) session
    stats = fts.rebuild_incremental(db_path=db, source_root=src)
    assert stats.sessions_indexed == 0
    assert stats.sessions_skipped == 1


def test_rebuild_incremental_picks_up_mutated(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    path = _write_session(src, "abc-123", [{"role": "user", "content": "first"}])
    db = tmp_path / "index.db"
    fts.build_index(db_path=db, source_root=src)
    # Mutate file: append new turn + bump mtime
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "type": "user", "timestamp": "2026-05-06T00:00:00Z",
            "message": {"role": "user", "content": "second"},
        }) + "\n")
    new_mtime = time.time() + 10
    import os  # noqa: PLC0415
    os.utime(path, (new_mtime, new_mtime))
    stats = fts.rebuild_incremental(db_path=db, source_root=src)
    assert stats.sessions_indexed == 1
    assert stats.turns_indexed == 2  # both turns re-indexed
    # Search for second confirms the new content is searchable
    hits = fts.search("second", db_path=db)
    assert len(hits) == 1


def test_rebuild_incremental_picks_up_new_session(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    _write_session(src, "abc-123", [{"role": "user", "content": "first"}])
    db = tmp_path / "index.db"
    fts.build_index(db_path=db, source_root=src)
    # Add new session
    _write_session(src, "def-456", [{"role": "user", "content": "second session"}])
    stats = fts.rebuild_incremental(db_path=db, source_root=src)
    assert stats.sessions_indexed == 1
    assert stats.sessions_skipped == 1


# ── Source root missing ──────────────────────────────────────────────────────


def test_build_index_missing_source_returns_error(tmp_path):
    src = tmp_path / "no-such-dir"
    db = tmp_path / "index.db"
    stats = fts.build_index(db_path=db, source_root=src)
    assert stats.error is not None
    assert "source_root_missing" in stats.error
    assert stats.sessions_indexed == 0


# ── Kill-switch integration ──────────────────────────────────────────────────


def test_build_index_respects_kill_switch(tmp_path):
    src = tmp_path / "projects"
    src.mkdir()
    for i in range(5):
        _write_session(src, f"sess-{i}", [{"role": "user", "content": f"s{i}"}])

    class _StopAfter:
        """Mock LoopCounter — raises after N ticks to simulate a kill-switch."""
        def __init__(self, n: int) -> None:
            self.n = n
            self.count = 0

        def tick(self) -> None:
            self.count += 1
            if self.count > self.n:
                raise RuntimeError("MAX_ITERS")

    db = tmp_path / "index.db"
    counter = _StopAfter(2)
    stats = fts.build_index(db_path=db, source_root=src, loop_counter=counter)
    # After 2 ticks the third call raises — index has fewer than 5 sessions
    assert stats.error is not None
    assert "kill_switch" in stats.error
