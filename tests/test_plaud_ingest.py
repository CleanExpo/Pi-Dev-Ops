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
