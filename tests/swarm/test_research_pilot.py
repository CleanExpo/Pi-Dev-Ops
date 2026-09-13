"""RA-7522: read-only research swarm pilot contract.

Validators reject every listed bad case. The dry-run sample completes
without dispatching an agent or mutating a repository, Linear, CRM, or
production system.
"""

from __future__ import annotations

import copy
import subprocess
import sys
import urllib.request

import pytest

from swarm.research_pilot import (
    DESTRUCTIVE_TOOLS,
    MC_STATES,
    STOP_RULES,
    WRITE_LANE_ADMITTED,
    WRITE_LANE_GATE,
    PilotContractError,
    dry_run_pilot,
    sample_pilot_request,
    validate_pilot,
)

MUTATION_MODULES = (
    "swarm.linear_tools",
    "swarm.github_tools",
    "swarm.research_provider",
    "swarm.pilot.dispatcher",
    "swarm.orchestrator",
)


def _request(**overrides: object) -> dict:
    payload = copy.deepcopy(sample_pilot_request())
    payload.update(overrides)
    return payload


def _expect_reason(reason: str, **overrides: object) -> None:
    with pytest.raises(PilotContractError) as caught:
        validate_pilot(_request(**overrides))
    assert caught.value.reason == reason


def test_sample_request_is_a_positive_control() -> None:
    plan = validate_pilot(sample_pilot_request())
    assert len(plan.nodes) == 2
    assert plan.capabilities.mutations is False
    assert plan.capabilities.supports_cancellation is True
    assert plan.usage.status == "known"


def test_overlapping_ownership_is_rejected() -> None:
    nodes = sample_pilot_request()["nodes"]
    nodes[1]["owns"] = ["swarm/flow_engine.py"]
    _expect_reason("overlapping-ownership", nodes=nodes)


def test_parent_child_ownership_is_rejected() -> None:
    nodes = sample_pilot_request()["nodes"]
    nodes[0]["owns"] = ["swarm"]
    nodes[1]["owns"] = ["swarm/closed_loop.py"]
    _expect_reason("overlapping-ownership", nodes=nodes)


def test_missing_token_cap_is_rejected() -> None:
    _expect_reason("missing-caps", budget={"max_seconds": 120})


def test_zero_time_cap_is_rejected() -> None:
    _expect_reason("missing-caps", budget={"max_tokens": 8000, "max_seconds": 0})


def test_api_credit_budget_is_rejected() -> None:
    _expect_reason(
        "missing-caps",
        budget={"max_tokens": 8000, "max_seconds": 120, "max_cost_usd": 1.5},
    )


def test_implicit_mutations_capability_is_rejected() -> None:
    _expect_reason(
        "missing-caps",
        capabilities={"supports_cancellation": True, "write_lane": False},
    )


def test_unknown_usage_is_rejected() -> None:
    _expect_reason("unknown-usage", usage={"status": "unknown"})


def test_missing_usage_metrics_are_unknown_not_zero() -> None:
    _expect_reason("unknown-usage", usage={"status": "known"})


def test_missing_cancellation_is_rejected() -> None:
    _expect_reason(
        "missing-cancellation",
        capabilities={"mutations": False, "write_lane": False},
    )


def test_production_destructive_tools_are_rejected() -> None:
    nodes = sample_pilot_request()["nodes"]
    forbidden = next(iter(DESTRUCTIVE_TOOLS))
    nodes[0]["tools"] = ["read", forbidden]
    _expect_reason("production-destructive-tools", nodes=nodes)


def test_unknown_tool_is_rejected_as_production_risk() -> None:
    nodes = sample_pilot_request()["nodes"]
    nodes[0]["tools"] = ["read", "linear.create_issue"]
    _expect_reason("production-destructive-tools", nodes=nodes)


def test_mismatched_evidence_digest_is_rejected() -> None:
    evidence = sample_pilot_request()["evidence"]
    evidence["digest"] = "0" * 64
    _expect_reason("stale-or-mismatched-evidence", evidence=evidence)


def test_mismatched_source_state_is_rejected() -> None:
    evidence = sample_pilot_request()["evidence"]
    evidence["source_state"] = "fixture:stale"
    _expect_reason("stale-or-mismatched-evidence", evidence=evidence)


def test_missing_evidence_is_rejected() -> None:
    _expect_reason("stale-or-mismatched-evidence", evidence=None)


def test_write_lane_is_rejected_even_with_a_forged_approval() -> None:
    with pytest.raises(PilotContractError) as caught:
        validate_pilot(
            _request(
                capabilities={
                    "mutations": False,
                    "supports_cancellation": True,
                    "write_lane": True,
                    "board_approval": "forged",
                }
            )
        )
    assert caught.value.reason == "write-lane-requires-board-approval"
    assert WRITE_LANE_ADMITTED is False
    assert "board approval" in WRITE_LANE_GATE


def test_one_node_is_rejected() -> None:
    _expect_reason("node-count-out-of-range", nodes=sample_pilot_request()["nodes"][:1])


def test_dry_run_sample_completes_without_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run must not call a live system")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    before = set(sys.modules)
    receipt = dry_run_pilot(sample_pilot_request())
    imported = set(sys.modules) - before
    assert not imported.intersection(MUTATION_MODULES)
    assert receipt.dispatched is False
    assert receipt.mutated == ()
    assert receipt.mutations is False
    assert receipt.write_lane_admitted is False
    assert receipt.billing == "max_plan_only"
    assert receipt.source_state == "fixture:ra-7522:v1"
    assert receipt.usage.status == "known"
    assert receipt.usage.tokens == 0
    assert receipt.verifier_result == "projected-pass"
    assert receipt.handoff_id == "handoff-ra-7522-sample"
    assert receipt.final_states == {"r1": "passed", "r2": "passed"}
    assert [row["phase"] for row in receipt.projected_states] == [
        "pending",
        "ready",
        "running",
        "verifying",
        "passed",
    ]
    for row in receipt.projected_states:
        assert set(row["nodes"].values()) <= set(MC_STATES)


def test_budget_and_context_stop_rules_are_visible() -> None:
    receipt = dry_run_pilot(sample_pilot_request())
    rules = receipt.operator_stop_rules
    assert receipt.stop_rules == STOP_RULES
    assert rules["max_tokens"] == 8000
    assert rules["max_seconds"] == 120
    assert rules["reserve_stop_tokens"] == 6400
    assert rules["reserve_stop_seconds"] == 96
    assert rules["unknown_usage_blocks"] is True
    assert rules["mutations"] is False
    assert rules["write_lane_admitted"] is False
    assert "mutations=false" in " ".join(receipt.stop_rules)
    assert "board approval" in " ".join(receipt.stop_rules)
