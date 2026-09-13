"""UNI-2633 — one-word dispose. Nothing executes without GO."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.server.idea_pipeline import (
    PipelineGateError,
    append_and_examine,
    authorize_go_for,
    daily_snapshot,
    dispose_idea,
    start_spec_pipeline,
    try_execute_idea,
)
from app.server.idea_pipeline.dispose import dispose, try_execute


def _seed(tmp_path: Path) -> dict:
    return append_and_examine(
        tmp_path,
        "Teach shop owners to grow with a short self-paced video lesson.",
    )


def test_dispose_accepts_only_four_words(tmp_path: Path) -> None:
    packet = _seed(tmp_path)
    idea_id = packet["idea_id"]
    updated = dispose_idea(tmp_path, idea_id, "promote")
    assert updated["verdict"] == "PROMOTE"
    assert updated["executed"] is False
    assert updated["go_at"] is None
    with pytest.raises(PipelineGateError, match="one word"):
        dispose_idea(tmp_path, idea_id, "SHIP")


def test_go_refused_until_promote(tmp_path: Path) -> None:
    packet = _seed(tmp_path)
    parked = dispose_idea(tmp_path, packet["idea_id"], "PARK")
    assert parked["executed"] is False
    with pytest.raises(PipelineGateError, match="after PROMOTE"):
        authorize_go_for(tmp_path, packet["idea_id"])


def test_execute_refused_without_go(tmp_path: Path) -> None:
    packet = _seed(tmp_path)
    promoted = dispose_idea(tmp_path, packet["idea_id"], "PROMOTE")
    assert promoted["executed"] is False
    with pytest.raises(PipelineGateError, match="without GO"):
        try_execute_idea(tmp_path, packet["idea_id"])
    authorized = authorize_go_for(tmp_path, packet["idea_id"])
    assert authorized["go_at"]
    assert authorized["executed"] is False
    requested = try_execute_idea(tmp_path, packet["idea_id"])
    assert requested["execution_requested"] is True
    assert requested["executed"] is False


def test_in_memory_execute_still_false_after_go() -> None:
    packet = {
        "verdict": "PROMOTE",
        "go_at": "2026-09-13T00:00:00+00:00",
        "executed": False,
    }
    after = try_execute(packet)
    assert after["executed"] is False
    killed = dispose(
        {"executed": False, "verdict": None},
        "KILL",
    )
    assert killed["executed"] is False
    with pytest.raises(PipelineGateError, match="without GO"):
        try_execute({"verdict": "PROMOTE", "go_at": None})


def test_snapshot_keeps_promote_visible_until_go(tmp_path: Path) -> None:
    packet = _seed(tmp_path)
    dispose_idea(tmp_path, packet["idea_id"], "PROMOTE")
    snap = daily_snapshot(tmp_path)
    assert snap["packet"] is not None
    assert snap["packet"]["verdict"] == "PROMOTE"
    assert snap["packet"]["go_at"] is None


def test_pipeline_never_auto_starts(tmp_path: Path) -> None:
    packet = _seed(tmp_path)
    with patch("app.server.idea_pipeline.start_spec_pipeline") as starter:
        dispose_idea(tmp_path, packet["idea_id"], "PROMOTE")
        authorize_go_for(tmp_path, packet["idea_id"])
        try_execute_idea(tmp_path, packet["idea_id"])
        starter.assert_not_called()
    with pytest.raises(PipelineGateError, match="does not auto-start"):
        start_spec_pipeline(packet)
