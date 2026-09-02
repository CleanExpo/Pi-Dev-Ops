from __future__ import annotations

from app.server import continuation_horizon as horizon
from app.server import continuation_store


def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("TAO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(continuation_store, "load", lambda: {})
    monkeypatch.setattr(continuation_store, "save", lambda state: False)


def test_arm_objective_persists_cross_channel_state(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    state = horizon.arm_objective(objective="Finish Model Fabric", source="telegram", chat_id="8792816988")
    assert state["armed"] is True
    assert state["objective"] == "Finish Model Fabric"
    assert state["source"] == "telegram"
    assert state["chat_id"] == "8792816988"
    assert horizon.load_state()["objective"] == "Finish Model Fabric"


def test_followup_refines_instead_of_replacing_root_objective(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Finish Mission Control", source="telegram")
    state = horizon.arm_objective(objective="Also fix the Pixel Office", source="telegram")
    assert state["objective"] == "Finish Mission Control"
    assert state["latest_instruction"] == "Also fix the Pixel Office"
    assert state["objective_updates"][-1]["text"] == "Also fix the Pixel Office"


def test_durable_state_wins_over_local_cache(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    horizon.save_state({"armed": True, "objective": "local"})
    monkeypatch.setattr(continuation_store, "load", lambda: {"armed": True, "objective": "durable"})
    assert horizon.load_state()["objective"] == "durable"


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
    """RA-7373: this test's PRECONDITION changed, not its claim.

    It used to reach `should_continue() is True` by arming an objective and
    nothing else — which was true only because an empty horizon returned True,
    the defect this ticket is about. The assertion was pinning the bug while
    appearing to test completion.

    Its name and purpose are unchanged: completion disarms the guard. It now
    earns the True with a real pending step, so it tests what it claims.
    """
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Finish", source="claude")
    horizon.set_horizon([{"id": 1, "title": "Ship the fix"}])
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


# ── RA-7373: a guard that cannot pass carries no information ────────────────
#
# `should_continue()` returned True for an empty horizon, and `set_horizon()`
# has no caller outside these tests — so `steps` was never populated by
# anything that ships. The Stop hook therefore blocked unconditionally,
# forever, with no horizon to work through and no discoverable way to finish.

def test_an_empty_horizon_does_not_block_forever(monkeypatch, tmp_path):
    """THE DEFECT. Armed with nothing queued must mean "nothing to do".

    Read the other way — an empty horizon meaning "keep going" — the guard can
    never return False on its own, because only `set_horizon()` can make
    `steps` non-empty and nothing in production calls it.
    """
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Do the thing and stop.", source="claude")
    assert horizon.load_state().get("steps") in (None, [])
    assert horizon.should_continue() is False


def test_a_populated_horizon_still_blocks(monkeypatch, tmp_path):
    """GREEN CONTROL. The guard must still hold work open when work exists —
    otherwise the fix would have disabled the feature rather than repaired it."""
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Ship it", source="claude")
    horizon.set_horizon([{"id": 1, "title": "Write the test"},
                         {"id": 2, "title": "Push the fix"}])
    assert horizon.should_continue() is True


def test_a_fully_worked_horizon_stops(monkeypatch, tmp_path):
    """GREEN CONTROL 2 — the pre-existing exit still works. Every step done
    means done, without needing `mark_complete()`."""
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Ship it", source="claude")
    horizon.set_horizon([{"id": 1, "title": "Only step"}])
    horizon.mark_step("1", "done")
    assert horizon.should_continue() is False


def test_the_contract_names_the_mechanism_that_clears_it(monkeypatch, tmp_path):
    """The contract said WHEN to stop and never HOW to record it.

    `mark_complete()` is the only thing that clears the guard, and it appeared
    nowhere in the emitted text — nor anywhere else an agent would look. An
    exit that cannot be discovered is not an exit.
    """
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Finish", source="claude")
    text = horizon.operator_context()
    assert "mark_complete" in text
    assert "verified complete" in text, "the WHEN clause must survive too"


def test_a_refinement_from_another_surface_is_not_shown(monkeypatch, tmp_path):
    """CROSS-CONTEXT CONTAMINATION.

    One global state key is armed from every surface — claude, telegram, slack,
    subagents. Arming from a second surface while a first objective is active
    left the newcomer's prompt rendered to the first agent as "Latest
    refinement" of its own objective. Observed live: a telegram rubric shown to
    a claude session working an unrelated ticket.
    """
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Work the mesh ticket.", source="claude")
    horizon.arm_objective(objective="Review the brand rubric.", source="telegram")
    text = horizon.operator_context()
    assert "Work the mesh ticket." in text, "the root objective must survive"
    assert "Latest refinement" not in text
    assert "brand rubric" not in text


def test_a_refinement_from_the_same_surface_is_still_shown(monkeypatch, tmp_path):
    """GREEN CONTROL. Suppressing every refinement would be a different bug —
    a genuine follow-up from the owning surface must still reach the agent."""
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Work the mesh ticket.", source="claude")
    horizon.arm_objective(objective="Also cover the reaper path.", source="claude")
    text = horizon.operator_context()
    assert "Latest refinement: Also cover the reaper path." in text


def test_state_written_before_this_change_suppresses_the_refinement(monkeypatch, tmp_path):
    """Fail closed on state that predates `objective_source`.

    `.harness/` is per-machine runtime state, so files written by the old code
    exist and carry no owning context. Unknown must read as "cannot verify",
    not as "same context" — the whole defect was showing a prompt whose origin
    nobody had checked.
    """
    _isolated(monkeypatch, tmp_path)
    horizon.arm_objective(objective="Root", source="claude")
    state = horizon.load_state()
    state.pop("objective_source", None)
    state["latest_instruction"] = "A refinement of unknown origin"
    horizon.save_state(state)
    assert "Latest refinement" not in horizon.operator_context()
