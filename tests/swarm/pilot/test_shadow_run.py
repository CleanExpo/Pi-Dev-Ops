# tests/swarm/pilot/test_shadow_run.py
from unittest.mock import patch
from swarm.pilot.scripts import shadow_run


def test_shadow_run_executes_n_cycles(monkeypatch):
    monkeypatch.setenv("PILOT_SHADOW_MODE", "1")
    monkeypatch.setenv("PILOT_BOT_TOKEN", "test-token")
    monkeypatch.setenv("PILOT_BOT_CHAT_ID", "999")
    monkeypatch.setenv("PILOT_TENANT_SLUG", shadow_run.SHADOW_TENANT)

    outcomes = ["sent", "no_suggestion", "sent", "sent", "sent",
                "no_suggestion", "sent", "sent", "sent", "sent"]
    with patch("swarm.pilot.scripts.shadow_run.scheduler.run_cycle",
               side_effect=outcomes) as rc, \
         patch("swarm.pilot.scripts.shadow_run.RESULTS_FILE") as mock_path:
        mock_path.open.return_value.__enter__ = lambda s: s
        mock_path.open.return_value.__exit__ = lambda s, *a: False
        mock_path.open.return_value.write = lambda x: None
        report = shadow_run.run(n=10)

    assert rc.call_count == 10
    assert report["cycles"] == 10
    assert report["sent"] == 8
    assert report["no_suggestion"] == 2
    assert report["paused"] == 0
    assert report["error"] == 0


def test_shadow_run_aborts_when_shadow_mode_off(monkeypatch):
    monkeypatch.delenv("PILOT_SHADOW_MODE", raising=False)
    try:
        shadow_run.run(n=10)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "PILOT_SHADOW_MODE" in str(exc)


def test_shadow_run_aborts_wrong_tenant(monkeypatch):
    monkeypatch.setenv("PILOT_SHADOW_MODE", "1")
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")  # production tenant — must block
    try:
        shadow_run.run(n=1)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "phill-shadow" in str(exc)
