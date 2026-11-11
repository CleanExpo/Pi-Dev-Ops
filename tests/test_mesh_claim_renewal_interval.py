"""tests/test_mesh_claim_renewal_interval.py - M-PDO-REAPER-CLOUD-CLAIM-TTL.

An operator-set MESH_CLAIM_RENEW_INTERVAL_S longer than the claim TTL would let the
reaper release a live cloud claim before its first renewal, so the interval is capped
well inside the 65 min TTL floor.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TTL_FLOOR_S = 65 * 60


def _interval_used(monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> list[float]:
    """Start one cloud renewer with the thread stubbed out; return the interval it got."""
    from app.server import claim_renewal

    seen: list[float] = []

    class _NoThread:
        def __init__(self, target: object, args: tuple, name: str, daemon: bool) -> None:
            seen.append(args[3])

        def start(self) -> None:
            return None

    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    if env_value is None:
        monkeypatch.delenv("MESH_CLAIM_RENEW_INTERVAL_S", raising=False)
    else:
        monkeypatch.setenv("MESH_CLAIM_RENEW_INTERVAL_S", env_value)
    monkeypatch.setattr(claim_renewal.threading, "Thread", _NoThread)
    claim_renewal.start("UNI-9", "claim-9")
    claim_renewal.stop("UNI-9")
    return seen


def test_renew_interval_is_capped_below_the_claim_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _interval_used(monkeypatch, "7200")
    assert seen and seen[0] <= TTL_FLOOR_S / 3, f"renew interval {seen} can outlast the TTL floor"


def test_default_renew_interval_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.server import claim_renewal

    assert _interval_used(monkeypatch, None) == [claim_renewal.RENEW_INTERVAL_S]
