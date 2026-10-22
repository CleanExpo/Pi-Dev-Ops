"""Focused tests for hook manifests and global recovery."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    REPO_ROOT,
    SCRIPT_DIR,
    SetupError,
    _global_hook,
    _start_hook_session,
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


def _cursor(event: str, **fields: object) -> dict:
    """A payload shaped like the one cursor-agent 2026.10.19 sends to Claude hooks."""
    return {
        "conversation_id": "cursor-conv",
        "hook_event_name": event,
        "cursor_version": "2026.10.19-6bbf2c4",
        "workspace_roots": [str(REPO_ROOT)],
        **fields,
    }


def test_cursor_payload_is_normalised_and_still_mediated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt = "Review the auth change"
    _start_hook_session(
        tmp_path / "state", monkeypatch, session_id="cursor-conv", prompt=prompt
    )
    started = handle_hook(
        _cursor("sessionStart", session_id="cursor-conv"),
        surface="claude", event="SessionStart",
    )
    assert "permissionDecision" not in started["hookSpecificOutput"]

    shell = handle_hook(
        _cursor(
            "preToolUse", cwd="", tool_name="Shell",
            tool_input={"command": "echo hi", "cwd": "", "timeout": 30000},
        ),
        surface="claude", event="PreToolUse",
    )["hookSpecificOutput"]
    assert "permissionDecision" not in shell
    assert repr(prompt) in shell["additionalContext"]


def test_cursor_payload_with_a_real_mismatch_is_still_refused() -> None:
    with pytest.raises(SetupError, match="event mismatch"):
        handle_hook(
            _cursor("preToolUse", session_id="s", tool_name="Shell"),
            surface="claude", event="UserPromptSubmit",
        )
    with pytest.raises(SetupError, match="event mismatch"):
        handle_hook(
            {"session_id": "s", "cwd": str(REPO_ROOT), "hook_event_name": "preToolUse"},
            surface="claude", event="PreToolUse",
        )
    with pytest.raises(SetupError, match="missing cwd"):
        handle_hook(
            _cursor("preToolUse", session_id="s", workspace_roots=["/a", "/b"]),
            surface="claude", event="PreToolUse",
        )


def test_cursor_tool_without_a_frozen_objective_gets_a_deny_cursor_obeys(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT_DIR / "setup_driver.py"), "hook",
            "--surface", "claude", "--event", "PreToolUse", "--allow-non-git",
        ],
        input=json.dumps(_cursor(
            "preToolUse", session_id="cursor-no-prompt", cwd="",
            tool_name="Shell", tool_input={"command": "touch marker.txt"},
        )),
        env=_tamper_env(tmp_path), capture_output=True, text=True, check=True,
    )
    # Cursor obeys this Claude-format deny (probed 22/10/2026: the Shell call
    # was refused and no file was written); a non-deny JSON object is ignored.
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "no startup receipt exists" in output["permissionDecisionReason"]
