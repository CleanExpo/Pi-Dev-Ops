from datetime import datetime
import pytest
from app.server import grounding


def test_record_builds_anchor_with_hash_and_timestamp():
    anchor = grounding.record(
        primary_source="brain/plaud/itr.md",
        derived_from="linear://RA-512",
        parent_text="ticket body text",
        ttl_hours=24,
        confidence=0.8,
        parent_chain=["brain/plaud/itr.md"],
    )
    assert anchor["primary_source"] == "brain/plaud/itr.md"
    assert anchor["derived_from"] == "linear://RA-512"
    assert anchor["source_sha256"] == grounding._sha256_hex(b"ticket body text")
    assert anchor["ttl_hours"] == 24
    assert anchor["confidence"] == 0.8
    # chain accumulates parent lineage + this hop's immediate parent
    assert anchor["chain"] == ["brain/plaud/itr.md", "linear://RA-512"]
    # derived_at parses as ISO and is tz-aware
    ts = datetime.fromisoformat(anchor["derived_at"])
    assert ts.tzinfo is not None


def test_anchor_block_round_trips():
    anchor = grounding.record(
        primary_source="brain/plaud/itr.md",
        derived_from="linear://RA-512",
        parent_text="x",
    )
    block = grounding.anchor_to_block(anchor)
    assert block.startswith("<!-- ground:anchor")
    assert block.rstrip().endswith("-->")
    parsed = grounding.anchor_from_text("Some ticket body\n\n" + block)
    assert parsed["primary_source"] == "brain/plaud/itr.md"
    assert parsed["derived_from"] == "linear://RA-512"


def test_anchor_from_text_prose_fallback():
    body = (
        "Scan the flowchart.\n\n---\n"
        "Source: [itr.md](brain/plaud/itr.md)"
    )
    parsed = grounding.anchor_from_text(body)
    assert parsed["primary_source"] == "brain/plaud/itr.md"
    assert parsed["derived_from"] == "brain/plaud/itr.md"
    assert parsed.get("source_sha256", "") == ""  # drift unknown for legacy


def test_anchor_from_text_returns_none_when_absent():
    assert grounding.anchor_from_text("no anchor here") is None


def test_file_resolver_reads_and_hashes(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text("hello primary", encoding="utf-8")
    resolvers = grounding.default_resolvers(tmp_path)
    text, sha = grounding._resolve("doc.md", resolvers)
    assert text == "hello primary"
    assert sha == grounding._sha256_hex(b"hello primary")


def test_resolve_unknown_scheme_raises(tmp_path):
    resolvers = grounding.default_resolvers(tmp_path)
    with pytest.raises(KeyError):
        grounding._resolve("linear://RA-1", resolvers)


def test_scheme_detection():
    assert grounding._scheme("brain/plaud/x.md") == "file"
    assert grounding._scheme("file://x.md") == "file"
    assert grounding._scheme("linear://RA-9") == "linear"
    assert grounding._scheme("https://a.com") == "https"
