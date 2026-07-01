"""tests/test_tier0_runner.py — UNI-2212 runtime chain-walk executor.

Covers the follow-up slice deferred by tier0_lane's docstring: actually
*running* the resolved chain with failover, the hard privacy gate at runtime
(confidential → local only, OpenRouter never touched), and free-pool capacity
accounting. No network — both provider ``call`` coroutines are stubbed.
"""
from __future__ import annotations

import asyncio

import pytest

from app.server import tier0_lane, tier0_runner


_TIER0_ENV = (
    "TAO_TIER0_FREE_CHAIN", "TAO_TIER0_PAID_SPILL", "TAO_TIER0_LOCAL_MODEL",
    "TAO_TIER0_RPD_CAP", "TAO_TIER0_RPM_CAP",
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    for k in _TIER0_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(tier0_lane, "_LEDGER_PATH", tmp_path / "tier0-ledger.json")
    yield


def _stub_providers(monkeypatch, *, openrouter, ollama):
    """Replace both provider ``call`` coroutines with recording stubs.

    ``openrouter`` / ``ollama`` are callables (model_id) -> (rc, text, cost, err).
    Each records the model_ids it was invoked with on ``.seen``.
    """
    from app.server import provider_openrouter, provider_ollama

    async def or_call(*, prompt, model_id, role="", session_id="",
                      max_tokens=4096, timeout_s=30.0):
        or_call.seen.append(model_id)
        return openrouter(model_id)

    async def ol_call(*, prompt, model_id, role="", session_id="",
                      max_tokens=4096, timeout_s=30.0):
        ol_call.seen.append(model_id)
        return ollama(model_id)

    or_call.seen = []
    ol_call.seen = []
    monkeypatch.setattr(provider_openrouter, "call", or_call)
    monkeypatch.setattr(provider_ollama, "call", ol_call)
    return or_call, ol_call


# ── Verify (a): a gathering task runs on a FREE slug, zero Max consumption ────


def test_runs_on_free_openrouter_with_zero_max(monkeypatch):
    orc, olc = _stub_providers(
        monkeypatch,
        openrouter=lambda m: (0, f"answer from {m}", 0.0, None),
        ollama=lambda m: (0, "LOCAL", 0.0, None),
    )
    res = asyncio.run(tier0_runner.run_tier0("summarise this", role="gather"))

    assert res.ok is True
    # Won on the FIRST free slug; local lane never touched.
    assert res.provider == "openrouter"
    assert res.model_id == tier0_lane.DEFAULT_TIER0_FREE_CHAIN[0]
    assert olc.seen == []
    # No anthropic / claude_print lane exists anywhere in the walk.
    assert all(a.provider in ("openrouter", "ollama") for a in res.attempts)
    # One free request booked against the pool.
    assert tier0_runner._free_rpd_count() == 1


# ── Verify (b): a confidential task is refused free, routed LOCAL only ────────


def test_confidential_routes_local_only(monkeypatch):
    orc, olc = _stub_providers(
        monkeypatch,
        openrouter=lambda m: (0, "LEAK", 0.0, None),
        ollama=lambda m: (0, "local answer", 0.0, None),
    )
    res = asyncio.run(
        tier0_runner.run_tier0("client PII payload", confidential=True))

    assert res.ok is True
    assert res.provider == "ollama"
    assert res.model_id == tier0_lane.DEFAULT_TIER0_LOCAL_MODEL
    # OpenRouter (free or paid) was NEVER invoked with confidential data.
    assert orc.seen == []
    # A confidential task never books against the free pool.
    assert tier0_runner._free_rpd_count() == 0


# ── Failover walk ─────────────────────────────────────────────────────────────


def test_falls_through_to_next_free_slug_on_failure(monkeypatch):
    free = tier0_lane.DEFAULT_TIER0_FREE_CHAIN
    orc, olc = _stub_providers(
        monkeypatch,
        openrouter=lambda m: (1, "", 0.0, "openrouter_http_503")
        if m == free[0] else (0, f"ok {m}", 0.0, None),
        ollama=lambda m: (0, "LOCAL", 0.0, None),
    )
    res = asyncio.run(tier0_runner.run_tier0("classify"))

    assert res.ok is True
    assert res.model_id == free[1]
    assert res.attempts[0].model_id == free[0] and res.attempts[0].rc == 1
    assert olc.seen == []
    # Both free attempts (the failed one + the winner) count against the pool.
    assert tier0_runner._free_rpd_count() == 2


def test_spills_to_local_when_all_openrouter_fail(monkeypatch):
    orc, olc = _stub_providers(
        monkeypatch,
        openrouter=lambda m: (1, "", 0.0, "openrouter_http_429"),
        ollama=lambda m: (0, "local answer", 0.0, None),
    )
    res = asyncio.run(tier0_runner.run_tier0("dedup"))

    assert res.ok is True
    assert res.provider == "ollama"
    # Walked every OpenRouter lane (free + paid) before landing local.
    assert olc.seen == [tier0_lane.DEFAULT_TIER0_LOCAL_MODEL]
    assert len(orc.seen) == (
        len(tier0_lane.DEFAULT_TIER0_FREE_CHAIN)
        + len(tier0_lane.DEFAULT_TIER0_PAID_SPILL)
    )


def test_all_lanes_fail_returns_error(monkeypatch):
    _stub_providers(
        monkeypatch,
        openrouter=lambda m: (1, "", 0.0, "openrouter_down"),
        ollama=lambda m: (1, "", 0.0, "ollama_down"),
    )
    res = asyncio.run(tier0_runner.run_tier0("triage"))

    assert res.ok is False
    assert res.provider is None and res.text == ""
    assert res.error
    # Every lane in the resolved chain was attempted.
    assert len(res.attempts) == len(
        tier0_lane.resolve_tier0_chain(free_available=True))


# ── Capacity accounting: only FREE slugs book against the free pool ──────────


def test_paid_spill_success_books_no_free_request(monkeypatch):
    # Force the free pool closed so the chain starts at the paid spill.
    monkeypatch.setattr(tier0_lane, "free_capacity_available", lambda: False)
    orc, olc = _stub_providers(
        monkeypatch,
        openrouter=lambda m: (0, f"paid {m}", 0.34, None),
        ollama=lambda m: (0, "LOCAL", 0.0, None),
    )
    res = asyncio.run(tier0_runner.run_tier0("extract"))

    assert res.ok is True
    assert res.provider == "openrouter"
    assert res.model_id == tier0_lane.DEFAULT_TIER0_PAID_SPILL[0]
    assert res.cost_usd == pytest.approx(0.34)
    # Paid slug is NOT a free slug — nothing booked against the free RPD pool.
    assert tier0_runner._free_rpd_count() == 0
