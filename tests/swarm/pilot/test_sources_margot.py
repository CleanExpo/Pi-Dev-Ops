# tests/swarm/pilot/test_sources_margot.py
import pytest
from unittest.mock import patch, MagicMock
from swarm.pilot.sources import margot_source

MASTER = ["ATIA Meta", "Restoration", "Carpet", "IEP", "Plumbing", "HVAC",
          "Pressure-Washing", "CARSI", "Tier-2 Infra", "Margot", "Wiki"]


def _patch_master():
    return patch("swarm.pilot.canonicaliser.load_master_pillars", return_value=MASTER)


def _mock_client(rows):
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.execute.return_value.data = rows
    return c


@pytest.mark.parametrize("vertical,expected", [
    ("Restoration", ["Restoration"]),
    (None, ["Margot"]),
])
def test_collect_pillar_via_canonicaliser(vertical, expected):
    rows = [{"id": 1, "topic": "x", "status": "pending", "vertical": vertical}]
    with _patch_master(), patch.object(margot_source, "_supabase_client",
                                        return_value=_mock_client(rows)):
        assert margot_source.collect()[0].pillar == expected


def test_collect_empty_when_no_pending():
    with _patch_master(), patch.object(margot_source, "_supabase_client",
                                        return_value=_mock_client([])):
        assert margot_source.collect() == []


def test_module_has_no_valid_pillars_constant():
    assert not hasattr(margot_source, "_VALID_PILLARS")
