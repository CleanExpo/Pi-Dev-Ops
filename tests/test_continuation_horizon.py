from __future__ import annotations

from app.server import continuation_horizon as horizon


def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("TAO_DATA_DIR", str(tmp_path))


def test_arm_objective_persists_cross_channel_state(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    state = horizon.arm_objective(objective="Finish Model Fabric", source="telegram", chat_id="8792816988")
    assert state["armed"] is True
    assert state["objective"] == "Finish Model Fabric"
    assert state["source"] == "telegram"
    assert state["chat_id"] == "8792816988"
    assert horizon.load_state()["objective"] == "Finish Model Fabric"


def test_horizon_caps_at_fifteen_and_ready_steps_respect_dependencies(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Ship", source="mission-control")
    steps = [
        {"id": i, "title": f"Step {i}", "depends_on": [i - 1] if i > 1 else []}
        for i in range(1, 20)
    ]
    state = horizon.set_horizon(steps)
    assert len(state["steps"]) == 15
    assert [s["id"] for s in horizon.ready_steps()] == ["1"]
    horizon.mark_step("1", "verified", ["tests green"])
    assert [s["id"] for s in horizon.ready_steps()] == ["2"]


def test_protected_step_is_not_released_for_autonomous_execution(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Deploy safely", source="telegram")
    horizon.set_horizon([
        {"id": 1, "title": "Run tests"},
        {"id": 2, "title": "Production deploy", "protected": True},
    ])
    assert [s["id"] for s in horizon.ready_steps()] == ["1"]


def test_completion_disarms_stop_guard(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Finish", source="claude")
    assert horizon.should_continue() is True
    state = horizon.mark_complete(["CI green", "smoke green"])
    assert state["completed"] is True
    assert state["armed"] is False
    assert horizon.should_continue() is False


def test_operator_context_requires_refill_and_parallel_safe_work(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Keep momentum", source="telegram")
    text = horizon.operator_context()
    assert "15" in text
    assert "parallel" in text.lower()
    assert "refill" in text.lower()
    assert "protected" in text.lower()
