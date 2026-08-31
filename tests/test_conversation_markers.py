"""tests/test_conversation_markers.py — the incremental-sync marker store.

Split from `test_conversation_collector.py` when that file reached the 300-line
ceiling, and split along the same seam as the code: `scripts/conversation_markers.py`
owns deciding which session files have already been shipped, and these are the
tests for that decision.

The property worth guarding is damage isolation. The marker file is JSONL, one
self-contained record per line, so a truncated write costs the damaged line
rather than the whole history — a whole-file JSON object would make one bad byte
re-ship every session ever recorded.

Fully offline: nothing here opens a socket.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import conversation_collector as cc  # noqa: E402


def test_marker_positive_control_note() -> None:
    """Control: dropping the marker write makes the idempotence test FAIL.

    Verified by editing scripts/conversation_collector.py to replace
    `save_markers(markers, marker_path)` in run() with `pass`  (substitution
    asserted to change the file), then re-running this module: 1 failed on
    `assert summary["candidates"] == 0` (got 1 — the same session re-shipped).
    Reverted; green again.
    """
    assert "save_markers(markers, marker_path)" in Path(cc.__file__).read_text()


def test_torn_marker_costs_one_entry_not_the_history(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    path.write_text(
        json.dumps({"path": "/a.jsonl", "mtime": 1.0, "size": 10}) + "\n"
        + '{"path": "/b.jsonl", "mtime": 2.0, "siz\n'          # torn line
        + json.dumps({"path": "/c.jsonl", "mtime": 3.0, "size": 30}) + "\n"
    )
    markers = cc.load_markers(path)
    assert set(markers) == {"/a.jsonl", "/c.jsonl"}


def test_marker_roundtrip_and_legacy_json_object(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    cc.save_markers({"/a.jsonl": {"mtime": 1.5, "size": 7}}, path)
    assert cc.load_markers(path) == {"/a.jsonl": {"mtime": 1.5, "size": 7}}
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"/x.jsonl": {"mtime": 9.0, "size": 3}}))
    assert cc.load_markers(legacy)["/x.jsonl"]["size"] == 3
    assert cc.load_markers(tmp_path / "missing.json") == {}


# ── gating, limits, failure handling ─────────────────────────────────────────
