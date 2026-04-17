"""
test_integration_health.py — RA-1293 regression tests.

Locks:
  - tick() populates the snapshot and logs every probe.
  - Healthy → unhealthy transition fires Telegram exactly once (not on repeats).
  - get_snapshot() before any tick returns a safe shape (ok=None for each probe).
  - A probe that crashes is recorded as unhealthy, not re-raised.
"""
from unittest.mock import patch

from app.server import integration_health as ih


def _reset_module():
    ih._last_snapshot = {}
    ih._last_state = {}
    ih._tick_count = 0
    ih._last_tick_at = 0.0


def test_snapshot_before_any_tick_is_safe():
    _reset_module()
    snap = ih.get_snapshot()
    assert snap["tick"] == 0
    assert snap["all_healthy"] is None
    # Every probe name is represented with ok=None
    for name in ih._PROBES:
        assert snap["checks"][name]["ok"] is None


def test_tick_populates_snapshot_and_flags_all_healthy():
    _reset_module()
    with patch.dict(ih._PROBES, {
        "linear_api_key":   lambda: (True,  "ok"),
        "github_token":     lambda: (True,  "login=bot"),
        "linear_poll_live": lambda: (True,  "last_poll_age_s=12"),
    }, clear=True):
        snap = ih.tick()
    assert snap["tick"] == 1
    assert snap["all_healthy"] is True
    for name in ("linear_api_key", "github_token", "linear_poll_live"):
        assert snap["checks"][name]["ok"] is True


def test_transition_healthy_to_unhealthy_fires_telegram_once():
    _reset_module()

    # First tick: healthy — NO telegram
    with patch.dict(ih._PROBES, {"linear_api_key": lambda: (True, "ok")}, clear=True), \
         patch.object(ih, "_notify_telegram") as notify:
        ih.tick()
        assert notify.call_count == 0

    # Second tick: unhealthy — telegram fires exactly once
    with patch.dict(ih._PROBES, {"linear_api_key": lambda: (False, "HTTP 401")}, clear=True), \
         patch.object(ih, "_notify_telegram") as notify:
        ih.tick()
        assert notify.call_count == 1
        args = notify.call_args[0]
        assert args[0] == "linear_api_key"
        assert "401" in args[1]

    # Third tick: still unhealthy — NO repeat telegram
    with patch.dict(ih._PROBES, {"linear_api_key": lambda: (False, "HTTP 401")}, clear=True), \
         patch.object(ih, "_notify_telegram") as notify:
        ih.tick()
        assert notify.call_count == 0


def test_probe_exception_recorded_as_unhealthy():
    _reset_module()

    def explode():
        raise RuntimeError("boom")

    with patch.dict(ih._PROBES, {"linear_api_key": explode}, clear=True):
        snap = ih.tick()
    assert snap["checks"]["linear_api_key"]["ok"] is False
    assert "boom" in snap["checks"]["linear_api_key"]["detail"]


def test_startup_transition_from_unknown_to_unhealthy_does_not_fire():
    """RA-1293 — first-ever probe returning False must NOT fire Telegram.

    Only True → False transitions notify. False on first probe is a cold-start
    condition (probably the poller hasn't run yet, or Railway env is loading)
    and would spam the user with a ping on every deploy.
    """
    _reset_module()
    with patch.dict(ih._PROBES, {"linear_api_key": lambda: (False, "HTTP 401")}, clear=True), \
         patch.object(ih, "_notify_telegram") as notify:
        ih.tick()
        assert notify.call_count == 0
