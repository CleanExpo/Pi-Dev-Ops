"""RA-6903 — prune stale stuck:* keys from linear pulse state."""
from __future__ import annotations

from app.server.linear_pulse import _prune_stale_pulse_state


def test_prune_drops_stuck_keys_for_inactive_sessions():
    state = {
        "pulse_issue_id": "x",
        "stuck:dead-sess:build": 123,
        "stuck:dead-sess:build:alerted": True,
        "stuck:live-sess:plan": 456,
    }
    _prune_stale_pulse_state(state, {"live-sess"})
    assert "stuck:dead-sess:build" not in state
    assert "stuck:dead-sess:build:alerted" not in state
    assert "stuck:live-sess:plan" in state
