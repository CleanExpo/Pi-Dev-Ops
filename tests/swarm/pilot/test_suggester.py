# tests/swarm/pilot/test_suggester.py
from unittest.mock import MagicMock
from swarm.pilot import suggester
from swarm.pilot.types import RawCandidate


def _cand(fp, score=80):
    return RawCandidate(fingerprint=fp, headline="x", pillar=["Tier-2 Infra"],
                        effort="XS", source="github", confidence="HIGH",
                        body={}, impact_score=score)


def test_rank_skips_already_pending_fingerprint():
    m = MagicMock()
    m.is_blocked.return_value = False
    m.has_pending_fingerprint.side_effect = lambda fp: fp == "dup"
    top = suggester._rank([_cand("dup", score=99), _cand("fresh", score=50)], m)
    assert top.fingerprint == "fresh"


def test_rank_returns_none_when_all_pending():
    m = MagicMock()
    m.is_blocked.return_value = False
    m.has_pending_fingerprint.return_value = True
    assert suggester._rank([_cand("a"), _cand("b")], m) is None
