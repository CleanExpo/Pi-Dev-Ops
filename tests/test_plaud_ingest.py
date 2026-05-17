"""Tests for scripts/plaud_ingest.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import plaud_ingest


def test_slug_basic():
    assert plaud_ingest.slug_from_name("Acme Q2 Pricing") == "acme-q2-pricing"


def test_slug_punctuation():
    assert plaud_ingest.slug_from_name("Acme Q2 Pricing!?") == "acme-q2-pricing"


def test_slug_unicode_folds_to_ascii():
    assert plaud_ingest.slug_from_name("Café Sync") == "cafe-sync"


def test_slug_empty_falls_back_to_id():
    assert plaud_ingest.slug_from_name("", fallback_id="abc123") == "abc123"


def test_slug_whitespace_only_falls_back():
    assert plaud_ingest.slug_from_name("   ", fallback_id="xyz") == "xyz"


def test_slug_collapses_consecutive_dashes():
    assert plaud_ingest.slug_from_name("foo --- bar") == "foo-bar"


def test_splitter_no_split_under_limit():
    segments = [{"start_ms": i*1000, "end_ms": (i+1)*1000, "speaker": "A", "text": "x"*10}
                for i in range(50)]
    parts = plaud_ingest.split_segments(segments, max_chars=10_000)
    assert len(parts) == 1
    assert parts[0] == segments


def test_splitter_breaks_on_segment_boundary():
    segments = [{"start_ms": i*1000, "end_ms": (i+1)*1000, "speaker": "A", "text": "x"*1000}
                for i in range(60)]  # ~60k chars total
    parts = plaud_ingest.split_segments(segments, max_chars=20_000)
    assert len(parts) >= 3
    rebuilt = [seg for part in parts for seg in part]
    assert rebuilt == segments
    for part in parts:
        chars = sum(len(s["text"]) for s in part)
        assert chars <= 20_000 or len(part) == 1


def test_splitter_single_huge_segment_kept_intact():
    # Pathological: one segment alone exceeds limit. Don't split mid-segment.
    segments = [{"start_ms": 0, "end_ms": 60_000, "speaker": "A", "text": "x"*30_000}]
    parts = plaud_ingest.split_segments(segments, max_chars=20_000)
    assert parts == [segments]
