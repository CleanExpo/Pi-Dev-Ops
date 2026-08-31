"""tests/test_conversation_dedupe.py — one session, two project directories.

Split from `test_conversation_collector.py` at the 300-line ceiling. These two
guard `_dedupe_by_id`, and they are deliberately fixture-free: an earlier version
of the first test leaned on the shared `lake` fixture and asserted on the whole
row list, which failed because that fixture contributes a session of its own. A
test that builds exactly the lake it describes cannot be wrong about what is in
it.

Why this matters more than a duplicate row: the id is "<machine>:<session_id>"
and session_id is the JSONL filename stem, so one session under two project
directories — a worktree, a copied checkout — yields two rows with the same id.
Postgres fails such an upsert outright ("ON CONFLICT DO UPDATE command cannot
affect row a second time"), so a single duplicate rejects an entire batch of up
to BATCH_SIZE unrelated digests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import conversation_collector as cc  # noqa: E402

STEM = "1f0e3dad-99ff-4f4a-9f4a-000000000001"


def _lake_with_same_session_twice(tmp_path: Path) -> Path:
    """A lake where one session file appears under two project directories."""
    lake = tmp_path / "lake"
    body = "\n".join(json.dumps(rec) for rec in [
        {"type": "user", "message": {"role": "user", "content": "shared session"}},
        {"type": "assistant", "message": {"role": "assistant", "content": "ack"}},
    ])
    for project in ("-Users-me-Repo", "-Users-me-Repo-worktree"):
        d = lake / project
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{STEM}.jsonl").write_text(body + "\n")
    return lake


def test_one_session_under_two_project_dirs_ships_once(tmp_path: Path) -> None:
    """The duplicate must be collapsed before the batch is built."""
    rows, _fresh = cc.collect_rows(_lake_with_same_session_twice(tmp_path), {}, machine="mac")
    ids = [r["id"] for r in rows]
    assert ids == [f"mac:{STEM}"], f"duplicate id would poison the whole batch: {ids}"


def test_dedupe_keeps_the_most_recently_active_copy() -> None:
    """Newest wins: the two copies are one conversation, and the later
    last_activity_at is the more complete transcript. A dedupe that kept the
    first one seen would silently ship the staler digest."""
    older = {"id": "mac:s1", "last_activity_at": "2026-08-30T01:00:00Z", "title": "older"}
    newer = {"id": "mac:s1", "last_activity_at": "2026-08-30T09:00:00Z", "title": "newer"}
    assert cc._dedupe_by_id([older, newer])[0]["title"] == "newer"
    assert cc._dedupe_by_id([newer, older])[0]["title"] == "newer", "order must not matter"

    # A row carrying the field beats one that does not, either way round.
    missing = {"id": "mac:s2", "title": "no-timestamp"}
    dated = {"id": "mac:s2", "last_activity_at": "2026-08-30T01:00:00Z", "title": "dated"}
    assert cc._dedupe_by_id([missing, dated])[0]["title"] == "dated"
    assert cc._dedupe_by_id([dated, missing])[0]["title"] == "dated"
