"""Focused tests for recovery and control drift."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    REPO_ROOT,
    _pretool,
    _rehash_receipt,
    _start_hook_session,
    handle_hook,
    json,
    pytest,
    setup_driver_module,
)


def _recovery_hook(
    base: dict[str, str], tool_name: str, tool_input: dict | None = None
) -> dict:
    return handle_hook(
        {
            **base,
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input or {},
        },
        surface="claude",
        event="PreToolUse",
    )


def test_hook_allows_only_exact_recovery_safe_reads_without_startup_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    base = {
        "session_id": "recovery-no-state",
        "cwd": str(REPO_ROOT),
        "hook_event_name": "PreToolUse",
    }

    for tool_name in (
        "Read",
        "ToolSearch",
        "ReadMcpResource",
        "mcp__exa__web_search_exa",
        "mcp__plugin_exa_exa__get_code_context_exa",
    ):
        result = _recovery_hook(base, tool_name)
        output = result["hookSpecificOutput"]
        assert "permissionDecision" not in output
        assert "recovery-only read" in output["additionalContext"]
        assert "grants no mutation" in output["additionalContext"]

    for tool_name, tool_input in (
        ("Write", {"file_path": "x"}),
        ("Bash", {"command": "touch x"}),
        ("mcp__computer-use__computer", {"action": "click"}),
        ("ReadAndWrite", {}),
        ("ToolSearchMutate", {}),
        ("mcp__exa__web_search_exa_then_write", {}),
        ("mcp__attacker__read", {}),
    ):
        denied = _recovery_hook(base, tool_name, tool_input)
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_invalid_startup_state_allows_recovery_read_but_denies_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "state"
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(state_root))
    base = {"session_id": "recovery-invalid", "cwd": str(REPO_ROOT)}
    handle_hook(
        {
            **base,
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Inspect the invalid state",
        },
        surface="claude",
        event="UserPromptSubmit",
    )
    state_path = next(state_root.rglob("*.json"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["receipt"]["stage"] = "tampered"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    read_result = _recovery_hook(base, "Read")
    assert "permissionDecision" not in read_result["hookSpecificOutput"]
    assert (
        "startup state is invalid"
        in read_result["hookSpecificOutput"]["additionalContext"]
    )

    write_result = _recovery_hook(base, "Write")
    assert write_result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_first_tool_control_drift_uses_recovery_read_without_admitting_the_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "state"
    base, state_path = _start_hook_session(
        state_root, monkeypatch, session_id="first-tool-drift-read"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    receipt = state["receipt"]
    receipt["setup_contract"]["required_skills"]["senior-harness"]["folder_digest"] = (
        "sha256:" + "0" * 64
    )
    _rehash_receipt(receipt)
    state_path.write_text(json.dumps(state), encoding="utf-8")

    binding_result = setup_driver_module._check_control_bindings(receipt)
    assert binding_result.integrity_failures == ()
    assert binding_result.drift == (
        "bound skill changed after startup admission: senior-harness",
    )

    first_read = _pretool(base, "Read")
    assert "permissionDecision" not in first_read["hookSpecificOutput"]
    assert "recovery-only read" in first_read["hookSpecificOutput"]["additionalContext"]
    assert (
        "bound skill changed after startup admission"
        in first_read["hookSpecificOutput"]["additionalContext"]
    )

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["first_tool_admitted"] is False

    first_write = _pretool(base, "Write")
    assert first_write["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert (
        "bound skill changed after startup admission"
        in first_write["hookSpecificOutput"]["permissionDecisionReason"]
    )


def test_first_tool_control_drift_denies_mutation_in_a_fresh_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state", monkeypatch, session_id="first-tool-drift-write"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["receipt"]["driver_digest"] = "sha256:" + "0" * 64
    _rehash_receipt(state["receipt"])
    state_path.write_text(json.dumps(state), encoding="utf-8")

    denied = _pretool(base, "Write")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert (
        "setup driver changed after startup admission"
        in denied["hookSpecificOutput"]["permissionDecisionReason"]
    )


def test_delivery_control_drift_after_clean_first_tool_warns_without_denying_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state", monkeypatch, session_id="later-delivery-drift"
    )
    clean_first_tool = _pretool(base, "Read")
    assert "permissionDecision" not in clean_first_tool["hookSpecificOutput"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["first_tool_admitted"] is True

    state["receipt"]["driver_digest"] = "sha256:" + "0" * 64
    _rehash_receipt(state["receipt"])
    state_path.write_text(json.dumps(state), encoding="utf-8")

    later_write = _pretool(base, "Write")
    later_output = later_write["hookSpecificOutput"]
    assert "permissionDecision" not in later_output
    assert "control-code drift detected" in later_output["additionalContext"]

    followup = handle_hook(
        {
            **base,
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Continue the same objective",
        },
        surface="claude",
        event="UserPromptSubmit",
    )
    assert (
        "Control-code drift is present"
        in followup["hookSpecificOutput"]["additionalContext"]
    )


def test_integrity_failure_overrides_mixed_post_admission_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state", monkeypatch, session_id="mixed-binding-failure"
    )
    assert "permissionDecision" not in _pretool(base, "Read")["hookSpecificOutput"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    receipt = state["receipt"]
    receipt["setup_contract"]["required_skills"]["senior-harness"]["folder_digest"] = (
        "sha256:" + "0" * 64
    )
    receipt.pop("driver_digest")
    _rehash_receipt(receipt)
    state_path.write_text(json.dumps(state), encoding="utf-8")

    binding_result = setup_driver_module._check_control_bindings(receipt)
    failure = "setup driver digest is missing or malformed"
    drift = "bound skill changed after startup admission: senior-harness"
    assert failure in binding_result.integrity_failures
    assert drift in binding_result.drift

    denied = _pretool(base, "Write")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    denied_reason = denied["hookSpecificOutput"]["permissionDecisionReason"]
    assert failure in denied_reason

    recovery_read = _pretool(base, "Read")
    recovery_output = recovery_read["hookSpecificOutput"]
    assert "permissionDecision" not in recovery_output
    assert "recovery-only read" in recovery_output["additionalContext"]
    assert failure in recovery_output["additionalContext"]


def test_grill_drift_remains_strict_after_a_prior_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state",
        monkeypatch,
        session_id="grill-binding-drift",
        prompt="/grill-me shape recovery",
    )
    assert "permissionDecision" not in _pretool(base, "Read")["hookSpecificOutput"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["receipt"]["driver_digest"] = "sha256:" + "0" * 64
    _rehash_receipt(state["receipt"])
    state_path.write_text(json.dumps(state), encoding="utf-8")

    recovery_read = _pretool(base, "Read")
    read_output = recovery_read["hookSpecificOutput"]
    assert "permissionDecision" not in read_output
    assert "recovery-only read" in read_output["additionalContext"]
    assert "Delivery may continue" not in read_output["additionalContext"]

    denied = _pretool(base, "Write")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert (
        "setup driver changed after startup admission"
        in denied["hookSpecificOutput"]["permissionDecisionReason"]
    )
