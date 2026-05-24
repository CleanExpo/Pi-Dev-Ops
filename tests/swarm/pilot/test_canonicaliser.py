"""Tests for PillarCanonicaliser — per-source canonical pillar mapping.

Per ADR 001: sources delegate; canonicaliser owns translation. Returns ≥1
master pillars; fallback ["uncategorised"] preserves cardinality invariant.
"""
import pytest
from unittest.mock import patch
from swarm.pilot.canonicaliser import PillarCanonicaliser

MASTER = ["ATIA Meta", "Restoration", "Carpet", "IEP", "Plumbing", "HVAC",
          "Pressure-Washing", "CARSI", "Tier-2 Infra", "Margot", "Wiki"]


def _c():
    with patch("swarm.pilot.canonicaliser.load_master_pillars", return_value=MASTER):
        return PillarCanonicaliser()


@pytest.mark.parametrize("team,expected", [
    ("RA", ["Restoration"]), ("DR", ["Restoration"]), ("NRPG", ["Restoration"]),
    ("CCW", ["Carpet"]), ("CARSI", ["CARSI"]), ("ATIA", ["ATIA Meta"]),
    ("UG", ["Tier-2 Infra"]), ("SYN", ["Tier-2 Infra"]),
    ("ZZZ", ["uncategorised"]), (None, ["uncategorised"]),
])
def test_canonicalise_linear(team, expected):
    assert _c().canonicalise_linear(team) == expected


@pytest.mark.parametrize("vertical,expected", [
    ("Restoration", ["Restoration"]), ("CARSI", ["CARSI"]),
    ("Banking", ["Margot"]), (None, ["Margot"]),
])
def test_canonicalise_margot(vertical, expected):
    assert _c().canonicalise_margot(vertical) == expected


def test_canonicalise_other_sources():
    can = _c()
    assert can.canonicalise_github("Pi-Dev-Ops") == ["Tier-2 Infra"]
    assert can.canonicalise_gmail("msg-id-abc") == ["uncategorised"]
    assert can.canonicalise_wiki("any-slug") == ["Wiki"]


def test_all_methods_return_nonempty_list_for_any_input():
    can = _c()
    for fn in (can.canonicalise_linear, can.canonicalise_margot,
               can.canonicalise_github, can.canonicalise_gmail, can.canonicalise_wiki):
        for raw in (None, "", "garbage"):
            out = fn(raw)
            assert isinstance(out, list) and len(out) >= 1
