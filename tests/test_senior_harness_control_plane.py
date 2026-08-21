from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "senior-harness" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from control_plane import ControlPlaneError, authorize_event, derive_operation  # noqa: E402
from setup_driver import admit_startup, build_setup_contract  # noqa: E402


TEST_KEY = "senior-harness-control-plane-test-key-at-least-32-bytes"


@pytest.fixture(autouse=True)
def control_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_CONTROL_HMAC_KEY", TEST_KEY)
    monkeypatch.setenv("UNLAZY_RECEIPT_HMAC_KEY", "unlazy-control-plane-test-key-at-least-32-bytes")
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state-root"))


def _startup() -> dict:
    return admit_startup(build_setup_contract("Build independent components then integrate", REPO_ROOT, surface="codex"))


def _plan(receipt: dict) -> dict:
    repository = receipt["setup_contract"]["repository"]
    return {
        "schema_version": "1.0", "plan_id": "control-plan", "task": receipt["setup_contract"]["literal_objective"],
        "requested_depth": 3, "effective_depth": 3, "adjustment_reason": "", "base_sha": repository["head_sha"],
        "worktree": repository["worktree"], "max_parallel_workers": 2,
        "nodes": [
            {"id": "1", "type": "root", "purpose": "integrate", "owns": [], "needs": ["1.1", "1.2"], "exports": [], "route_ref": "", "gates": "gates/root.md", "state": "pending", "attempt": 0},
            {"id": "1.1", "type": "leaf", "purpose": "a", "owns": ["control/a.py"], "needs": [], "exports": [], "route_ref": "route-a", "worker_id": "worker-a", "gates": "gates/a.md", "state": "pending", "attempt": 0},
            {"id": "1.2", "type": "leaf", "purpose": "b", "owns": ["control/b.py"], "needs": [], "exports": [], "route_ref": "route-b", "worker_id": "worker-b", "gates": "gates/b.md", "state": "pending", "attempt": 0},
        ],
    }


def _route(receipt: dict) -> dict:
    route = copy.deepcopy(receipt["setup_contract"]["routing_request"])
    route["signals"]["ownership_disjoint"] = True
    route["capabilities"]["supports_parallel"] = True
    route["capabilities"]["supports_model_override"] = True
    route["capabilities"]["supports_cancellation"] = True
    # Recalculate a receipt with the fanout route; a route modification after
    # admission must not be permitted by the controller.
    contract = copy.deepcopy(receipt["setup_contract"])
    contract["routing_request"] = route
    from app.server.task_routing import decide_route
    from senior_harness import digest
    contract["route_decision"] = decide_route(route).to_dict()
    unsigned = dict(contract)
    unsigned.pop("setup_contract_digest")
    contract["setup_contract_digest"] = digest(unsigned)
    rebuilt = {"schema_version": "1.0", "stage": "startup-admitted", "setup_contract": contract,
               "driver_digest": receipt["driver_digest"], "admission": receipt["admission"]}
    rebuilt["receipt_integrity_digest"] = digest(rebuilt)
    return rebuilt


def test_derives_only_closed_actual_host_operations() -> None:
    assert derive_operation({"tool_name": "senior-harness.dispatch", "tool_input": {}})[0] == "dispatch"
    with pytest.raises(ControlPlaneError, match="not an admitted"):
        derive_operation({"tool_name": "shell", "tool_input": {"operation": "dispatch"}})
    with pytest.raises(ControlPlaneError, match="differs"):
        derive_operation({"tool_name": "wait", "tool_input": {"operation": "delivery"}})


def test_fanout_denies_root_shell_edit_and_analysis(tmp_path: Path) -> None:
    receipt = _route(_startup())
    plan = _plan(receipt)
    route = receipt["setup_contract"]["routing_request"]
    for name in ("shell", "edit", "analysis", "delivery"):
        with pytest.raises(ControlPlaneError, match="not an admitted"):
            authorize_event(receipt, plan, route, {"tool_name": name, "tool_input": {}}, state_path=Path(os.environ["SENIOR_HARNESS_STATE_DIR"]) / "state.json")


