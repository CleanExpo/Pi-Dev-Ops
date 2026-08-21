from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def routing_request():
    return {
        "schema_version": "1.0",
        "request_id": "cli-example",
        "task": "Check three disjoint project surfaces",
        "harness": "codex",
        "signals": {
            "determinism": "medium",
            "ambiguity": "low",
            "scope": "multi-file",
            "dependency_count": 0,
            "reasoning_depth": "normal",
            "stakes": ["none"],
            "volume": 3,
            "expected_minutes": 45,
            "context_tokens_estimate": 6000,
            "modalities": ["text", "code"],
            "required_tools": ["read", "test"],
            "sensitivity": "internal",
            "prior_failures": 0,
            "ownership_disjoint": True,
        },
        "limits": {
            "max_cost_usd": 0.2,
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


def valid_plan():
    return {
        "schema_version": "1.0",
        "plan_id": "cli-plan",
        "task": "Two independent checks",
        "requested_depth": 3,
        "effective_depth": 3,
        "adjustment_reason": "",
        "base_sha": "b" * 40,
        "worktree": str(REPO_ROOT),
        "max_parallel_workers": 2,
        "nodes": [
            {
                "id": "1",
                "type": "root",
                "purpose": "integrate",
                "owns": [],
                "needs": ["1.1", "1.2"],
                "exports": [],
                "route_ref": "root-route",
                "gates": "gates/root.md",
                "state": "pending",
                "attempt": 0,
            },
            {
                "id": "1.1",
                "type": "leaf",
                "purpose": "first",
                "owns": ["src/one.py"],
                "needs": [],
                "exports": [],
                "route_ref": "route-one",
                "gates": "gates/one.md",
                "state": "pending",
                "attempt": 0,
            },
            {
                "id": "1.2",
                "type": "leaf",
                "purpose": "second",
                "owns": ["src/two.py"],
                "needs": [],
                "exports": [],
                "route_ref": "route-two",
                "gates": "gates/two.md",
                "state": "pending",
                "attempt": 0,
            },
        ],
    }


def test_documented_model_router_stdin_invocation():
    result = subprocess.run(
        [sys.executable, "-m", "app.server.task_routing"],
        cwd=REPO_ROOT,
        input=json.dumps(routing_request()),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["action"] == "fanout"


def test_model_router_cli_rejects_string_boolean_before_policy_evaluation():
    raw = routing_request()
    raw["signals"]["ownership_disjoint"] = "false"
    raw["capabilities"]["supports_parallel"] = "false"
    result = subprocess.run(
        [sys.executable, "-m", "app.server.task_routing"],
        cwd=REPO_ROOT,
        input=json.dumps(raw),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    error = json.loads(result.stderr)
    assert error["status"] == "invalid_request"
    assert "must be a boolean" in error["error"]


def test_model_router_cli_rejects_non_finite_budget_before_serializing():
    raw = routing_request()
    raw["limits"]["max_cost_usd"] = float("nan")
    result = subprocess.run(
        [sys.executable, "-m", "app.server.task_routing"],
        cwd=REPO_ROOT,
        input=json.dumps(raw),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    error = json.loads(result.stderr)
    assert error["status"] == "invalid_request"
    assert "must be finite" in error["error"]


def test_documented_unlazy_plan_commands_work_without_pythonpath(tmp_path):
    help_result = subprocess.run(
        [sys.executable, "scripts/unlazy_plan.py", "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert help_result.returncode == 0, help_result.stderr

    template = subprocess.run(
        [
            sys.executable,
            "scripts/unlazy_plan.py",
            "template",
            "Build a project slice",
            "--tree",
            "9",
            "--max-workers",
            "3",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert template.returncode == 0, template.stderr
    assert json.loads(template.stdout)["effective_depth"] == 7

    plan_path = tmp_path / "PLAN.json"
    plan_path.write_text(json.dumps(valid_plan()))
    lint = subprocess.run(
        [sys.executable, "scripts/unlazy_plan.py", "lint", str(plan_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert lint.returncode == 0, lint.stderr
    assert json.loads(lint.stdout)["status"] == "valid"

    ready = subprocess.run(
        [sys.executable, "scripts/unlazy_plan.py", "ready", str(plan_path), "--active", "1.1"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert ready.returncode == 0, ready.stderr
    assert json.loads(ready.stdout)["ready"] == ["1.2"]
