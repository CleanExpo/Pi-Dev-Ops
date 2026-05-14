"""Tests for the citation-formatting helpers in swarm.research.gemini_research.

These cover the rendering layer Phill added so PM bot briefings, Telegram
escalations, and Linear comments show ``publisher.tld — Headline`` instead of
the raw Vertex AI redirect URL.

Australian English in code comments.
"""
from __future__ import annotations

import pytest

from swarm.research import format_citation, format_citations_block
from swarm.research.gemini_research import Citation


# ── Sample citations ────────────────────────────────────────────────────────


VERTEX_URL_A = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AAA"
VERTEX_URL_B = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/BBB"

# Title with hyphen separator (the common Gemini shape).
CIT_HYPHEN = Citation(
    url=VERTEX_URL_A,
    title="carsi.com.au - Mould Remediation Pathway",
    snippet="",
)

# Title with em-dash separator.
CIT_EMDASH = Citation(
    url=VERTEX_URL_B,
    title="iicrc.org — S500 Water Damage Standard",
    snippet="",
)

# Title with no separator at all — just the publisher domain.
CIT_NOSEP = Citation(
    url="https://example.invalid/foo",
    title="masterbuilders.com.au",
    snippet="",
)

# Title containing Telegram MarkdownV2 special chars — exercises the escaper.
CIT_TG_SPECIAL = Citation(
    url="https://example.invalid/page",
    title="example.com.au - Standard (v1.2) [draft]!",
    snippet="",
)


# ── format_citation ─────────────────────────────────────────────────────────


def test_format_citation_markdown_uses_dash_when_title_has_separator():
    out = format_citation(CIT_HYPHEN, style="markdown")
    assert out == f"[carsi.com.au — Mould Remediation Pathway]({VERTEX_URL_A})"


def test_format_citation_markdown_handles_emdash_separator():
    out = format_citation(CIT_EMDASH, style="markdown")
    assert out == f"[iicrc.org — S500 Water Damage Standard]({VERTEX_URL_B})"


def test_format_citation_markdown_falls_back_when_no_separator():
    out = format_citation(CIT_NOSEP, style="markdown")
    assert out == "[masterbuilders.com.au](https://example.invalid/foo)"


def test_format_citation_plain_strips_markdown_brackets():
    out = format_citation(CIT_HYPHEN, style="plain")
    assert out == f"carsi.com.au — Mould Remediation Pathway ({VERTEX_URL_A})"


def test_format_citation_compact_returns_publisher_only():
    out = format_citation(CIT_HYPHEN, style="compact")
    assert out == f"[carsi.com.au]({VERTEX_URL_A})"


def test_format_citation_telegram_escapes_reserved_chars():
    out = format_citation(CIT_TG_SPECIAL, style="telegram")
    # MarkdownV2 reserved chars in the label must each be backslash-escaped.
    # The em-dash separator that splits publisher/headline survives intact
    # (it's not in the MD2 reserved set), but ".", "(", ")", "[", "]", "!"
    # must all be escaped inside the link-text run.
    assert "example\\.com\\.au" in out  # dots in domain escaped
    assert "\\(v1\\.2\\)" in out        # parenthesised version
    assert "\\[draft\\]" in out         # bracketed token
    assert "\\!" in out                 # exclamation escaped
    # The closing markdown-link paren is not escaped — it's syntax.
    assert out.endswith(")")
    # And the URL itself is preserved verbatim (no special chars to escape).
    assert "(https://example.invalid/page)" in out


def test_format_citation_telegram_escapes_closing_paren_in_url():
    cit = Citation(url="https://example.invalid/path)withparen", title="example.com")
    out = format_citation(cit, style="telegram")
    # Closing paren inside the URL must be escaped or it would terminate
    # the markdown link early.
    assert "path\\)withparen" in out


def test_format_citation_unknown_style_raises():
    with pytest.raises(ValueError, match="unknown style"):
        format_citation(CIT_HYPHEN, style="bogus")


def test_format_citation_handles_empty_url():
    cit = Citation(url="", title="carsi.com.au - Article")
    out = format_citation(cit, style="markdown")
    # No URL → label only, no markdown link wrapping.
    assert out == "carsi.com.au — Article"


# ── format_citations_block ──────────────────────────────────────────────────


def test_format_citations_block_empty_returns_empty_string():
    assert format_citations_block([], style="markdown") == ""
    assert format_citations_block([], style="telegram") == ""
    assert format_citations_block([], style="plain", heading=None) == ""


def test_format_citations_block_markdown_numbers_list_and_bolds_heading():
    out = format_citations_block(
        [CIT_HYPHEN, CIT_EMDASH, CIT_NOSEP], style="markdown",
    )
    expected = (
        "**Sources**\n"
        f"1. [carsi.com.au — Mould Remediation Pathway]({VERTEX_URL_A})\n"
        f"2. [iicrc.org — S500 Water Damage Standard]({VERTEX_URL_B})\n"
        "3. [masterbuilders.com.au](https://example.invalid/foo)"
    )
    assert out == expected


def test_format_citations_block_custom_heading_renders():
    out = format_citations_block([CIT_HYPHEN], style="markdown", heading="References")
    assert out.startswith("**References**\n1. ")


def test_format_citations_block_no_heading_omits_heading_line():
    out = format_citations_block([CIT_HYPHEN], style="markdown", heading=None)
    # First line should be the numbered citation, not the heading.
    assert out.splitlines()[0].startswith("1. ")


def test_format_citations_block_telegram_escapes_heading_specials():
    out = format_citations_block(
        [CIT_HYPHEN], style="telegram", heading="Sources!",
    )
    # Bold wrapper around an escaped heading text.
    assert out.startswith("*Sources\\!*\n")
