"""Contract tests for the deterministic routing schema.

These bind the integer contract declared by ``routing_schema`` to the escalation
behaviour in ``task_routing``.  A fractional ``prior_failures`` previously
truncated to zero, which silently suppressed monotonic failure escalation while
the request still validated and exited successfully.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.server.routing_schema import RoutingValidationError
from app.server.task_routing import decide_route


def _request(**signal_overrides: object) -> dict[str, object]:
    """A valid mechanical request: deterministic + shallow => cheap/low."""
    signals: dict[str, object] = {
        "determinism": "high",
        "ambiguity": "low",
        "scope": "inline",
        "reasoning_depth": "shallow",
        "stakes": ["none"],
        "sensitivity": "public",
    }
    signals.update(signal_overrides)
    return {
        "schema_version": "1.0",
        "request_id": "req-escalation",
        "task": "rename a local variable",
        "harness": "claude-code",
        "signals": signals,
        "limits": {"max_parallel_workers": 1},
    }


def test_baseline_mechanical_route_is_cheap_without_failures() -> None:
    """Positive control: the fixture really does produce the cheap floor."""
    decision = decide_route(_request())
    assert decision.quality_floor == "cheap"
    assert "monotonic-failure-escalation" not in decision.reasons


def test_first_integer_failure_retries_same_floor_with_named_feedback() -> None:
    decision = decide_route(
        _request(prior_failures=1, failure_feedback=["unit-tests: assertion mismatch"])
    )
    assert decision.quality_floor == "cheap"
    assert decision.action != "bailout"
    assert "same-floor-retry-with-gate-feedback" in decision.reasons


def test_failure_without_named_feedback_bails_out() -> None:
    decision = decide_route(_request(prior_failures=1))
    assert decision.action == "bailout"
    assert "failure-feedback-missing" in decision.reasons


@pytest.mark.parametrize("value", ["gate failed", [""], [1], None])
def test_failure_feedback_requires_nonempty_string_list(value: object) -> None:
    with pytest.raises(RoutingValidationError, match="list of non-empty strings"):
        decide_route(_request(failure_feedback=value))


@pytest.mark.parametrize("value", [0.9, 1.5, 2.0])
def test_fractional_prior_failures_is_rejected_not_truncated(value: float) -> None:
    """A float must never be truncated into a passing integer signal.

    Truncating 0.9 to 0 made the request validate, exit successfully, and route
    at the cheap floor with escalation omitted entirely.
    """
    with pytest.raises(RoutingValidationError, match="must be an integer"):
        decide_route(_request(prior_failures=value))


@pytest.mark.parametrize("value", ["5", "0", " 1"])
def test_numeric_strings_are_rejected(value: str) -> None:
    """The declared contract is an integer, not a coercible string."""
    with pytest.raises(RoutingValidationError, match="must be an integer"):
        decide_route(_request(prior_failures=value))


def test_boolean_prior_failures_is_rejected() -> None:
    with pytest.raises(RoutingValidationError, match="must be an integer"):
        decide_route(_request(prior_failures=True))


def test_negative_prior_failures_is_rejected() -> None:
    with pytest.raises(RoutingValidationError, match="must be non-negative"):
        decide_route(_request(prior_failures=-1))


@pytest.mark.parametrize(
    "field,value",
    [
        ("dependency_count", 1.5),
        ("volume", 2.5),
        ("expected_minutes", 0.5),
        ("context_tokens_estimate", 10.5),
    ],
)
def test_other_fractional_signals_are_rejected(field: str, value: float) -> None:
    """The same truncation applied to every integer signal on the request."""
    with pytest.raises(RoutingValidationError, match="must be an integer"):
        decide_route(_request(**{field: value}))


@pytest.mark.parametrize("field", ["max_parallel_workers", "deadline_seconds"])
def test_fractional_limits_are_rejected(field: str) -> None:
    payload = _request()
    payload["limits"] = {"max_parallel_workers": 1, field: 1.5}
    with pytest.raises(RoutingValidationError, match="must be an integer"):
        decide_route(payload)


def test_route_cli_rejects_fractional_prior_failures(tmp_path: Path) -> None:
    """Bind the fix at the boundary the reviewer actually reproduced.

    The reported defect was the route CLI exiting 0 and returning
    quality_floor='cheap' with 'monotonic-failure-escalation' omitted.  Asserting
    only on decide_route() would leave that exact surface unproven.
    """
    payload = _request(prior_failures=0.9)
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps(payload), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", "app.server.task_routing", str(request_file)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0, "the CLI must not exit 0 on a fractional signal"
    combined = completed.stdout + completed.stderr
    assert "must be an integer" in combined
    assert "cheap" not in combined
