"""Unit tests for the mesh_ships row builder (RA-7377).

The route is a thin auth + insert wrapper. Every validation rule lives here
so a malformed payload never becomes a feed row.
"""
from __future__ import annotations

import pytest

from app.server.mesh_ship_write import MAX_FILES, ShipRejected, build_row


def _valid(**overrides):
    payload = {
        "machine": "unite-mac-mini",
        "repo": "CleanExpo/Pi-Dev-Ops",
        "branch": "mesh/unite-mac-mini/ra-7377-abc",
        "sha": "13958db2c4e1a0b7f8d3c2a1b0e9f8d7c6b5a432",
        "subject": "feat(mesh): record the ship",
        "files_changed": 3,
    }
    payload.update(overrides)
    return payload


def test_build_row_keeps_the_schema_columns():
    row = build_row(_valid())
    assert set(row) == {
        "machine", "repo", "branch", "sha", "subject", "files_changed", "shipped_at",
    }
    assert row["machine"] == "unite-mac-mini"
    assert row["repo"] == "CleanExpo/Pi-Dev-Ops"
    assert row["files_changed"] == 3
    assert row["shipped_at"].endswith("+00:00") or "T" in row["shipped_at"]


def test_shipped_at_is_stamped_here_not_taken_from_the_client():
    row = build_row(_valid(shipped_at="1999-01-01T00:00:00Z"))
    assert not row["shipped_at"].startswith("1999")


@pytest.mark.parametrize("field", ["machine", "repo"])
def test_required_fields_reject_blank(field):
    with pytest.raises(ShipRejected, match=field):
        build_row(_valid(**{field: "   "}))


def test_sha_must_be_hex():
    with pytest.raises(ShipRejected, match="sha"):
        build_row(_valid(sha="not-a-sha"))


def test_sha_is_stored_lowercase():
    row = build_row(_valid(sha="A526459"))
    assert row["sha"] == "a526459"


def test_optional_fields_may_be_omitted():
    row = build_row({"machine": "host", "repo": "owner/repo"})
    assert row["branch"] is None
    assert row["sha"] is None
    assert row["subject"] is None
    assert row["files_changed"] == 0


def test_files_changed_rejects_negatives():
    with pytest.raises(ShipRejected, match="files_changed"):
        build_row(_valid(files_changed=-1))


def test_files_changed_rejects_above_cap():
    with pytest.raises(ShipRejected, match="files_changed"):
        build_row(_valid(files_changed=MAX_FILES + 1))


def test_control_characters_are_rejected():
    with pytest.raises(ShipRejected, match="subject"):
        build_row(_valid(subject="ok\nnot-ok"))
