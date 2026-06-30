"""tests/test_tier0_lane.py — UNI-2212 unit tests for the Tier-0 gathering lane.

Covers the pure chain resolver, the hard privacy gate, and the RPD/RPM
capacity ledger. No network; the ledger is redirected to a temp file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.server import tier0_lane


_TIER0_ENV = (
    "TAO_TIER0_FREE_CHAIN", "TAO_TIER0_PAID_SPILL", "TAO_TIER0_LOCAL_MODEL",
    "TAO_TIER0_RPD_CAP", "TAO_TIER0_RPM_CAP",
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Clear Tier-0 env overrides and point the ledger at a temp file."""
    for k in _TIER0_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(tier0_lane, "_LEDGER_PATH", tmp_path / "tier0-ledger.json")
    yield


# ── Chain resolver ───────────────────────────────────────────────────────────


def test_free_first_when_capacity_available():
    chain = tier0_lane.resolve_tier0_chain(free_available=True)
    # Free OpenRouter slugs lead, paid spill next, local Ollama last.
    assert chain[0] == ("openrouter", tier0_lane.DEFAULT_TIER0_FREE_CHAIN[0])
    assert chain[-1] == ("ollama", tier0_lane.DEFAULT_TIER0_LOCAL_MODEL)
    providers = [p for p, _ in chain]
    assert providers[-1] == "ollama"
    # Paid spill slugs are present after the free ones.
    assert ("openrouter", tier0_lane.DEFAULT_TIER0_PAID_SPILL[0]) in chain


def test_free_dropped_when_exhausted():
    chain = tier0_lane.resolve_tier0_chain(free_available=False)
    free_slugs = {("openrouter", s) for s in tier0_lane.DEFAULT_TIER0_FREE_CHAIN}
    assert not (free_slugs & set(chain)), "free slugs must be dropped when exhausted"
    # Spill + local remain, in order.
    assert chain[0] == ("openrouter", tier0_lane.DEFAULT_TIER0_PAID_SPILL[0])
    assert chain[-1] == ("ollama", tier0_lane.DEFAULT_TIER0_LOCAL_MODEL)


def test_privacy_gate_confidential_is_local_only():
    chain = tier0_lane.resolve_tier0_chain(confidential=True, free_available=True)
    assert chain == [("ollama", tier0_lane.DEFAULT_TIER0_LOCAL_MODEL)]
    # No OpenRouter (free or paid) ever carries confidential data.
    assert all(p == "ollama" for p, _ in chain)


def test_select_tier0_lane_returns_head():
    assert tier0_lane.select_tier0_lane(confidential=False) == (
        "openrouter", tier0_lane.DEFAULT_TIER0_FREE_CHAIN[0],
    )
    assert tier0_lane.select_tier0_lane(confidential=True) == (
        "ollama", tier0_lane.DEFAULT_TIER0_LOCAL_MODEL,
    )


def test_env_overrides_chain(monkeypatch):
    monkeypatch.setenv("TAO_TIER0_FREE_CHAIN", "a/b:free, c/d:free")
    monkeypatch.setenv("TAO_TIER0_PAID_SPILL", "e/f")
    monkeypatch.setenv("TAO_TIER0_LOCAL_MODEL", "myllama:latest")
    chain = tier0_lane.resolve_tier0_chain(free_available=True)
    assert chain == [
        ("openrouter", "a/b:free"),
        ("openrouter", "c/d:free"),
        ("openrouter", "e/f"),
        ("ollama", "myllama:latest"),
    ]


# ── Capacity ledger (RPD / RPM) ──────────────────────────────────────────────


def test_capacity_available_on_empty_ledger():
    assert tier0_lane.free_capacity_available() is True


def test_rpd_cap_flips_capacity_false(monkeypatch):
    monkeypatch.setenv("TAO_TIER0_RPD_CAP", "3")
    monkeypatch.setenv("TAO_TIER0_RPM_CAP", "100")  # keep RPM out of the way
    for _ in range(3):
        assert tier0_lane.free_capacity_available() is True
        tier0_lane.record_free_request()
    assert tier0_lane.free_capacity_available() is False


def test_rpm_cap_flips_capacity_false(monkeypatch):
    monkeypatch.setenv("TAO_TIER0_RPD_CAP", "100000")  # keep RPD out of the way
    monkeypatch.setenv("TAO_TIER0_RPM_CAP", "2")
    tier0_lane.record_free_request()
    assert tier0_lane.free_capacity_available() is True
    tier0_lane.record_free_request()
    assert tier0_lane.free_capacity_available() is False


def test_ledger_persists_atomically(monkeypatch):
    monkeypatch.setenv("TAO_TIER0_RPD_CAP", "50")
    tier0_lane.record_free_request()
    assert tier0_lane._LEDGER_PATH.exists()
    assert not Path(str(tier0_lane._LEDGER_PATH) + ".tmp").exists()


def test_exhaustion_fires_edge_triggered_alert(monkeypatch):
    monkeypatch.setenv("TAO_TIER0_RPD_CAP", "1")
    monkeypatch.setenv("TAO_TIER0_RPM_CAP", "100")
    calls: list[dict] = []
    import swarm.telegram_alerts as ta
    monkeypatch.setattr(ta, "send", lambda *a, **k: calls.append(k) or True)
    tier0_lane.record_free_request()  # hits RPD cap of 1
    assert len(calls) == 1
    assert calls[0]["dedup_key"] == "tier0_free_rpd_exhausted"
    assert calls[0]["severity"] == "high"
