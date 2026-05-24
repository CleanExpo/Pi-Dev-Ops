# tests/swarm/pilot/test_gmail_source.py
from unittest.mock import patch, MagicMock
from swarm.pilot.sources import gmail_source

MASTER = ["ATIA Meta", "Restoration", "Carpet", "IEP", "Plumbing", "HVAC",
          "Pressure-Washing", "CARSI", "Tier-2 Infra", "Margot", "Wiki"]


def _patch_master():
    return patch("swarm.pilot.canonicaliser.load_master_pillars", return_value=MASTER)


def _mock_threads(threads):
    m = MagicMock()
    m.return_value = threads
    return m


def test_collect_yields_uncategorised_pillar():
    thread = {"id": "msg-id-abc", "snippet": "Invoice overdue", "label": "INBOX"}
    with _patch_master(), patch.object(gmail_source, "_fetch_unactioned_threads",
                                       return_value=[thread]):
        c = gmail_source.collect()
    assert c[0].pillar == ["uncategorised"]
    assert c[0].fingerprint == "gmail:thread:msg-id-abc"


def test_collect_empty_when_no_threads():
    with _patch_master(), patch.object(gmail_source, "_fetch_unactioned_threads",
                                       return_value=[]):
        assert gmail_source.collect() == []


def test_collect_source_field_is_gmail():
    thread = {"id": "abc123", "snippet": "test", "label": "INBOX"}
    with _patch_master(), patch.object(gmail_source, "_fetch_unactioned_threads",
                                       return_value=[thread]):
        c = gmail_source.collect()
    assert c[0].source == "gmail"
