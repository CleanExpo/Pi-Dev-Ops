"""Tests for swarm.pilot.cli — production cron entrypoint.

The cutover script invokes `python -m swarm.pilot.cli scheduler` per cron
tick, so we lock down:
  - scheduler subcommand emits a JSON line with outcome + tenant_slug
  - exit 0 on any non-exception outcome (incl. no_suggestion / off_hours)
  - exit 1 + JSON error record on exception inside run_cycle
  - health subcommand exit 0 only when required env vars are set
"""
import json
from unittest.mock import patch

import pytest

from swarm.pilot import cli


def _parse(capsys) -> dict:
    out = capsys.readouterr().out.strip().splitlines()
    assert out, "cli should emit at least one JSON line on stdout"
    return json.loads(out[-1])


def test_scheduler_emits_outcome_json(monkeypatch, capsys):
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    with patch("swarm.pilot.scheduler.run_cycle", return_value="no_suggestion"):
        rc = cli.main(["scheduler"])
    assert rc == 0
    rec = _parse(capsys)
    assert rec["outcome"] == "no_suggestion"
    assert rec["tenant_slug"] == "phill"
    assert "ts" in rec


def test_scheduler_default_tenant_when_env_unset(monkeypatch, capsys):
    monkeypatch.delenv("PILOT_TENANT_SLUG", raising=False)
    with patch("swarm.pilot.scheduler.run_cycle", return_value="sent"):
        rc = cli.main(["scheduler"])
    assert rc == 0
    assert _parse(capsys)["tenant_slug"] == "phill"


def test_scheduler_catches_exception_returns_1(monkeypatch, capsys):
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    with patch("swarm.pilot.scheduler.run_cycle", side_effect=RuntimeError("boom")):
        rc = cli.main(["scheduler"])
    assert rc == 1
    rec = _parse(capsys)
    assert rec["outcome"] == "error"
    assert rec["error"] == "boom"
    assert rec["error_type"] == "RuntimeError"


def test_health_unhealthy_when_required_env_missing(monkeypatch, capsys):
    monkeypatch.delenv("PILOT_BOT_TOKEN", raising=False)
    monkeypatch.delenv("PILOT_BOT_CHAT_ID", raising=False)
    rc = cli.main(["health"])
    assert rc == 1
    rec = _parse(capsys)
    assert rec["outcome"] == "unhealthy"
    assert "PILOT_BOT_TOKEN" in rec["required_missing"]
    assert "PILOT_BOT_CHAT_ID" in rec["required_missing"]


def test_health_healthy_when_required_env_present(monkeypatch, capsys):
    monkeypatch.setenv("PILOT_BOT_TOKEN", "tk")
    monkeypatch.setenv("PILOT_BOT_CHAT_ID", "8792816988")
    rc = cli.main(["health"])
    assert rc == 0
    rec = _parse(capsys)
    assert rec["outcome"] == "healthy"
    assert rec["required_missing"] == []


def test_no_subcommand_exits_2(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main([])
    # argparse exits with 2 when required subcommand is missing
    assert excinfo.value.code == 2
