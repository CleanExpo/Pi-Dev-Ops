"""Focused tests for pending objective integrity."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    REPO_ROOT,
    _global_hook,
    _global_hook_result,
    _pending_file,
    _tamper_env,
    json,
    setup_driver_module,
)


def _tampered_pending(
    tmp_path: Path, session: str
) -> tuple[dict[str, str], Path, Path, dict]:
    env = _tamper_env(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    _global_hook(
        "UserPromptSubmit",
        {"session_id": session, "cwd": str(outside), "prompt": "Inspect only"},
        env,
    )
    pending_path = _pending_file(tmp_path)
    tampered = json.loads(pending_path.read_text(encoding="utf-8"))
    tampered["literal_objective"] = "Deploy instead"
    pending_path.write_text(json.dumps(tampered), encoding="utf-8")
    return env, outside, pending_path, tampered


def _pretool(session: str, tool: str, env: dict[str, str]) -> dict:
    return _global_hook(
        "PreToolUse",
        {
            "session_id": session,
            "cwd": str(REPO_ROOT),
            "tool_name": tool,
            "tool_input": {},
        },
        env,
    )


def test_a_later_prompt_cannot_launder_a_tampered_pending_objective(
    tmp_path: Path,
) -> None:
    """tampered state -> another prompt -> first tool attempt stays denied."""
    session = "tamper-then-prompt"
    env, outside, pending_path, tampered = _tampered_pending(tmp_path, session)

    outside_prompt = _global_hook_result(
        "UserPromptSubmit",
        {"session_id": session, "cwd": str(outside), "prompt": "Replace it"},
        env,
    )
    assert outside_prompt["decision"] == "block"
    assert "pending startup objective is invalid" in outside_prompt["reason"]
    assert "source=clear" in outside_prompt["reason"]

    inside_prompt = _global_hook_result(
        "UserPromptSubmit",
        {"session_id": session, "cwd": str(REPO_ROOT), "prompt": "Replace it"},
        env,
    )
    assert inside_prompt["decision"] == "block"
    assert "pending startup objective is invalid" in inside_prompt["reason"]

    assert json.loads(pending_path.read_text(encoding="utf-8")) == tampered
    assert not setup_driver_module._state_path(REPO_ROOT.resolve(), session).exists()

    for tool in ("Write", "Bash", "Read"):
        denied = _pretool(session, tool, env)
        assert denied["permissionDecision"] == "deny", tool
        assert (
            "pending startup objective is invalid" in denied["permissionDecisionReason"]
        )
    assert not setup_driver_module._state_path(REPO_ROOT.resolve(), session).exists()


def test_session_start_clear_is_the_one_recovery_from_a_tampered_pending_objective(
    tmp_path: Path,
) -> None:
    """Positive control: the terminal denial is escapable exactly as documented."""
    session = "tamper-then-clear"
    env, outside, pending_path, _ = _tampered_pending(tmp_path, session)
    denied = _pretool(session, "Write", env)
    assert denied["permissionDecision"] == "deny"

    cleared = _global_hook(
        "SessionStart",
        {"session_id": session, "cwd": str(outside), "source": "clear"},
        env,
    )
    assert "cleared the pending objective lock" in cleared["additionalContext"]
    assert not pending_path.exists()

    recovered_prompt = "Rebuild the startup receipt"
    frozen = _global_hook(
        "UserPromptSubmit",
        {"session_id": session, "cwd": str(outside), "prompt": recovered_prompt},
        env,
    )
    assert repr(recovered_prompt) in frozen["additionalContext"]

    admitted = _pretool(session, "Read", env)
    assert "permissionDecision" not in admitted
    assert "recovered pending objective" in admitted["additionalContext"]
    assert repr(recovered_prompt) in admitted["additionalContext"]
