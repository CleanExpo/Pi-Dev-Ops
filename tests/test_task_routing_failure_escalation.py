"""Focused regression tests for terminal comparable-failure escalation."""
from __future__ import annotations

import pytest

from app.server.task_routing import decide_route


def _request(*, task_shape: str, prior_failures: int) -> dict[str, object]:
    profiles = {
        "cheap": {"determinism": "high", "reasoning_depth": "shallow"},
        "mid": {"determinism": "medium", "reasoning_depth": "normal"},
        "top": {"determinism": "medium", "reasoning_depth": "deep"},
    }
    signals: dict[str, object] = {
        "ambiguity": "low",
        "scope": "bounded",
        "stakes": ["none"],
        "sensitivity": "public",
        "prior_failures": prior_failures,
        "failure_feedback": ["tests-python: comparable assertion failure"] if prior_failures else [],
        **profiles[task_shape],
    }
    return {
        "schema_version": "1.0",
        "request_id": f"failure-escalation-{task_shape}-{prior_failures}",
        "task": "retry a comparable failed route",
        "harness": "codex",
        "signals": signals,
        "limits": {"deadline_seconds": 900, "max_parallel_workers": 1},
    }


@pytest.mark.parametrize(
    ("task_shape", "prior_failures", "expected_floor", "expected_action"),
    [
        ("cheap", 0, "cheap", "delegate"),
        ("cheap", 1, "cheap", "delegate"),
        ("cheap", 2, "mid", "delegate"),
        ("cheap", 3, "top", "delegate"),
        ("cheap", 4, "top", "bailout"),
        ("mid", 0, "mid", "delegate"),
        ("mid", 1, "mid", "delegate"),
        ("mid", 2, "top", "delegate"),
        ("mid", 3, "top", "bailout"),
        ("top", 0, "top", "delegate"),
        ("top", 1, "top", "delegate"),
        ("top", 2, "top", "bailout"),
    ],
)
def test_comparable_failures_follow_the_terminal_escalation_chain(
    task_shape: str, prior_failures: int, expected_floor: str, expected_action: str
) -> None:
    decision = decide_route(_request(task_shape=task_shape, prior_failures=prior_failures))

    assert decision.quality_floor == expected_floor
    assert decision.action == expected_action
    assert ("monotonic-failure-escalation" in decision.reasons) is (prior_failures >= 2)
    assert ("same-floor-retry-with-gate-feedback" in decision.reasons) is (
        prior_failures == 1
    )
    assert ("failure-escalation-exhausted" in decision.reasons) is (
        expected_action == "bailout"
    )


def test_exhausted_top_route_has_terminal_non_dispatch_semantics() -> None:
    decision = decide_route(_request(task_shape="top", prior_failures=2))

    assert decision.action == "bailout"
    assert decision.execution["max_parallel_workers"] == 1
    assert decision.budget["reservation_required"] is False
    assert decision.fallback == ("top", "bailout")
    assert decision.confidence == 0.99
