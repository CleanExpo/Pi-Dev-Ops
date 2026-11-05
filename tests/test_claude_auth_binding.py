"""A login verdict holds only for the CLI and environment it checked, and anything
not verified now keeps autonomy from admitting work (Codex review rounds 3 and 4).

Split from test_claude_auth_readiness.py, whose fixtures it reuses."""

import json
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

from app.server import provider_policy as policy
from app.server import sdk_execution_boundary as sdk
from tests import test_claude_auth_readiness as base

LIVE, _status = base.LIVE, base._status
probe = base.probe  # the shared pytest fixture, collected from this module


@pytest.mark.parametrize("change", ["cli", "cli_replaced", "home"])
def test_a_verdict_does_not_carry_over_to_a_different_cli_or_environment(
        monkeypatch: pytest.MonkeyPatch, probe: ModuleType | None, tmp_path: Path, change: str) -> None:
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


def test_autonomy_drops_the_ticket_when_the_cli_changed_after_a_good_check(
        monkeypatch: pytest.MonkeyPatch, probe: ModuleType | None, tmp_path: Path) -> None:
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


def test_autonomy_drops_the_ticket_before_the_first_check_lands(
        monkeypatch: pytest.MonkeyPatch, probe: ModuleType | None) -> None:
    from app.server import autonomy_evidence
    assert probe is not None, "cached auth probe is missing"
    monkeypatch.setattr(probe, "_schedule", Mock())  # first check still in flight
    assert autonomy_evidence.generation_blocked("TEST-3", Mock()) is True


# Every reader of the cached login, against every state that is not "verified now".
# Writers: claude_auth_probe.refresh() (and reset()). Sole direct reader:
# generation_readiness(), consumed by the three paths below. Dispatch itself re-runs
# the frozen check live (sdk_attempt.py) and never reads this cache.
def _read_health() -> bool:
    return json.loads(base._authed_health()[1])["generation"]["status"] == "blocked"


def _read_admission() -> bool:
    from app.server import autonomy_evidence
    return autonomy_evidence.generation_blocked("TEST-M", Mock())


def _read_autonomy_status() -> bool:
    from app.server import autonomy
    return autonomy.autonomy_status()["generation"]["status"] == "blocked"


def _enter(state: str, monkeypatch: pytest.MonkeyPatch, probe: ModuleType, tmp_path: Path) -> None:
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
def test_every_reader_blocks_on_every_unverified_state(
        monkeypatch: pytest.MonkeyPatch, probe: ModuleType | None, tmp_path: Path,
        reader: Callable[[], bool], state: str) -> None:
    assert probe is not None, "cached auth probe is missing"
    _enter(state, monkeypatch, probe, tmp_path)
    assert reader() is (state != "verified")  # verified is the positive control


def test_a_failed_check_is_rechecked_when_the_cli_changes(
        monkeypatch: pytest.MonkeyPatch, probe: ModuleType | None, tmp_path: Path) -> None:
    """A cached failure is bound to the CLI that failed. A new CLI is re-checked now."""
    assert probe is not None, "cached auth probe is missing"
    monkeypatch.setattr(probe, "_schedule", Mock())
    cli = tmp_path / "claude"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o755)
    monkeypatch.setattr(sdk.shutil, "which", lambda name: str(cli))
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**{**LIVE, "loggedIn": False})))
    probe.refresh()
    assert probe._kick.is_set() is False
    other = tmp_path / "other-claude"
    other.write_text("#!/bin/sh\n")
    other.chmod(0o755)
    monkeypatch.setattr(sdk.shutil, "which", lambda name: str(other))
    report = sdk.generation_readiness()
    assert report["auth_verified"] is False
    assert any("current CLI or environment" in blocker for blocker in report["blockers"])
    assert probe._kick.is_set()


@pytest.mark.parametrize(("second", "changed"), [
    (subprocess.TimeoutExpired("claude", 10), False), (OSError("x"), False),
    (Mock(returncode=2, stdout="", stderr=""), False),
    (Mock(returncode=0, stdout="not-json", stderr=""), False),
    (Mock(returncode=0, stdout="[]", stderr=""), False),
    (Mock(returncode=0, stdout="{}", stderr=""), True),
])
def test_only_a_parsed_disagreement_is_a_login_change(
        monkeypatch: pytest.MonkeyPatch, probe: ModuleType | None,
        second: object, changed: bool) -> None:
    """A second read that fails is unverified. A parsed payload that disagrees changed."""
    assert probe is not None, "cached auth probe is missing"
    monkeypatch.setattr(probe, "_schedule", lambda: None)
    monkeypatch.setattr(policy.subprocess, "run", Mock(side_effect=[_status(**LIVE), second]))
    snap = probe.refresh()
    assert snap["verified"] is False
    assert ("changed during the check" in snap["error"]) is changed
    if not changed:
        assert "could not be verified" in snap["error"]


def test_worker_epoch_is_fixed_when_the_thread_starts(
        monkeypatch: pytest.MonkeyPatch, probe: ModuleType | None) -> None:
    """reset() bumps the epoch. A worker already started must not publish into the new one."""
    assert probe is not None, "cached auth probe is missing"
    started, release, done = threading.Event(), threading.Event(), threading.Event()
    seen: list[int | None] = []
    real = probe.refresh

    def spy(generation: int | None = None) -> dict:
        seen.append(generation)
        started.set()
        release.wait(5)
        try:
            return real(generation)
        finally:
            done.set()

    monkeypatch.setattr(probe, "refresh", spy)
    monkeypatch.setattr(probe, "_schedule", lambda: None)
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**LIVE)))
    captured = probe._epoch
    probe._start_refresh()
    assert started.wait(5)
    with probe._lock:
        probe._epoch += 1
        probe._snapshot = None
        probe._landed.clear()
    release.set()
    assert done.wait(5) and seen == [captured]
    snap = probe.snapshot()
    assert snap["verified"] is False and "not yet verified" in snap["error"]
