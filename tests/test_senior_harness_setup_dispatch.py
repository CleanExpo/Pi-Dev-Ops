"""Focused tests for delivery dispatch admission."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    REPO_ROOT,
    SCRIPT_DIR,
    SetupError,
    _delivery,
    _receipt,
    guard_dispatch,
    json,
    pytest,
    subprocess,
    sys,
)


def _git_status() -> str:
    return subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _start_result(surface: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "setup_driver.py"),
            "start",
            "Create the setup driver",
            "--project",
            str(REPO_ROOT),
            "--surface",
            surface,
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_guard_accepts_only_ready_nonmutating_move() -> None:
    objective = "Create the setup driver"
    receipt = _receipt(objective)
    payload = _delivery(objective)
    for move in payload["move_graph"][:6]:
        move["status"] = "passed"
    payload["move_graph"][6]["status"] = "ready"

    assert guard_dispatch(payload, receipt, "M07")["status"] == "admitted"
    with pytest.raises(SetupError, match="cannot authorize mutating"):
        guard_dispatch(payload, receipt, "M12")


def test_open_uncertainty_case_keeps_original_problem_stopped() -> None:
    objective = "Create the setup driver"
    receipt = _receipt(objective)
    payload = _delivery(objective)
    for move in payload["move_graph"][:6]:
        move["status"] = "passed"
    payload["move_graph"][6]["status"] = "ready"
    payload["uncertainty_cases"] = [
        {
            "problem_id": "P-setup",
            "status": "open",
            "stop_current_path": True,
            "specialist_ids": ["a", "b"],
            "arbiter_id": "c",
            "evidence_ids": ["E1", "E2"],
            "experiment": "Independent replay",
            "resolution_criterion": "Replay agrees",
        }
    ]

    with pytest.raises(SetupError, match="stopped by an open uncertainty case"):
        guard_dispatch(payload, receipt, "M07", problem_id="P-setup")


@pytest.mark.parametrize("surface", ["codex", "claude", "vscode-openrouter"])
def test_cli_start_is_machine_readable_read_only_and_conservative(surface: str) -> None:
    before = _git_status()
    result = _start_result(surface)
    after = _git_status()

    receipt = json.loads(result.stdout)
    assert receipt["stage"] == "startup-admitted"
    setup = receipt["setup_contract"]
    assert setup["surface"] == surface
    assert setup["routing_request"]["capabilities"]["supports_parallel"] is False
    assert setup["routing_request"]["capabilities"]["supports_cancellation"] is False
    assert setup["route_decision"]["action"] == "delegate"
    assert setup["orchestration_policy"]["parallel_required"] is False
    assert before == after
