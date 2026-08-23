"""Focused tests for lifecycle and adapter capacity."""

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


def _hook(
    base: dict[str, str], event: str, *, surface: str = "codex", **payload: object
) -> dict:
    return handle_hook(
        {**base, "hook_event_name": event, **payload},
        surface=surface,
        event=event,
    )


def _assert_parallel_contract(contract: dict, context: str, expected: bool) -> None:
    capabilities = contract["routing_request"]["capabilities"]
    assert capabilities["supports_parallel"] is expected
    assert capabilities["supports_cancellation"] is expected
    assert contract["orchestration_policy"]["parallel_required"] is expected
    assert contract["orchestration_policy"]["requires_disjoint_ownership_proof"] is True
    if expected:
        assert contract["routing_request"]["signals"]["ownership_disjoint"] is False
        assert contract["route_decision"]["action"] == "delegate"
        assert contract["route_decision"]["execution"]["max_parallel_workers"] == 4
        reasons = contract["route_decision"]["reasons"]
        assert "parallel-first-capacity-pending-disjoint-proof" in reasons
        assert contract["orchestration_policy"]["root_mutation_authority"] is False
        assert "dispatch independent workers immediately" in context
        assert "Do not begin root implementation first" in context
    else:
        assert "dispatch independent workers immediately" not in context


ADAPTER_CAPACITY_CASES = [
    ("codex", True, True),
    ("codex", False, False),
    ("claude", True, False),
    ("claude", False, False),
]


def test_hook_lifecycle_freezes_first_prompt_and_denies_missing_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    _observe_adapter(tmp_path, monkeypatch)
    base = {"session_id": "session-1", "cwd": str(REPO_ROOT)}

    denied = _hook(base, "PreToolUse")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"

    submitted = _hook(base, "UserPromptSubmit", prompt="  Primary objective  ")
    assert "Primary objective" in submitted["hookSpecificOutput"]["additionalContext"]

    allowed = _hook(base, "PreToolUse", tool_name="Read", tool_input={})
    assert "permissionDecision" not in allowed["hookSpecificOutput"]
    assert "Primary objective" in allowed["hookSpecificOutput"]["additionalContext"]
    assert (
        "dispatch independent workers immediately"
        in allowed["hookSpecificOutput"]["additionalContext"]
    )

    followup = _hook(base, "UserPromptSubmit", prompt="Push an unrelated release")
    assert "remains frozen" in followup["hookSpecificOutput"]["additionalContext"]
    assert "Primary objective" in followup["hookSpecificOutput"]["additionalContext"]
    assert (
        "dispatch independent workers immediately"
        in followup["hookSpecificOutput"]["additionalContext"]
    )

    cleared = _hook(base, "SessionStart", source="clear")
    assert (
        "cleared the prior objective lock"
        in cleared["hookSpecificOutput"]["additionalContext"]
    )
    denied_after_clear = _hook(base, "PreToolUse")
    assert denied_after_clear["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"adapter_signature": "   "}, "blank signature"),
        ({"adapter_signature": None}, "missing signature"),
        ({"capacity": False}, "capacity not demonstrated"),
        ({"isolation": False}, "isolation not demonstrated"),
        ({"signed_dispatch": False}, "dispatch not signed"),
        ({"cancellation": False}, "cancellation not demonstrated"),
        ({"capacity": "yes"}, "evidence is not a boolean true"),
        ({"surface": "claude"}, "receipt belongs to another surface"),
    ],
)
def test_incomplete_adapter_receipt_never_grants_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: dict, reason: str
) -> None:
    """A receipt missing any named evidence item must fail closed, not degrade quietly."""
    receipt_path = _observe_adapter(tmp_path, monkeypatch)
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload.update(mutation)
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    assert setup_driver_module._read_adapter_receipt("codex") is None, reason
    capabilities = setup_driver_module._surface_capabilities(
        "codex",
        hooks_configured=True,
        adapter_receipt=setup_driver_module._read_adapter_receipt("codex"),
    )
    assert capabilities["supports_parallel"] is False, reason
    assert capabilities["supports_cancellation"] is False, reason
    assert capabilities["capability_probe"] == "unprobed"


def test_unreadable_adapter_receipt_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed or absent receipt file is unprobed, never assumed good."""
    monkeypatch.setenv(
        setup_driver_module.ADAPTER_RECEIPT_ENV, str(tmp_path / "absent.json")
    )
    assert setup_driver_module._read_adapter_receipt("codex") is None

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(setup_driver_module.ADAPTER_RECEIPT_ENV, str(broken))
    assert setup_driver_module._read_adapter_receipt("codex") is None

    monkeypatch.delenv(setup_driver_module.ADAPTER_RECEIPT_ENV, raising=False)
    assert setup_driver_module._read_adapter_receipt("codex") is None


@pytest.mark.parametrize(
    ("surface", "observed_adapter", "parallel_expected"), ADAPTER_CAPACITY_CASES
)
def test_fresh_hook_session_routes_substantive_work_to_parallel_fanout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    observed_adapter: bool,
    parallel_expected: bool,
) -> None:
    """A host may claim parallel capacity only when its signed adapter exists."""
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv(setup_driver_module.ADAPTER_RECEIPT_ENV, raising=False)
    if observed_adapter:
        _observe_adapter(tmp_path, monkeypatch, surface=surface)
    base = {"session_id": "fresh-parallel-window", "cwd": str(REPO_ROOT)}

    submitted = _hook(
        base,
        "UserPromptSubmit",
        surface=surface,
        prompt="Repair the harness, test the runtime, and independently review the result",
    )

    state_path = setup_driver_module._state_path(
        REPO_ROOT.resolve(), base["session_id"]
    )
    receipt = json.loads(state_path.read_text(encoding="utf-8"))["receipt"]
    contract = receipt["setup_contract"]
    context = submitted["hookSpecificOutput"]["additionalContext"]
    _assert_parallel_contract(contract, context, parallel_expected)
