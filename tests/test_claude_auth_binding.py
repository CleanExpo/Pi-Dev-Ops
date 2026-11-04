"""A login verdict holds only for the CLI and environment it checked, and anything
not verified now keeps autonomy from admitting work (Codex review rounds 3 and 4).

Split from test_claude_auth_readiness.py, whose fixtures it reuses."""

from unittest.mock import Mock

import pytest

from app.server import provider_policy as policy
from app.server import sdk_execution_boundary as sdk
from tests import test_claude_auth_readiness as base

LIVE, _status = base.LIVE, base._status
probe = base.probe  # the shared pytest fixture, collected from this module


@pytest.mark.parametrize("change", ["cli", "cli_replaced", "home"])
def test_a_verdict_does_not_carry_over_to_a_different_cli_or_environment(monkeypatch, probe, tmp_path, change):
    """Codex round 3: the cache must be bound to the CLI and child env it checked."""
    assert probe is not None, "cached auth probe is missing"
    monkeypatch.setattr(probe, "_schedule", Mock())
    cli = tmp_path / "claude"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o755)
    monkeypatch.setattr(sdk.shutil, "which", lambda name: str(cli))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**LIVE)))
    probe.refresh()
    assert sdk.generation_readiness()["auth_verified"] is True
    if change == "cli":
        other = tmp_path / "other-claude"
        other.write_text("#!/bin/sh\n")
        other.chmod(0o755)
        monkeypatch.setattr(sdk.shutil, "which", lambda name: str(other))
    elif change == "cli_replaced":
        cli.write_text("#!/bin/sh\necho replaced\n")  # same path, different binary
    else:
        monkeypatch.setenv("HOME", str(tmp_path / "elsewhere"))
    report = sdk.generation_readiness()
    assert report["auth_verified"] is False
    assert report["status"] == "blocked"  # until the new CLI/env passes its own check
    assert any("current CLI or environment" in b for b in report["blockers"])
    assert probe._kick.is_set()  # and the refresher is woken to re-check now


def test_autonomy_drops_the_ticket_when_the_cli_changed_after_a_good_check(monkeypatch, probe, tmp_path):
    """Codex round 4: a CLI/env change must stop admission, not just lose 'verified'."""
    from app.server import autonomy_evidence
    assert probe is not None, "cached auth probe is missing"
    monkeypatch.setattr(probe, "_schedule", Mock())
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**LIVE)))
    probe.refresh()
    emit = Mock()
    assert autonomy_evidence.generation_blocked("TEST-1", emit) is False  # verified: admitted
    other = tmp_path / "replacement-claude"
    other.write_text("#!/bin/sh\n")
    other.chmod(0o755)
    monkeypatch.setattr(sdk.shutil, "which", lambda name: str(other))
    assert autonomy_evidence.generation_blocked("TEST-2", emit) is True
    assert emit.call_args.args[0]["action"] == "session_blocked"


def test_autonomy_drops_the_ticket_before_the_first_check_lands(monkeypatch, probe):
    from app.server import autonomy_evidence
    assert probe is not None, "cached auth probe is missing"
    monkeypatch.setattr(probe, "_schedule", Mock())  # first check still in flight
    assert autonomy_evidence.generation_blocked("TEST-3", Mock()) is True
