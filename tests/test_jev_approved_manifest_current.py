"""The committed .jev-approved.json must match the files it approves.

A stale hash makes the Jev scout skip that file, and on 31/10/2026 two of the four approved files
(client.py, engine.py) had hashes that never matched any committed version. This test fails the
build the moment an approved file changes without a reviewed re-approval.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jev_platform import ask

REPO = Path(__file__).resolve().parent.parent
FILES = json.loads((REPO / ask.MANIFEST).read_text())["files"]


@pytest.mark.parametrize("rel", sorted(FILES))
def test_approved_hash_matches_the_file(rel):
    assert ask.approve_entry(str(REPO), rel) == {rel: FILES[rel]}, (
        f"{rel} changed since it was approved: re-run `python -m jev_platform approve {rel}`, "
        "review the file and commit the new hash")
