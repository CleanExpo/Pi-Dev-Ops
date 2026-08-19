"""The cost-strategy card was renamed in the vault, not in this repo.

`gemma4-cost-strategy.md` became `cheap-model-cost-strategy.md` on 2026-08-19
when Gemma 4 was retired. The card lives in the 2nd-Brain vault, which is not
versioned with this repository, so a host that has not synced the rename would
read nothing and report that as "no opportunities found" — a silent no-op
dressed as a clean scan. These tests hold the dual-read open until the fleet
has caught up.
"""
from __future__ import annotations

import pathlib
import tempfile
from unittest.mock import patch

from swarm import enhancement_scout as ES

CARD = "### 1. Move triage to the cheap tier\n\n### 2. Batch the pulse\n"


def _scan_with_card(filename: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as d:
        (pathlib.Path(d) / filename).write_text(CARD, encoding="utf-8")
        with patch.object(ES, "_wiki_dir", return_value=pathlib.Path(d)):
            return ES._scan_cheap_model_opportunities()


def test_reads_the_current_card_name():
    items = _scan_with_card("cheap-model-cost-strategy.md")
    assert len(items) == 2
    assert items[0]["source"] == "cheap-model-cost-strategy.md"


def test_falls_back_to_the_legacy_card_on_an_unsynced_host():
    """Without this, an unsynced vault turns the scan into a silent no-op."""
    items = _scan_with_card("gemma4-cost-strategy.md")
    assert len(items) == 2


def test_source_names_the_card_actually_read():
    """Provenance must not claim the new card when the old one was read."""
    items = _scan_with_card("gemma4-cost-strategy.md")
    assert items[0]["source"] == "gemma4-cost-strategy.md"


def test_returns_empty_when_no_card_exists_at_all():
    assert _scan_with_card("unrelated.md") == []
