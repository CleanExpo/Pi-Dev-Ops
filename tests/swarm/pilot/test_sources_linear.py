# tests/swarm/pilot/test_sources_linear.py
from unittest.mock import patch
from swarm.pilot.sources import linear_source

MASTER = ["ATIA Meta", "Restoration", "Carpet", "IEP", "Plumbing", "HVAC",
          "Pressure-Washing", "CARSI", "Tier-2 Infra", "Margot", "Wiki"]


def _patch_master():
    return patch("swarm.pilot.canonicaliser.load_master_pillars", return_value=MASTER)


def _issue(id_, team_key):
    return {"id": id_, "title": "x", "state": "In Progress",
            "updatedAt": "2026-05-01T00:00:00Z", "team": {"key": team_key}}


def test_collect_RA_yields_restoration_and_correct_fingerprint():
    with _patch_master(), patch.object(linear_source, "_fetch_in_flight_epics",
                                        return_value=[_issue("RA-2947", "RA")]):
        c = linear_source.collect()
    assert c[0].pillar == ["Restoration"]
    assert c[0].fingerprint == "linear:stale_epic:RA-2947"


def test_collect_unknown_team_yields_uncategorised():
    with _patch_master(), patch.object(linear_source, "_fetch_in_flight_epics",
                                        return_value=[_issue("ZZZ-1", "ZZZ")]):
        assert linear_source.collect()[0].pillar == ["uncategorised"]


def test_module_has_no_team_to_pillar_constant():
    assert not hasattr(linear_source, "_TEAM_TO_PILLAR")


def test_collect_empty_when_no_stale():
    with _patch_master(), patch.object(linear_source, "_fetch_in_flight_epics", return_value=[]):
        assert linear_source.collect() == []