def test_dispatch_verify_wait_use_scheduler_and_persist_signed_state(tmp_path: Path) -> None:
    receipt = _route(_startup())
    route = receipt["setup_contract"]["routing_request"]
    state = Path(os.environ["SENIOR_HARNESS_STATE_DIR"]) / f"{tmp_path.name}-state.json"
    dispatched = authorize_event(receipt, _plan(receipt), route, {
        "tool_name": "senior-harness.dispatch", "tool_input": {"node_id": "1.1", "worker_context_id": "host-a"},
    }, state_path=state)
    assert next(node for node in dispatched["plan"]["nodes"] if node["id"] == "1.1")["state"] == "running"
    verifying = authorize_event(receipt, dispatched["plan"], route, {
        "tool_name": "senior-harness.verify", "tool_input": {"node_id": "1.1"},
    }, state_path=state)
    assert next(node for node in verifying["plan"]["nodes"] if node["id"] == "1.1")["state"] == "verifying"
    waited = authorize_event(receipt, verifying["plan"], route, {
        "tool_name": "senior-harness.wait", "tool_input": {},
    }, state_path=state)
    assert waited["scheduler"]["active"] == ["1.1"]
    stored = json.loads(state.read_text(encoding="utf-8"))
    assert stored["last_operation"] == "wait"
    assert stored["authority_mac"].startswith("hmac-sha256:")
    assert oct(state.stat().st_mode & 0o777) == "0o600"


def test_route_plan_and_state_forgery_fail_closed(tmp_path: Path) -> None:
    receipt = _route(_startup())
    route = receipt["setup_contract"]["routing_request"]
    state = Path(os.environ["SENIOR_HARNESS_STATE_DIR"]) / f"{tmp_path.name}-state.json"
    initial_plan = _plan(receipt)
    with pytest.raises(ControlPlaneError, match="must be under"):
        authorize_event(receipt, initial_plan, route, {
            "tool_name": "reserve_dispatch", "tool_input": {"node_id": "1.1", "worker_context_id": "host-a"},
        }, state_path=tmp_path / "must-not-live-in-checkout-or-an-arbitrary-path.json")
    dispatched = authorize_event(receipt, initial_plan, route, {
        "tool_name": "reserve_dispatch", "tool_input": {"node_id": "1.1", "worker_context_id": "host-a"},
    }, state_path=state)
    # A concurrent caller holding the plan it read before the first reservation
    # cannot make a second reservation after the compare-and-swap transaction.
    with pytest.raises(ControlPlaneError, match="plan_digest"):
        authorize_event(receipt, initial_plan, route, {
            "tool_name": "reserve_dispatch", "tool_input": {"node_id": "1.2", "worker_context_id": "host-b"},
        }, state_path=state)
    state.write_text('{"schema_version":"1.0","authority_mac":"forged"}', encoding="utf-8")
    with pytest.raises(ControlPlaneError, match="authenticity"):
        authorize_event(receipt, dispatched["plan"], route, {"tool_name": "wait", "tool_input": {}}, state_path=state)


def test_cli_returns_machine_readable_denial(tmp_path: Path) -> None:
    receipt = _route(_startup())
    route = receipt["setup_contract"]["routing_request"]
    inputs = {"receipt": receipt, "plan": _plan(receipt), "route": route, "event": {"tool_name": "shell", "tool_input": {}}}
    paths = {}
    for name, payload in inputs.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = path
    state_root = tmp_path / "state-root"
    env = dict(os.environ, SENIOR_HARNESS_CONTROL_HMAC_KEY=TEST_KEY, UNLAZY_RECEIPT_HMAC_KEY="unlazy-control-plane-test-key-at-least-32-bytes", SENIOR_HARNESS_STATE_DIR=str(state_root))
    result = subprocess.run([sys.executable, str(SCRIPT_DIR / "control_plane.py"), "authorize", "--receipt", str(paths["receipt"]), "--plan", str(paths["plan"]), "--routing-request", str(paths["route"]), "--event", str(paths["event"]), "--state", str(state_root / "state.json")], cwd=REPO_ROOT, env=env, text=True, capture_output=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "denied"
