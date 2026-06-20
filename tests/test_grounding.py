from datetime import datetime
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
