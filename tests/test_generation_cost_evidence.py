"""Missing SDK usage evidence must survive aggregation and event formatting."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock

import pytest

from app.server import session_phases as phases
from app.server.session_model import BuildSession


@pytest.mark.parametrize("costs,expected", [
    ([None], None), ([0.2], 0.2), ([None, 0.2], None),
    ([0.1, None], None), ([0.1, 0.2], 0.3), ([float("nan")], None),
])
def test_generation_preserves_unknown_attempt_cost(monkeypatch, tmp_path, costs, expected):
    monkeypatch.setattr(phases.persistence, "save_session", Mock())
    monkeypatch.setattr(phases, "_build_incident_context", lambda **_: "")
    metric = Mock()
    monkeypatch.setattr(phases, "_emit_phase_metric", metric)
    responses = [(0 if i == len(costs) - 1 else 1, "output", cost) for i, cost in enumerate(costs)]
    monkeypatch.setattr(phases, "_run_claude_via_sdk", AsyncMock(side_effect=responses))
    session = BuildSession(workspace=str(tmp_path))
    assert asyncio.run(phases._phase_generate(session, "spec", "sonnet", ""))
    actual = metric.call_args.args[3]
    assert actual is None if expected is None else actual == pytest.approx(expected)


@pytest.mark.parametrize("cost", [None, 0.0, 0.25])
def test_phase_metric_keeps_unknown_and_reported_usage_distinct(cost):
    session = BuildSession()
    phases._emit_phase_metric(session, "generate", time.monotonic(), cost)
    metric = session.phase_metrics["generate"]
    event = session.output_lines[-1]
    assert metric["cost_usd"] == cost
    assert event["cost_usd"] == cost
    assert metric["cost_verified"] is False
    assert event["cost_basis"] == ("unknown" if cost is None else "reported_usage")
    if cost is None:
        assert "unknown" in event["text"]
        assert "$0" not in event["text"]
