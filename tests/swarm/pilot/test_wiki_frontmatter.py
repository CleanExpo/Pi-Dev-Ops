"""Tests for wiki_frontmatter.py — master pillar enum loader.

Per ADR 001: wiki YAML frontmatter is the single source of truth for the pillar enum.
"""
from pathlib import Path
import pytest
from swarm.pilot import wiki_frontmatter as wf

FIXTURE = """---
type: wiki
updated: 2026-05-15
pillars:
  - ATIA Meta
  - Restoration
  - Carpet
  - IEP
  - Plumbing
  - HVAC
  - Pressure-Washing
  - CARSI
  - Tier-2 Infra
  - Margot
  - Wiki
---

# Master plan body.
"""


def _fixture(tmp_path: Path, body: str = FIXTURE) -> Path:
    p = tmp_path / "master-plan.md"
    p.write_text(body)
    return p


def test_load_pillars_returns_eleven(tmp_path):
    wf._cache.clear()
    pillars = wf.load_master_pillars(path=_fixture(tmp_path))
    assert len(pillars) == 11
    assert "ATIA Meta" in pillars and "Tier-2 Infra" in pillars


def test_ttl_cache_serves_stale_then_invalidate_forces_reload(tmp_path):
    p = _fixture(tmp_path)
    wf._cache.clear()
    first = wf.load_master_pillars(path=p)
    p.write_text(FIXTURE.replace("- Wiki", "- Wiki\n  - ExtraThing"))
    cached = wf.load_master_pillars(path=p)
    assert first == cached  # cache hit, no reload
    wf.invalidate_cache()
    fresh = wf.load_master_pillars(path=p)
    assert "ExtraThing" in fresh


@pytest.mark.parametrize("body,match", [
    ("# No frontmatter", "frontmatter"),
    ("---\ntype: wiki\n---\nbody", "pillars"),
    ("---\npillars: []\n---\nbody", "pillars"),
])
def test_bad_frontmatter_raises(tmp_path, body, match):
    p = tmp_path / "broken.md"
    p.write_text(body)
    wf._cache.clear()
    with pytest.raises(RuntimeError, match=match):
        wf.load_master_pillars(path=p)
