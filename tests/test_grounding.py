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


def _anchor_for(tmp_path, parent_text="p", ttl=168):
    return grounding.record(
        primary_source="primary.md",
        derived_from="primary.md",
        parent_text=parent_text,
        ttl_hours=ttl,
    )


def test_reground_fresh(tmp_path):
    (tmp_path / "primary.md").write_text("p", encoding="utf-8")
    anchor = _anchor_for(tmp_path, parent_text="p")
    r = grounding.reground("art://1", anchor, repo_root=tmp_path)
    assert r.status == grounding.FRESH
    assert r.primary_text == "p"


def test_reground_drifted_when_parent_changed(tmp_path):
    (tmp_path / "primary.md").write_text("CHANGED", encoding="utf-8")
    anchor = _anchor_for(tmp_path, parent_text="original")  # sha of "original"
    r = grounding.reground("art://1", anchor, repo_root=tmp_path)
    assert r.status == grounding.DRIFTED
    assert r.primary_text == "CHANGED"  # still returned so caller can re-derive


def test_reground_missing_when_primary_unresolvable(tmp_path):
    anchor = _anchor_for(tmp_path)  # primary.md not written
    r = grounding.reground("art://1", anchor, repo_root=tmp_path)
    assert r.status == grounding.MISSING


def test_reground_stale_past_ttl(tmp_path):
    (tmp_path / "primary.md").write_text("p", encoding="utf-8")
    anchor = _anchor_for(tmp_path, parent_text="p", ttl=1)
    anchor["derived_at"] = "2000-01-01T00:00:00+00:00"  # ancient
    r = grounding.reground("art://1", anchor, repo_root=tmp_path)
    assert r.status == grounding.STALE


def test_reground_cycle_when_self_sourced(tmp_path):
    (tmp_path / "WIKI.md").write_text("w", encoding="utf-8")
    anchor = grounding.record(
        primary_source="WIKI.md", derived_from="WIKI.md", parent_text="w",
    )
    r = grounding.reground("WIKI.md", anchor, repo_root=tmp_path)
    assert r.status == grounding.CYCLE


def test_reground_cycle_on_repeated_lineage(tmp_path):
    (tmp_path / "primary.md").write_text("p", encoding="utf-8")
    anchor = grounding.record(
        primary_source="primary.md", derived_from="b.md", parent_text="p",
        parent_chain=["primary.md", "b.md"],  # b.md repeats
    )
    r = grounding.reground("art://1", anchor, repo_root=tmp_path)
    assert r.status == grounding.CYCLE


def test_require_grounding_returns_fresh(tmp_path):
    (tmp_path / "primary.md").write_text("p", encoding="utf-8")
    anchor = grounding.record(primary_source="primary.md", derived_from="primary.md", parent_text="p")
    r = grounding.require_grounding("art://1", anchor, repo_root=tmp_path)
    assert r.status == grounding.FRESH


def test_require_grounding_raises_on_missing(tmp_path):
    anchor = grounding.record(primary_source="primary.md", derived_from="primary.md", parent_text="p")
    with pytest.raises(grounding.GroundingError):
        grounding.require_grounding("art://1", anchor, repo_root=tmp_path)


def test_require_grounding_allow_ungrounded_downgrades(tmp_path, caplog):
    import logging
    anchor = grounding.record(primary_source="primary.md", derived_from="primary.md", parent_text="p")
    with caplog.at_level(logging.WARNING):
        r = grounding.require_grounding("art://1", anchor, repo_root=tmp_path, allow_ungrounded=True)
    assert r.status == grounding.MISSING
    assert any("ungrounded" in rec.message.lower() for rec in caplog.records)
