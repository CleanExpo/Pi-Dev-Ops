"""RA-7538 — Mission Control supabase component must use supabase_health.

The old wrapper looked up supabase_log.health_check (missing), so the
component sat at not_observed / note=untested. Pointing the lookup at
supabase_health without reading result['ok'] is worse: health_check returns
a dict, and bool(any non-empty dict) is True — a permanent false green.

These tests fail against both the missing-symbol path and bool(dict).
"""

from __future__ import annotations

import asyncio
import inspect

from app.server import supabase_health, supabase_log
from app.server.routes import health_full


def _run(coro):
    return asyncio.run(coro)


def _payload(probe, monkeypatch):
    monkeypatch.setattr(supabase_health, "health_check", probe)
    return _run(health_full._check_supabase())


def test_check_supabase_calls_supabase_health_not_log():
    """Wrong-module lookup is the original defect; this must stay wired."""
    src = inspect.getsource(health_full._check_supabase)
    assert "supabase_health" in src
    assert "supabase_log" not in src
    assert not hasattr(supabase_log, "health_check")


def test_missing_probe_cannot_silently_green(monkeypatch):
    monkeypatch.delattr(supabase_health, "health_check", raising=False)
    payload = _run(health_full._check_supabase())
    assert payload["ok"] is False
    assert payload.get("observed") is not True
    assert payload.get("status") != "live"
    assert payload.get("note") != "untested"
    verdict = health_full.classify({"supabase": payload})
    assert verdict["degraded_components"] == ["supabase"]
    assert verdict["red_components"] == []


def test_unobserved_probe_dict_is_never_live(monkeypatch):
    """observed=False is unproven. bool(dict) would still call this live."""
    payload = _payload(
        lambda: {
            "ok": False,
            "observed": False,
            "detail": "not configured — planted unobserved dict",
        },
        monkeypatch,
    )
    assert payload["ok"] is False
    assert payload["observed"] is False
    assert payload["status"] == "not_observed"
    assert payload["status"] != "live"
    verdict = health_full.classify({"supabase": payload})
    assert verdict["degraded_components"] == ["supabase"]
    assert verdict["red_components"] == []
    assert verdict["ok"] is True  # unobserved degrades; it does not 503


def test_ok_false_observed_dict_is_never_live(monkeypatch):
    """Critic mutation: non-empty {ok: False} must stay red, never live/green.

    bool({"ok": False, "observed": True, "detail": "..."}) is True. The old
    wrapper did ok = bool(fn()), so this exact payload would report live.
    """
    down = {
        "ok": False,
        "observed": True,
        "detail": "Supabase answered HTTP 503 for a read on gate_checks",
    }
    assert bool(down) is True, "positive control: bool(dict) would green this"

    payload = _payload(lambda: down, monkeypatch)

    assert payload.get("note") != "untested", (
        "wrapper never called the probe — that is the original miss path"
    )
    assert payload["ok"] is False
    assert payload["observed"] is True
    assert payload["status"] == "red"
    assert payload["status"] != "live"
    verdict = health_full.classify({"supabase": payload})
    assert verdict["red_components"] == ["supabase"]
    assert verdict["degraded_components"] == []
    assert verdict["ok"] is False
    assert verdict["fully_observed"] is False


def test_ok_and_observed_true_is_live(monkeypatch):
    payload = _payload(
        lambda: {"ok": True, "observed": True, "detail": "read-back succeeded"},
        monkeypatch,
    )
    assert payload["ok"] is True
    assert payload["observed"] is True
    assert payload["status"] == "live"
    verdict = health_full.classify({"supabase": payload})
    assert verdict["red_components"] == []
    assert verdict["degraded_components"] == []
    assert verdict["ok"] is True
    assert verdict["fully_observed"] is True


def test_crashing_probe_is_unobserved_not_live(monkeypatch):
    def boom():
        raise RuntimeError("planted probe crash")

    monkeypatch.setattr(supabase_health, "health_check", boom)
    payload = _run(health_full._check_supabase())
    assert payload["ok"] is False
    assert payload["observed"] is False
    assert payload["status"] == "not_observed"
    assert payload["status"] != "live"
    assert payload.get("note") == "probe_crashed"
