"""tests/test_six_pager_chunking.py — 6-pager Telegram chunking smoke."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import six_pager  # noqa: E402


def test_short_brief_returns_single_chunk():
    out = six_pager.chunk_for_telegram("hello world")
    assert out == ["hello world"]


def test_brief_under_limit_returns_single_chunk():
    text = "1. CFO\nshort body\n\n2. CMO\nalso short"
    out = six_pager.chunk_for_telegram(text)
    assert len(out) == 1
    assert out[0] == text


def test_brief_over_limit_splits_at_section_boundary():
    """Six big sections, each ~800 chars → multiple chunks, each starting
    at a section boundary."""
    sections = [
        f"{i}. Section {i}\n" + ("content line " * 80)
        for i in range(1, 7)
    ]
    text = "\n\n".join(sections)
    assert len(text) > six_pager.TELEGRAM_CHUNK_BUDGET

    out = six_pager.chunk_for_telegram(text)
    assert len(out) > 1
    for chunk in out:
        assert len(chunk) <= six_pager.TELEGRAM_CHUNK_BUDGET
    # Every chunk should start with a "<digit>. " section header
    import re
    for chunk in out:
        assert re.match(r"^\d+\.\s", chunk), f"chunk did not start at section: {chunk[:40]!r}"


def test_oversize_single_section_splits_on_paragraphs():
    """One section larger than max_chars → split on blank lines within it."""
    paragraphs = [("paragraph " * 100) for _ in range(20)]
    section = "1. Big section\n\n" + "\n\n".join(paragraphs)
    assert len(section) > 4000

    out = six_pager.chunk_for_telegram(
        section, max_chars=2000,
    )
    assert len(out) > 1
    for chunk in out:
        assert len(chunk) <= 2000


def test_oversize_paragraph_splits_on_lines():
    """A paragraph longer than max_chars (no blank lines) → line-boundary split."""
    long_paragraph = "1. Section\n" + "\n".join(
        ["short line " * 5] * 200
    )
    assert len(long_paragraph) > 5000

    out = six_pager.chunk_for_telegram(
        long_paragraph, max_chars=1000,
    )
    assert len(out) >= 5
    for chunk in out:
        assert len(chunk) <= 1000


def test_oversize_single_line_hard_cuts():
    """A single line longer than max_chars must hard-cut to satisfy the bound."""
    massive = "x" * 5000
    out = six_pager.chunk_for_telegram(massive, max_chars=1000)
    assert len(out) == 5
    assert all(len(c) <= 1000 for c in out)
    assert "".join(out) == massive


def test_chunk_budget_below_telegram_limit():
    """Sanity: the default chunk budget leaves headroom for `[i/N]\\n` headers."""
    assert six_pager.TELEGRAM_CHUNK_BUDGET < six_pager.TELEGRAM_MESSAGE_LIMIT
    # A typical "[12/12]\n" header is ~9 chars; budget should leave at least that.
    assert six_pager.TELEGRAM_MESSAGE_LIMIT - six_pager.TELEGRAM_CHUNK_BUDGET >= 16


def test_assembled_six_pager_chunks_are_safe():
    """End-to-end: even an empty-state assembled brief chunks safely."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        brief = six_pager.assemble_six_pager(
            repo_root=Path(tmp), date_str="2026-05-03",
        )
    chunks = six_pager.chunk_for_telegram(brief)
    assert len(chunks) >= 1
    assert all(len(c) <= six_pager.TELEGRAM_CHUNK_BUDGET for c in chunks)
