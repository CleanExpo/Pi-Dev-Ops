from __future__ import annotations

import pytest

from swarm.unlazy_scheduler import (
    PlanValidationError,
    plan_template,
    ready_nodes,
    record_result,
    validate_plan,
)


def valid_plan():
    return {
        "schema_version": "1.0",
        "plan_id": "plan-1",
        "task": "Build independent components then integrate",
        "requested_depth": 4,
        "effective_depth": 3,
        "adjustment_reason": "natural leaves reached at depth three",
        "base_sha": "a" * 40,
        "worktree": "/Volumes/Storage Unit/example",
        "max_parallel_workers": 2,
        "nodes": [
            {
                "id": "1",
                "type": "root",
                "purpose": "integrate",
                "owns": ["integration/result.json"],
                "needs": ["1.2", "1.3"],
                "exports": [],
                "route_ref": "route-root",
                "gates": "gates/root.md",
                "state": "pending",
                "attempt": 0,
            },
            {
                "id": "1.1",
                "type": "leaf",
                "purpose": "component a",
                "owns": ["src/a.py", "tests/test_a.py"],
                "needs": [],
                "exports": ["A"],
                "route_ref": "route-a",
                "gates": "gates/a.md",
                "state": "pending",
                "attempt": 0,
            },
            {
                "id": "1.2",
                "type": "leaf",
                "purpose": "component b",
                "owns": ["src/b.py", "tests/test_b.py"],
                "needs": [],
                "exports": ["B"],
                "route_ref": "route-b",
                "gates": "gates/b.md",
                "state": "pending",
                "attempt": 0,
            },
            {
                "id": "1.3",
                "type": "leaf",
                "purpose": "join outputs",
                "owns": ["src/join.py", "tests/test_join.py"],
                "needs": ["1.1"],
                "exports": [],
                "route_ref": "route-join",
                "gates": "gates/join.md",
                "state": "pending",
                "attempt": 0,
            },
        ],
    }


def test_lint_accepts_acyclic_disjoint_plan():
    plan = validate_plan(valid_plan())
    assert plan.effective_depth == 3
    assert len(plan.nodes) == 4


def test_rolling_ready_fills_cap_with_disjoint_leaves():
    assert [node.id for node in ready_nodes(valid_plan())] == ["1.1", "1.2"]


def test_out_of_order_return_unlocks_new_leaf_immediately():
    updated = record_result(valid_plan(), "1.1", passed=True, changed_paths=["src/a.py"])
    assert [node.id for node in ready_nodes(updated, active_ids=["1.2"])] == ["1.3"]


def test_blocked_dependency_does_not_unlock_dependant():
    updated = record_result(valid_plan(), "1.1", passed=False, changed_paths=["src/a.py"])
    assert "1.3" not in [node.id for node in ready_nodes(updated)]


def test_ownership_collision_fails_before_dispatch():
    raw = valid_plan()
    raw["nodes"][2]["owns"] = ["src/a.py"]
    with pytest.raises(PlanValidationError, match="ownership collision"):
        validate_plan(raw)


def test_parent_child_ownership_collision_is_rejected():
    raw = valid_plan()
    raw["nodes"][2]["owns"] = ["src/a.py/generated"]
    with pytest.raises(PlanValidationError, match="ownership collision"):
        validate_plan(raw)


def test_cycle_is_rejected():
    raw = valid_plan()
    raw["nodes"][1]["needs"] = ["1.3"]
    with pytest.raises(PlanValidationError, match="cycle"):
        validate_plan(raw)


def test_unreachable_node_is_rejected():
    raw = valid_plan()
    raw["nodes"][0]["needs"] = ["1.3"]
    with pytest.raises(PlanValidationError, match="not reachable"):
        validate_plan(raw)


def test_unsafe_or_wildcard_ownership_is_rejected():
    for unsafe in ("../secret", "/absolute/path", "src/**/*.py"):
        raw = valid_plan()
        raw["nodes"][1]["owns"] = [unsafe]
        with pytest.raises(PlanValidationError, match="unsafe|wildcard"):
            validate_plan(raw)


def test_out_of_contract_return_trips_boundary():
    with pytest.raises(PlanValidationError, match="outside ownership"):
        record_result(valid_plan(), "1.1", passed=True, changed_paths=["src/b.py"])


def test_requested_depth_above_seven_is_truthfully_reduced():
    raw = plan_template("large project", 9)
    assert raw["requested_depth"] == 9
    assert raw["effective_depth"] == 7
    assert raw["adjustment_reason"] == "capped-at-seven"
    with pytest.raises(PlanValidationError, match="route_ref"):
        validate_plan(raw)
