# tests/swarm/pilot/test_digest.py
from unittest.mock import MagicMock
from swarm.pilot import digest


def test_daily_digest_fires_for_paused_hard_tenant():
    """ADR 003: L4 digest IGNORES pause_state — digest survives any pause."""
    m = MagicMock()
    m.get_pause_state.return_value = "paused-hard"
    m.daily_counts.return_value = {"accepted": 0, "deferred": 0, "rejected": 0, "blocked": 0}
    m.top_pending.return_value = []
    text = digest.daily_text(m)
    assert "Pilot daily digest" in text
    m.get_pause_state.assert_not_called()  # digest must never read pause_state


def test_daily_text_contains_counts():
    m = MagicMock()
    m.daily_counts.return_value = {"accepted": 3, "deferred": 1, "rejected": 2, "blocked": 0}
    m.top_pending.return_value = []
    text = digest.daily_text(m)
    assert "3" in text and "accepted" in text.lower()


def test_digest_does_not_import_get_pause_state():
    """Regression guard: digest.py must never call get_pause_state (ADR 003 §3)."""
    import ast, pathlib
    src = pathlib.Path("swarm/pilot/digest.py").read_text()
    assert "get_pause_state" not in src, \
        "digest.py must not reference get_pause_state — ADR 003 scope-separation violation"
