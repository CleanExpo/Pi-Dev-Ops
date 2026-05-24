# tests/swarm/pilot/test_sources_github.py
from unittest.mock import patch
from swarm.pilot.sources import github_source

MASTER = ["ATIA Meta", "Restoration", "Carpet", "IEP", "Plumbing", "HVAC",
          "Pressure-Washing", "CARSI", "Tier-2 Infra", "Margot", "Wiki"]


def _patch_master():
    return patch("swarm.pilot.canonicaliser.load_master_pillars", return_value=MASTER)


def test_github_pillar_is_list_via_canonicaliser():
    prs = [{"number": 226, "title": "x", "repository": "Pi-Dev-Ops",
            "hours_since_green": 50, "merged": False}]
    with _patch_master(), patch.object(github_source, "_fetch_stale_green_prs", return_value=prs):
        c = github_source.collect()
    assert c[0].pillar == ["Tier-2 Infra"]


def test_collect_empty_when_no_stale_green():
    with _patch_master(), patch.object(github_source, "_fetch_stale_green_prs", return_value=[]):
        assert github_source.collect() == []
