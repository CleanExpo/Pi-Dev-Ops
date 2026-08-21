from __future__ import annotations

import json

import pytest

from app.server.routing_schema import RoutingValidationError
from app.server.task_routing import decide_route


def request(**signal_overrides):
    signals = {
        "determinism": "medium",
        "ambiguity": "medium",
        "scope": "bounded",
        "dependency_count": 0,
        "reasoning_depth": "normal",
        "stakes": ["none"],
        "volume": 1,
        "expected_minutes": 30,
        "context_tokens_estimate": 4000,
        "modalities": ["text", "code"],
        "required_tools": ["read", "edit", "test"],
        "sensitivity": "internal",
        "prior_failures": 0,
        "ownership_disjoint": False,
    }
    signals.update(signal_overrides)
    return {
        "schema_version": "1.0",
        "request_id": "req-1",
        "task": "Implement one bounded change",
        "harness": "codex",
        "signals": signals,
        "limits": {
            "max_cost_usd": 0.25,
            "max_quota_units": None,
            "deadline_seconds": 900,
            "max_parallel_workers": 3,
        },
        "capabilities": {
            "local_quality_floors": ["cheap", "mid", "top"],
            "supports_parallel": True,
            "supports_model_override": True,
            "supports_cancellation": True,
        },
    }


def test_route_is_deterministic_and_provider_neutral():
    first = decide_route(request())
    second = decide_route(request())
    assert first.to_json() == second.to_json()
    output = first.to_dict()
    assert output["route_id"] == second.route_id
    assert "provider" not in output
    assert "model_id" not in output


def test_confidential_high_stakes_without_local_top_fails_closed():
    raw = request(sensitivity="client", stakes=["payment"], scope="subsystem")
    raw["capabilities"]["local_quality_floors"] = ["cheap", "mid"]
    decision = decide_route(raw)
    assert decision.action == "bailout"
    assert decision.execution_location == "local_only"
    assert decision.quality_floor == "top"
    assert decision.verifier["quality_floor"] == "top"
    assert "no-local-capability-at-required-floor" in decision.reasons


def test_confidential_high_stakes_routes_only_when_local_top_exists():
    decision = decide_route(request(sensitivity="confidential", stakes=["security"]))
    assert decision.action == "delegate"
    assert decision.execution_location == "local_only"
    assert decision.quality_floor == "top"
    assert decision.worker_role == "senior"


def test_local_top_capability_can_satisfy_lower_floor():
    raw = request(sensitivity="confidential")
    raw["capabilities"]["local_quality_floors"] = ["top"]
    decision = decide_route(raw)
    assert decision.action == "delegate"
    assert decision.quality_floor == "mid"


def test_trivial_deterministic_work_stays_inline():
    decision = decide_route(
        request(
            determinism="high",
            ambiguity="low",
            scope="inline",
            reasoning_depth="shallow",
            expected_minutes=5,
        )
    )
    assert decision.action == "inline"
    assert decision.task_class == "mechanical"
    assert decision.quality_floor == "cheap"


def test_disjoint_multi_file_work_fans_out_to_cap():
    decision = decide_route(
        request(scope="multi-file", volume=4, dependency_count=2, ownership_disjoint=True)
    )
    assert decision.action == "fanout"
    assert decision.execution["max_parallel_workers"] == 3


def test_harness_without_parallelism_degrades_to_delegate():
    raw = request(scope="multi-file", volume=4, ownership_disjoint=True)
    raw["capabilities"]["supports_parallel"] = False
    decision = decide_route(raw)
    assert decision.action == "delegate"
    assert decision.execution["max_parallel_workers"] == 1
    assert "harness-parallelism-unavailable" in decision.reasons


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("max_cost_usd", 0.0, "zero-cost-budget"),
        ("max_quota_units", 0.0, "zero-quota-budget"),
        ("deadline_seconds", 0, "zero-deadline"),
    ],
)
def test_delegated_work_fails_closed_on_zero_execution_limit(field, value, reason):
    raw = request(scope="multi-file", volume=4, ownership_disjoint=True)
    raw["limits"][field] = value
    decision = decide_route(raw)
    assert decision.action == "bailout"
    assert decision.execution["max_parallel_workers"] == 1
    assert decision.budget["reservation_required"] is False
    assert reason in decision.reasons


def test_timed_fanout_without_cancellation_degrades_to_one_worker():
    raw = request(scope="multi-file", volume=4, ownership_disjoint=True)
    raw["capabilities"]["supports_cancellation"] = False
    decision = decide_route(raw)
    assert decision.action == "delegate"
    assert decision.execution["max_parallel_workers"] == 1
    assert "harness-cancellation-unavailable" in decision.reasons


def test_all_zero_limits_and_no_cancellation_never_fan_out():
    raw = request(scope="multi-file", volume=4, ownership_disjoint=True)
    raw["limits"].update(
        {"max_cost_usd": 0.0, "max_quota_units": 0.0, "deadline_seconds": 0}
    )
    raw["capabilities"]["supports_cancellation"] = False
    decision = decide_route(raw)
    assert decision.action == "bailout"
    assert decision.execution["max_parallel_workers"] == 1
    assert decision.budget["reservation_required"] is False


def test_failure_escalation_never_downgrades():
    decision = decide_route(
        request(determinism="high", reasoning_depth="shallow", prior_failures=2)
    )
    assert decision.quality_floor == "top"
    assert decision.fallback == ("top", "bailout")


def test_high_stakes_failure_escalation_preserves_xhigh_effort():
    decision = decide_route(request(stakes=["security"], prior_failures=2))
    assert decision.quality_floor == "top"
    assert decision.reasoning_effort == "xhigh"
    assert "monotonic-failure-escalation" in decision.reasons


def test_invalid_bool_integer_is_rejected():
    raw = request()
    raw["signals"]["dependency_count"] = True
    with pytest.raises(RoutingValidationError, match="must be an integer"):
        decide_route(raw)


@pytest.mark.parametrize("invalid", ["false", 0, None, [], {}])
@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("signals", "ownership_disjoint"),
        ("capabilities", "supports_parallel"),
        ("capabilities", "supports_model_override"),
        ("capabilities", "supports_cancellation"),
    ],
)
def test_boolean_fields_reject_non_json_booleans(section, field, invalid):
    raw = request()
    raw[section][field] = invalid
    with pytest.raises(RoutingValidationError, match=f"{section}.{field} must be a boolean"):
        decide_route(raw)


def test_decision_json_round_trips():
    payload = json.loads(decide_route(request()).to_json())
    assert payload["schema_version"] == "1.0"
    assert payload["policy_version"].startswith("sha256:")
