"""A login verdict holds only for the CLI and environment it checked, and anything
not verified now keeps autonomy from admitting work (Codex review rounds 3 and 4).

Split from test_claude_auth_readiness.py, whose fixtures it reuses."""

import json
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


# Every reader of the cached login, against every state that is not "verified now".
# Writers: claude_auth_probe.refresh() (and reset()). Sole direct reader:
# generation_readiness(), consumed by the three paths below. Dispatch itself re-runs
# the frozen check live (sdk_attempt.py) and never reads this cache.
def _read_health():
    return json.loads(base._authed_health()[1])["generation"]["status"] == "blocked"


def _read_admission():
    from app.server import autonomy_evidence
    return autonomy_evidence.generation_blocked("TEST-M", Mock())


def _read_autonomy_status():
    from app.server import autonomy
    return autonomy.autonomy_status()["generation"]["status"] == "blocked"


def _enter(state, monkeypatch, probe, tmp_path):
    monkeypatch.setattr(probe, "_schedule", Mock())
    if state == "unstartable":
        monkeypatch.setattr(probe, "_schedule", Mock(side_effect=RuntimeError("can't start new thread")))
        return
    if state == "pending":
        return
    payload = {**LIVE, "loggedIn": False} if state == "dead" else LIVE
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**payload)))
    probe.refresh()
    if state == "stale":
        now = probe._clock()
        monkeypatch.setattr(probe, "_clock", lambda: now + probe.TTL_S)
    elif state == "cached_then_unstartable":  # Codex round 6: refresher died after a good check
        monkeypatch.setattr(probe, "_schedule", Mock(side_effect=RuntimeError("can't start new thread")))
    elif state == "rebound":
        other = tmp_path / "replacement-claude"
        other.write_text("#!/bin/sh\n")
        other.chmod(0o755)
        monkeypatch.setattr(sdk.shutil, "which", lambda name: str(other))


@pytest.mark.parametrize("reader", [_read_health, _read_admission, _read_autonomy_status],
                         ids=["health", "admission", "autonomy_status"])
@pytest.mark.parametrize("state", ["verified", "pending", "dead", "stale", "rebound", "unstartable",
                                   "cached_then_unstartable"])
def test_every_reader_blocks_on_every_unverified_state(monkeypatch, probe, tmp_path, reader, state):
    assert probe is not None, "cached auth probe is missing"
    _enter(state, monkeypatch, probe, tmp_path)
    assert reader() is (state != "verified")  # verified is the positive control
