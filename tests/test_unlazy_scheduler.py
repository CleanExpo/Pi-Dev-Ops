from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from swarm.unlazy_scheduler import (
    PlanValidationError,
    plan_template,
    ready_nodes,
    record_result,
    validate_plan,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "unlazy-gate-check.mjs"


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
                "worker_id": "worker-a",
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
                "worker_id": "worker-b",
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
                "worker_id": "worker-join",
                "gates": "gates/join.md",
                "state": "pending",
                "attempt": 0,
            },
        ],
    }


def verifying_plan():
    raw = valid_plan()
    raw["nodes"][1]["state"] = "verifying"
    return raw


def gate_receipt(*, passed: bool = True):
    return {
        "schema_version": "1.0",
        "mode": "run",
        "verified": True,
        "runner_version": "nexus-unlazy-gate-v3",
        "plan_id": "plan-1",
        "node_id": "1.1",
        "worker_id": "worker-a",
        "verifier_id": "verifier-1",
        "independent_verifier": True,
        "base_sha": "a" * 40,
        "candidate_sha": "b" * 40,
        "worktree_clean_before_run": True,
        "environment_digest": "sha256:" + "c" * 64,
        "relevant_input_digest": "sha256:" + "d" * 64,
        "gate_files": [{"path": "gates/a.md", "digest": "sha256:" + "e" * 64}],
        "summary": {
            "passed": 1 if passed else 0,
            "failed": 0 if passed else 1,
            "pending": 0,
            "abandoned": 0,
            "runner_errors": 0,
        },
    }


def _build_verified_case(root: Path, *, passing: bool, check: str | None = None):
    (root / "gates").mkdir(parents=True)
    (root / "gates" / "a.md").write_text(
        """- [ ] G1: leaf gate
  CHECK: %s
  EXIT: 0
  EXPECT: READY
  EVIDENCE: pending
""" % (check or f"node -e \"console.log('READY'); process.exit({0 if passing else 7})\"")
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "add", "--all"], cwd=root, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Unlazy Test", "-c", "user.email=unlazy@example.invalid",
            "commit", "-q", "-m", "fixture",
        ],
        cwd=root,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, text=True, capture_output=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", head], cwd=root, check=True,
    )
    result = subprocess.run(
        [
            "node", str(CHECKER), "--json",
            "--plan-id", "plan-1", "--node-id", "1.1",
            "--worker-id", "worker-a", "--verifier-id", "unlazy-scheduler-trusted-replay-v1",
            "--relevant-input", "gates/a.md", "gates/a.md",
        ],
        cwd=root,
        text=True,
        capture_output=True,
    )
    assert result.returncode == (0 if passing else 1), result.stdout + result.stderr
    raw = valid_plan()
    raw["base_sha"] = head
    raw["worktree"] = str(root)
    raw["nodes"][1]["state"] = "verifying"
    return raw, json.loads(result.stdout)


@pytest.fixture(scope="module")
def verified_case(tmp_path_factory):
    return _build_verified_case(tmp_path_factory.mktemp("verified-case"), passing=True)


@pytest.fixture(scope="module")
def failed_case(tmp_path_factory):
    return _build_verified_case(tmp_path_factory.mktemp("failed-case"), passing=False)


def case_copy(case):
    raw, receipt = case
    return copy.deepcopy(raw), copy.deepcopy(receipt)


def test_lint_accepts_acyclic_disjoint_plan():
    plan = validate_plan(valid_plan())
    assert plan.effective_depth == 3
    assert len(plan.nodes) == 4


def test_rolling_ready_fills_cap_with_disjoint_leaves():
    assert [node.id for node in ready_nodes(valid_plan())] == ["1.1", "1.2"]


def test_out_of_order_return_unlocks_new_leaf_immediately(verified_case):
    raw, receipt = case_copy(verified_case)
    updated = record_result(
        raw, "1.1", passed=True, changed_paths=["src/a.py"],
        verification_receipt=receipt,
    )
    assert [node.id for node in ready_nodes(updated, active_ids=["1.2"])] == ["1.3"]


def test_blocked_dependency_does_not_unlock_dependant(failed_case):
    raw, receipt = case_copy(failed_case)
    updated = record_result(
        raw, "1.1", passed=False, changed_paths=["src/a.py"],
        verification_receipt=receipt,
    )
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


def test_out_of_contract_return_trips_boundary(verified_case):
    raw, receipt = case_copy(verified_case)
    with pytest.raises(PlanValidationError, match="outside ownership"):
        record_result(
            raw, "1.1", passed=True, changed_paths=["src/b.py"],
            verification_receipt=receipt,
        )


