"""Focused tests for hook manifests and global recovery."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    REPO_ROOT,
    SCRIPT_DIR,
    SetupError,
    _global_hook,
    _tamper_env,
    handle_hook,
    json,
    os,
    pytest,
    subprocess,
    sys,
)


def _outside_prompt(
    session_id: str, cwd: Path, prompt: str, env: dict[str, str]
) -> dict:
    return _global_hook(
        "UserPromptSubmit",
        {"session_id": session_id, "cwd": str(cwd), "prompt": prompt},
        env,
    )


def test_hook_rejects_malformed_or_mismatched_input() -> None:
    with pytest.raises(SetupError, match="missing session_id"):
        handle_hook({}, surface="claude", event="PreToolUse")
    with pytest.raises(SetupError, match="event mismatch"):
        handle_hook(
            {
                "session_id": "s",
                "cwd": str(REPO_ROOT),
                "hook_event_name": "SessionStart",
            },
            surface="claude",
            event="PreToolUse",
        )


def test_project_hook_manifests_preserve_existing_claude_gate() -> None:
    codex = json.loads(
        (REPO_ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8")
    )
    claude = json.loads(
        (REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
    )

    for manifest in (codex, claude):
        assert {"SessionStart", "UserPromptSubmit", "PreToolUse"} <= set(
            manifest["hooks"]
        )
    claude_pretool_commands = [
        hook["command"]
        for group in claude["hooks"]["PreToolUse"]
        for hook in group["hooks"]
    ]
    assert any("run_setup_driver.sh" in command for command in claude_pretool_commands)
    assert any(
        "autonomy_gate_hook.py" in command for command in claude_pretool_commands
    )


def test_hook_cli_malformed_pretool_input_returns_a_deny_decision() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "setup_driver.py"),
            "hook",
            "--surface",
            "codex",
            "--event",
            "PreToolUse",
        ],
        input="not-json",
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "malformed hook input" in output["permissionDecisionReason"]


def test_global_hook_can_skip_non_git_tasks_without_making_an_admission_claim(
    tmp_path: Path,
) -> None:
    payload = json.dumps(
        {
            "session_id": "outside-git",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
        }
    )
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
        input=payload,
        capture_output=True,
        text=True,
        check=True,
    )

    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert "permissionDecision" not in output
    assert "outside a Git project" in output["additionalContext"]


def test_global_hook_recovers_original_prompt_after_entering_git(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    env = _tamper_env(tmp_path)
    prompt = "Repair the startup receipt loop"

    submitted = _outside_prompt("outside-then-git", outside, prompt, env)
    assert "pending" in submitted["additionalContext"]
    repeated = _outside_prompt("outside-then-git", outside, "Replace it", env)
    assert repr(prompt) in repeated["additionalContext"]
    assert "Replace it" not in repeated["additionalContext"]

    output = _global_hook(
        "PreToolUse",
        {
            "session_id": "outside-then-git",
            "cwd": str(REPO_ROOT),
            "tool_name": "Read",
            "tool_input": {},
        },
        env,
    )
    assert "permissionDecision" not in output
    assert "recovered pending objective" in output["additionalContext"]
    assert repr(prompt) in output["additionalContext"]
    assert "no startup receipt exists" not in output["additionalContext"]


def test_global_hook_refuses_a_tampered_pending_prompt(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    outside = tmp_path / "outside"
    outside.mkdir()
    env = dict(
        os.environ,
        SENIOR_HARNESS_STATE_DIR=str(state_root),
        SENIOR_HARNESS_SEAL_KEY_FILE=str(tmp_path / "seal.key"),
    )
    _global_hook(
        "UserPromptSubmit",
        {
            "session_id": "tampered-pending",
            "cwd": str(outside),
            "prompt": "Inspect only",
        },
        env,
    )
    pending_files = list(state_root.rglob("*.json"))
    assert len(pending_files) == 1
    pending = json.loads(pending_files[0].read_text(encoding="utf-8"))
    pending["literal_objective"] = "Deploy instead"
    pending_files[0].write_text(json.dumps(pending), encoding="utf-8")

    output = _global_hook(
        "PreToolUse",
        {
            "session_id": "tampered-pending",
            "cwd": str(REPO_ROOT),
            "tool_name": "Write",
            "tool_input": {},
        },
        env,
    )
    assert output["permissionDecision"] == "deny"
    assert "pending startup objective is invalid" in output["permissionDecisionReason"]
