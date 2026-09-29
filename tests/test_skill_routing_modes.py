"""SKILL_ROUTER off/shadow/on: shadow never changes the brief; on uses only the routed skill."""
import logging
import threading
import time

import pytest

from app.server import skill_routing

BRIEF = "write a session handoff before I stop for the day"


@pytest.fixture(autouse=True)
def no_live_jev(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(skill_routing, "LEDGER", tmp_path / "ledger.sqlite")
    monkeypatch.setattr(skill_routing, "_CATALOGUE", None)


def test_off_is_exactly_todays_context(monkeypatch):
    monkeypatch.setenv("SKILL_ROUTER", "off")
    assert skill_routing.skill_context(BRIEF, "feature") == skill_routing.legacy_context("feature")


def test_shadow_keeps_todays_context_and_logs_the_decision(monkeypatch, caplog):
    monkeypatch.setenv("SKILL_ROUTER", "shadow")
    with caplog.at_level(logging.INFO, logger="app.server.skill_routing"):
        out = skill_routing.skill_context(BRIEF, "feature")
        skill_routing.wait_for_shadow()
    assert out == skill_routing.legacy_context("feature")
    line = next(r.getMessage() for r in caplog.records if "skill_router" in r.getMessage())
    assert '"picked": ["session-handoff"]' in line and '"source": "lexical_fallback"' in line
    assert BRIEF not in line  # the request itself is never logged, only a hash


def test_on_uses_only_the_routed_skill(monkeypatch):
    monkeypatch.setenv("SKILL_ROUTER", "on")
    out = skill_routing.skill_context(BRIEF, "feature")
    assert "### Skill: session-handoff" in out and out.count("### Skill:") == 1


def test_router_error_falls_back_to_todays_context(monkeypatch, caplog):
    monkeypatch.setenv("SKILL_ROUTER", "on")

    def boom(_):
        raise RuntimeError("catalogue broke")

    monkeypatch.setattr(skill_routing, "_decide", boom)
    with caplog.at_level(logging.WARNING, logger="app.server.skill_routing"):
        assert skill_routing.skill_context(BRIEF, "feature") == skill_routing.legacy_context("feature")
    assert any("RuntimeError" in r.getMessage() for r in caplog.records)


def test_daily_cap_blocks_the_call_and_is_visible(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("SKILL_ROUTER_DAILY_CAP_USD", "0")
    called = []
    monkeypatch.setattr("scripts.mission_control_jev_shadow.evaluate", lambda *a, **k: called.append(1))
    d = skill_routing._decide(BRIEF)
    assert called == [] and d.source == "lexical_fallback" and d.reason == "jev_error:CapReached"


def test_shadow_never_waits_for_a_slow_jev(monkeypatch):
    """Review P1-SHADOW-BLOCKS-BRIEF: a keyed shadow brief blocked 0.33 s on a 0.25 s Jev."""
    monkeypatch.setenv("SKILL_ROUTER", "shadow")
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-real-key")
    release = threading.Event()

    def slow(*_a, **_k):
        release.wait(5)
        raise TimeoutError("jev slow")

    monkeypatch.setattr("scripts.mission_control_jev_shadow.evaluate", slow)
    started = time.monotonic()
    out = skill_routing.skill_context(BRIEF, "feature")
    elapsed = time.monotonic() - started
    release.set()
    skill_routing.wait_for_shadow()
    assert out == skill_routing.legacy_context("feature")
    assert elapsed < 0.2, f"shadow blocked the brief for {elapsed:.3f}s"


def test_a_busy_shadow_skips_rather_than_queues(monkeypatch, caplog):
    monkeypatch.setenv("SKILL_ROUTER", "shadow")
    release = threading.Event()
    calls = []

    def slow(raw):
        calls.append(raw)
        release.wait(5)
        raise RuntimeError("done")

    monkeypatch.setattr(skill_routing, "_decide", slow)
    with caplog.at_level(logging.INFO, logger="app.server.skill_routing"):
        skill_routing.skill_context(BRIEF, "feature")
        skill_routing.skill_context(BRIEF, "feature")
        release.set()
        skill_routing.wait_for_shadow()
    assert len(calls) == 1
    assert any("shadow_skipped_busy" in r.getMessage() for r in caplog.records)


def test_unknown_mode_means_shadow(monkeypatch):
    monkeypatch.setenv("SKILL_ROUTER", "yes please")
    assert skill_routing.mode() == "shadow"
