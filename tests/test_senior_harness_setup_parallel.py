"""Focused tests for parallel root policy."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    REPO_ROOT,
    _observe_adapter,
    handle_hook,
    json,
    pytest,
    setup_driver_module,
)


UNSAFE_VERIFIER_COMMANDS = [
    "ruff check --fix app.py",
    "ruff format app.py",
    "pytest --junitxml=app.py",
    "pytest --basetemp=app",
    "pytest /tmp/attacker_owned_test.py",
    "pytest tests/../../tmp/attacker_owned_test.py",
    "pytest tests/{../app.py,test_ok.py}",
    "./attacker/pytest -q",
    "pnpm test -- --update",
]


def _parallel_hook(
    base: dict[str, str], tool_name: str, tool_input: dict | None = None
) -> dict:
    return handle_hook(
        {
            **base,
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input or {},
        },
        surface="codex",
        event="PreToolUse",
    )


def _start_parallel_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    _observe_adapter(tmp_path, monkeypatch)
    base = {"session_id": "parallel-root-boundary", "cwd": str(REPO_ROOT)}
    handle_hook(
        {
            **base,
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Repair and verify the harness",
        },
        surface="codex",
        event="UserPromptSubmit",
    )
    return base


def _assert_root_denied(result: dict) -> None:
    output = result["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "denied root implementation" in output["permissionDecisionReason"]


def test_unverified_adapter_does_not_lock_root_or_admit_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _start_parallel_session(tmp_path, monkeypatch)
    for tool_name, tool_input in (
        ("Write", {"file_path": "app.py"}),
        ("Edit", {"file_path": "app.py"}),
        ("apply_patch", {"patch": "*** Begin Patch"}),
    ):
        result = _parallel_hook(base, tool_name, tool_input)
        assert "permissionDecision" not in result["hookSpecificOutput"]

    proof = _parallel_hook(base, "exec_command", {"cmd": "pytest -q"})
    assert "permissionDecision" not in proof["hookSpecificOutput"]

    dispatch = _parallel_hook(base, "senior-harness.dispatch", {"node_id": "1.1"})
    assert dispatch["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "signed" in dispatch["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("command", UNSAFE_VERIFIER_COMMANDS)
def test_parallel_root_denies_mutating_or_unbounded_verifier_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    del tmp_path, monkeypatch
    payload = {
        "tool_name": "exec_command", "cwd": str(REPO_ROOT),
        "tool_input": {"cmd": command},
    }
    assert setup_driver_module._is_parallel_verification_tool(payload) is False


def test_parallel_verifier_binds_actual_execution_workdir(tmp_path: Path) -> None:
    payload = {
        "tool_name": "exec_command",
        "cwd": str(REPO_ROOT),
        "tool_input": {"cmd": "pytest tests/evil.py", "workdir": str(tmp_path)},
    }
    assert setup_driver_module._is_parallel_verification_tool(payload) is False
    payload["tool_input"]["cmd"] = "pytest -q"
    assert setup_driver_module._is_parallel_verification_tool(payload) is False


def test_grill_hook_never_orders_dispatch_before_shared_understanding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    base = {"session_id": "grill-no-early-fanout", "cwd": str(REPO_ROOT)}
    submitted = handle_hook(
        {
            **base,
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/grill-me shape recovery",
        },
        surface="claude",
        event="UserPromptSubmit",
    )
    state_path = setup_driver_module._state_path(
        REPO_ROOT.resolve(), base["session_id"]
    )
    contract = json.loads(state_path.read_text(encoding="utf-8"))["receipt"][
        "setup_contract"
    ]
    assert contract["orchestration_policy"]["parallel_required"] is False
    context = submitted["hookSpecificOutput"]["additionalContext"]
    assert "dispatch independent workers immediately" not in context
    assert "worker dispatch remain denied" in context
