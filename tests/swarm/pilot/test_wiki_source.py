# tests/swarm/pilot/test_wiki_source.py
from unittest.mock import patch
from swarm.pilot.sources import wiki_source

MASTER = ["ATIA Meta", "Restoration", "Carpet", "IEP", "Plumbing", "HVAC",
          "Pressure-Washing", "CARSI", "Tier-2 Infra", "Margot", "Wiki"]


def _patch_master():
    return patch("swarm.pilot.canonicaliser.load_master_pillars", return_value=MASTER)


def test_collect_yields_wiki_pillar():
    pages = [{"slug": "restoration-overview", "category": "Restoration",
               "days_since_edit": 30}]
    with _patch_master(), patch.object(wiki_source, "_fetch_stale_pages",
                                       return_value=pages):
        c = wiki_source.collect()
    assert c[0].pillar == ["Wiki"]
    assert c[0].fingerprint == "wiki:stale_page:restoration-overview"


def test_collect_empty_when_no_stale_pages():
    with _patch_master(), patch.object(wiki_source, "_fetch_stale_pages",
                                       return_value=[]):
        assert wiki_source.collect() == []


def test_collect_source_field_is_wiki():
    pages = [{"slug": "hvac-guide", "category": "HVAC", "days_since_edit": 60}]
    with _patch_master(), patch.object(wiki_source, "_fetch_stale_pages",
                                       return_value=pages):
        c = wiki_source.collect()
    assert c[0].source == "wiki"