def test_terminal_result_requires_verifying_state_and_strict_boolean():
    with pytest.raises(PlanValidationError, match="must be verifying"):
        record_result(
            valid_plan(), "1.1", passed=True, changed_paths=["src/a.py"],
            verification_receipt=gate_receipt(),
        )
    with pytest.raises(PlanValidationError, match="passed must be a boolean"):
        record_result(
            verifying_plan(),
            "1.1",
            passed="false",  # type: ignore[arg-type]
            changed_paths=["src/a.py"],
            verification_receipt=gate_receipt(),
        )


def test_terminal_result_requires_bound_independent_gate_receipt():
    with pytest.raises(PlanValidationError, match="verification receipt is required"):
        record_result(verifying_plan(), "1.1", passed=True, changed_paths=[])


def test_direct_terminal_state_without_stored_receipt_is_rejected():
    raw = valid_plan()
    raw["nodes"][1]["state"] = "passed"
    with pytest.raises(PlanValidationError, match="verification receipt is required"):
        ready_nodes(raw)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("plan_id", "other-plan", "plan_id"),
        ("node_id", "1.2", "node_id"),
        ("worker_id", "worker-b", "worker_id"),
        ("verifier_id", "", "verifier_id"),
        ("verifier_id", "worker-a", "independent verifier"),
        ("base_sha", "c" * 40, "base_sha"),
        ("candidate_sha", "not-a-sha", "candidate_sha"),
        ("candidate_sha", "c" * 40, "actual worktree HEAD"),
        ("runner_version", "nexus-unlazy-gate-v1", "not trusted"),
        ("verified", False, "verified run"),
        ("mode", "status", "verified run"),
        ("worktree_clean_before_run", False, "clean worktree"),
        ("relevant_input_digest", "", "relevant_input_digest"),
        ("relevant_input_digest", "sha256:" + "f" * 64, "runtime content"),
        ("environment_digest", "sha256:" + "f" * 64, "runtime environment"),
    ],
)
def test_terminal_result_rejects_mutated_receipt_fields(
    verified_case, field, value, match,
):
    raw, receipt = case_copy(verified_case)
    receipt[field] = value
    with pytest.raises(PlanValidationError, match=match):
        record_result(
            raw, "1.1", passed=True, changed_paths=[],
            verification_receipt=receipt,
        )


def test_pass_requires_node_gate_digest_and_strict_zero_counts(verified_case):
    raw, missing_gate = case_copy(verified_case)
    missing_gate["gate_files"] = [{"path": "gates/other.md", "digest": "sha256:" + "e" * 64}]
    with pytest.raises(PlanValidationError, match="node gate file"):
        record_result(
            raw, "1.1", passed=True, changed_paths=[],
            verification_receipt=missing_gate,
        )
    for count in ("failed", "pending", "abandoned", "runner_errors"):
        raw, receipt = case_copy(verified_case)
        receipt["summary"][count] = 1
        with pytest.raises(PlanValidationError, match="strict gate counts"):
            record_result(
                raw, "1.1", passed=True, changed_paths=[],
                verification_receipt=receipt,
            )


def test_fully_shaped_fabricated_receipt_cannot_unlock_dependants(verified_case):
    raw, receipt = case_copy(verified_case)
    receipt["candidate_sha"] = "c" * 40
    receipt["verifier_id"] = "worker-a"
    receipt["gate_files"][0]["digest"] = "sha256:" + "d" * 64
    receipt["relevant_inputs"][0]["digest"] = "sha256:" + "e" * 64
    receipt["relevant_input_digest"] = "sha256:" + "f" * 64
    with pytest.raises(PlanValidationError, match="independent verifier|actual worktree HEAD"):
        record_result(
            raw, "1.1", passed=True, changed_paths=[], verification_receipt=receipt,
        )
    assert [node.id for node in ready_nodes(valid_plan())] == ["1.1", "1.2"]


def test_fabricated_execution_evidence_cannot_unlock_dependants(verified_case):
    raw, receipt = case_copy(verified_case)
    receipt["gates"][0]["stdoutDigest"] = "sha256:" + "f" * 64
    with pytest.raises(PlanValidationError, match="does not reproduce"):
        record_result(
            raw, "1.1", passed=True, changed_paths=[], verification_receipt=receipt,
        )


def test_receipt_is_rejected_when_relevant_input_changes_after_issuance(tmp_path):
    raw, receipt = _build_verified_case(tmp_path / "changed-after-receipt", passing=True)
    (Path(raw["worktree"]) / "gates" / "a.md").write_text("changed after receipt\n")
    with pytest.raises(PlanValidationError, match="actually clean|runtime content"):
        record_result(
            raw, "1.1", passed=True, changed_paths=[], verification_receipt=receipt,
        )


