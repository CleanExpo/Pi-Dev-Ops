"""Tests for tao_codebase_wiki._read_short_context grounding fix.

Ensures the function does NOT feed the prior WIKI.md back as context
(the wiki-on-wiki regeneration loop), and DOES include actual source files.
"""
from app.server import tao_codebase_wiki as wiki


def test_short_context_excludes_prior_wiki_and_includes_source(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "WIKI.md").write_text("PRIOR WIKI PROSE that must not feed back", encoding="utf-8")
    (d / "README.md").write_text("readme line", encoding="utf-8")
    (d / "core.py").write_text("def primary_thing():\n    return 42\n", encoding="utf-8")

    ctx = wiki._read_short_context(str(tmp_path), "pkg")
    assert "PRIOR WIKI PROSE" not in ctx          # no wiki-on-wiki
    assert "def primary_thing" in ctx             # grounded in source
