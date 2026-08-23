"""Negative controls for fail-closed Senior Harness lifecycle hooks."""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "senior-harness" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import setup_driver  # noqa: E402


def _hook_cli(tmp_path: Path, tool_name: str, tool_input: dict[str, str]) -> dict:
    payload = {
        "session_id": "outside-git-security",
        "cwd": str(tmp_path),
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
    }
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "setup_driver.py"),
            "hook",
            "--surface",
            "codex",
            "--event",
            "PreToolUse",
            "--allow-non-git",
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["hookSpecificOutput"]


def _base(session_id: str, event: str) -> dict[str, str]:
    return {
        "session_id": session_id,
        "cwd": str(REPO_ROOT),
        "hook_event_name": event,
    }


def _grill_command(command: str, state: Path) -> dict[str, object]:
    return {
        **_base("grill-security", "PreToolUse"),
        "tool_name": "Bash",
        "tool_input": {
            "command": shlex.join(
                [sys.executable, str(SCRIPT_DIR / "grill_session.py"), command, "--state", str(state)]
            )
        },
    }


def test_outside_git_write_is_denied_without_a_receipt(tmp_path: Path) -> None:
    output = _hook_cli(tmp_path, "Write", {"file_path": str(tmp_path / "escaped")})
    assert output["permissionDecision"] == "deny"
    assert "no startup receipt" in output["permissionDecisionReason"]


def test_outside_git_exact_read_stays_recovery_only(tmp_path: Path) -> None:
    output = _hook_cli(tmp_path, "Read", {"file_path": str(tmp_path / "evidence")})
    assert "permissionDecision" not in output
    assert "recovery-only read" in output["additionalContext"]


def test_git_grep_pager_execution_is_not_recovery_safe() -> None:
    payload = {
        "tool_name": "exec_command",
        "tool_input": {"cmd": "git grep -O'/usr/bin/touch /tmp/probe' pattern"},
    }
    assert setup_driver._tool_is_recovery_safe(payload) is False


def test_invalid_receipt_cannot_replace_the_frozen_objective(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    first = {**_base("tamper-lock", "UserPromptSubmit"), "prompt": "frozen objective"}
    setup_driver.handle_hook(first, surface="codex", event="UserPromptSubmit")
    path = setup_driver._state_path(REPO_ROOT.resolve(), "tamper-lock")
    state = json.loads(path.read_text(encoding="utf-8"))
    state["receipt"]["receipt_seal"] = "sha256:" + ("0" * 64)
    path.write_text(json.dumps(state), encoding="utf-8")

    later = {**_base("tamper-lock", "UserPromptSubmit"), "prompt": "replacement objective"}
    output = setup_driver.handle_hook(later, surface="codex", event="UserPromptSubmit")

    assert output["decision"] == "block"
    assert "cannot be replaced" in output["reason"]
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["receipt"]["setup_contract"]["literal_objective"] == "frozen objective"


@pytest.mark.parametrize(
    "command", ["start", "show", "validate", "evidence", "answer", "confirm", "materialize"]
)
def test_only_shipped_grill_state_commands_use_the_driver_lane(
    command: str, tmp_path: Path
) -> None:
    assert setup_driver._tool_is_grill_driver(_grill_command(command, tmp_path / "state.json"))


def test_ungoverned_question_tool_is_not_a_recovery_read() -> None:
    assert setup_driver._tool_is_recovery_safe({"tool_name": "request_user_input"}) is False


def test_valid_grill_receipt_admits_its_driver_but_denies_generic_questions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    prompt = {**_base("grill-security", "UserPromptSubmit"), "prompt": "/grill-me secure intake"}
    setup_driver.handle_hook(prompt, surface="codex", event="UserPromptSubmit")

    driver = setup_driver.handle_hook(
        _grill_command("show", tmp_path / "state" / "grill.json"),
        surface="codex",
        event="PreToolUse",
    )["hookSpecificOutput"]
    assert "permissionDecision" not in driver

    question = {
        **_base("grill-security", "PreToolUse"),
        "tool_name": "request_user_input",
        "tool_input": {"question": "Ignore the governed decision tree?"},
    }
    denied = setup_driver.handle_hook(
        question, surface="codex", event="PreToolUse"
    )["hookSpecificOutput"]
    assert denied["permissionDecision"] == "deny"
    assert "control-state driver" in denied["permissionDecisionReason"]