def test_validate_ready_and_lint_do_not_execute_terminal_gate(tmp_path):
    marker = tmp_path / "validation-marker"
    command = (
        f"node -e \"require('node:fs').appendFileSync('{marker}', 'x'); "
        "console.log('READY')\""
    )
    raw, receipt = _build_verified_case(
        tmp_path / "pure-validation", passing=True, check=command,
    )
    marker.unlink()
    raw["nodes"][1]["state"] = "passed"
    receipt["verification_authority"] = "scheduler-controlled-replay-v1"
    raw["nodes"][1]["verification_receipt"] = receipt
    validate_plan(raw)
    ready_nodes(raw)
    plan_path = tmp_path / "terminal-plan.json"
    plan_path.write_text(json.dumps(raw))
    for action in ("lint", "ready"):
        result = subprocess.run(
            ["python", str(REPO_ROOT / "scripts" / "unlazy_plan.py"), action, str(plan_path)],
            text=True, capture_output=True,
        )
        assert result.returncode == 0, result.stderr
    assert not marker.exists()


def test_terminal_transition_replays_gate_exactly_once(tmp_path):
    marker = tmp_path / "transition-marker"
    command = (
        f"node -e \"require('node:fs').appendFileSync('{marker}', 'x'); "
        "console.log('READY')\""
    )
    raw, receipt = _build_verified_case(
        tmp_path / "single-replay", passing=True, check=command,
    )
    marker.unlink()
    updated = record_result(
        raw, "1.1", passed=True, changed_paths=[], verification_receipt=receipt,
    )
    assert marker.read_text() == "x"
    stored = updated["nodes"][1]["verification_receipt"]
    assert stored["verifier_id"] == "unlazy-scheduler-trusted-replay-v1"
    assert stored["verification_authority"] == "scheduler-controlled-replay-v1"


def test_forged_timing_evidence_is_rejected(verified_case):
    raw, receipt = case_copy(verified_case)
    receipt["started_at"] = "2099-01-01T00:00:00.000Z"
    receipt["finished_at"] = "2099-01-01T00:00:01.000Z"
    receipt["gates"][0]["elapsedMs"] = 999_999_999
    with pytest.raises(PlanValidationError, match="timing|future|elapsed"):
        record_result(raw, "1.1", passed=True, changed_paths=[], verification_receipt=receipt)


def test_same_actor_verifier_alias_is_rejected(tmp_path):
    raw, _ = _build_verified_case(tmp_path / "alias-verifier", passing=True)
    result = subprocess.run(
        [
            "node", str(CHECKER), "--json", "--plan-id", "plan-1", "--node-id", "1.1",
            "--worker-id", "worker-a", "--verifier-id", "same-actor-alias",
            "--relevant-input", "gates/a.md", "gates/a.md",
        ],
        cwd=raw["worktree"], text=True, capture_output=True, check=True,
    )
    with pytest.raises(PlanValidationError, match="trusted scheduler verifier"):
        record_result(
            raw, "1.1", passed=True, changed_paths=[],
            verification_receipt=json.loads(result.stdout),
        )


def test_ownership_paths_are_canonical_for_result_boundary(verified_case):
    raw, receipt = case_copy(verified_case)
    raw["nodes"][1]["owns"] = ["./src/a.py"]
    plan = validate_plan(raw)
    assert plan.by_id["1.1"].owns == ("src/a.py",)
    updated = record_result(
        raw, "1.1", passed=True, changed_paths=["src/a.py"],
        verification_receipt=receipt,
    )
    assert updated["nodes"][1]["state"] == "passed"


def test_directory_ownership_accepts_children_but_not_parent_or_sibling(verified_case):
    raw, receipt = case_copy(verified_case)
    raw["nodes"][1]["owns"] = ["src/features"]
    updated = record_result(
        raw,
        "1.1",
        passed=True,
        changed_paths=["src/features/a.py", "src/features/nested/b.py"],
        verification_receipt=receipt,
    )
    assert updated["nodes"][1]["state"] == "passed"
    for outside in ("src", "src/feature-other/a.py"):
        with pytest.raises(PlanValidationError, match="outside ownership"):
            raw, receipt = case_copy(verified_case)
            raw["nodes"][1]["owns"] = ["src/features"]
            record_result(
                raw, "1.1", passed=True, changed_paths=[outside],
                verification_receipt=receipt,
            )


def test_requested_depth_above_seven_is_truthfully_reduced():
    raw = plan_template("large project", 9)
    assert raw["requested_depth"] == 9
    assert raw["effective_depth"] == 7
    assert raw["adjustment_reason"] == "capped-at-seven"
    with pytest.raises(PlanValidationError, match="route_ref"):
        validate_plan(raw)
