from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "senior-harness" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from grill_session import (  # noqa: E402
    SHARED_UNDERSTANDING_PHRASE,
    answer_pending_question,
    confirm_shared_understanding,
    start_session,
)
from senior_harness import digest  # noqa: E402
import setup_driver as setup_driver_module  # noqa: E402
from setup_driver import (  # noqa: E402
    SetupError,
    admit_startup,
    build_setup_contract,
    guard_dispatch,
    handle_hook,
    validate_startup_receipt,
)

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "senior_harness_self_host.json"


def _receipt(objective: str = "Create the setup driver") -> dict:
    contract = build_setup_contract(objective, REPO_ROOT, surface="codex")
    return admit_startup(contract)


def _delivery(objective: str = "Create the setup driver") -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["literal_request"] = objective
    payload["authorized_scope"] = [objective]
    payload["task_id"] = digest({"task": objective})[7:23]
    payload["repository"]["worktree"] = str(REPO_ROOT)
    payload["repository"]["candidate_sha"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    return payload


def _rehash_receipt(receipt: dict) -> None:
    contract = receipt.get("setup_contract")
    if isinstance(contract, dict):
        unsigned_contract = dict(contract)
        unsigned_contract.pop("setup_contract_digest", None)
        contract["setup_contract_digest"] = digest(unsigned_contract)
    unsigned_receipt = dict(receipt)
    unsigned_receipt.pop("receipt_integrity_digest", None)
    unsigned_receipt.pop("receipt_seal", None)
    receipt["receipt_integrity_digest"] = digest(unsigned_receipt)
    # Tests that intentionally model legitimate control-code drift need a
    # receipt issued by the Harness, not an attacker recomputing public hashes.
    receipt["receipt_seal"] = setup_driver_module._receipt_seal(receipt)


def _start_hook_session(
    state_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_id: str,
    prompt: str = "Develop the Senior Harness",
) -> tuple[dict[str, str], Path]:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(state_root))
    base = {"session_id": session_id, "cwd": str(REPO_ROOT)}
    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": prompt},
        surface="claude",
        event="UserPromptSubmit",
    )
    state_path = setup_driver_module._state_path(REPO_ROOT.resolve(), session_id)
    assert state_path.is_file()
    return base, state_path


def _pretool(base: dict[str, str], tool_name: str) -> dict:
    return handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": {}},
        surface="claude",
        event="PreToolUse",
    )


def test_setup_freezes_literal_objective_and_issues_no_authority() -> None:
    objective = "  Create the setup driver — exactly.  "
    receipt = _receipt(objective)

    setup = receipt["setup_contract"]
    assert setup["literal_objective"] == objective
    assert setup["authority"]["mutation_authority"] is False
    assert receipt["admission"]["startup_only"] is True
    assert receipt["admission"]["mutation_authority"] is False
    assert validate_startup_receipt(receipt, literal_objective=objective)["status"] == "valid"


def test_setup_binds_exact_checkout_head_state_skills_and_driver() -> None:
    receipt = _receipt()
    setup = receipt["setup_contract"]

    assert setup["repository"]["worktree"] == str(REPO_ROOT.resolve())
    assert len(setup["repository"]["head_sha"]) == 40
    assert set(setup["required_skills"]) == {"senior-harness", "model-router", "unlazy"}
    assert all(item["folder_digest"].startswith("sha256:") for item in setup["required_skills"].values())
    assert receipt["driver_digest"].startswith("sha256:")
    assert setup["routing_request"]["task"] == "Create the setup driver"
    assert setup["route_decision"]["quality_floor"] == "top"
    assert setup["route_decision"]["worker_role"] == "senior"
    assert setup["route_decision"]["action"] == "delegate"
    assert setup["delivery_controller"]["skill_id"] == "unlazy"
    assert setup["delivery_controller"]["required"] is True


def test_tampered_receipt_and_changed_objective_fail_closed() -> None:
    receipt = _receipt()
    tampered = copy.deepcopy(receipt)
    tampered["setup_contract"]["literal_objective"] = "Push something else"

    with pytest.raises(SetupError, match="integrity"):
        validate_startup_receipt(tampered)
    with pytest.raises(SetupError, match="differs from the frozen"):
        validate_startup_receipt(receipt, literal_objective="Secondary release task")


def test_recomputed_public_digests_cannot_forge_embedded_mutation_authority() -> None:
    forged = copy.deepcopy(_receipt())
    contract = forged["setup_contract"]
    contract["authority"]["mutation_authority"] = True
    unsigned_contract = dict(contract)
    unsigned_contract.pop("setup_contract_digest")
    contract["setup_contract_digest"] = digest(unsigned_contract)
    unsigned_receipt = dict(forged)
    unsigned_receipt.pop("receipt_integrity_digest")
    unsigned_receipt.pop("receipt_seal")
    forged["receipt_integrity_digest"] = digest(unsigned_receipt)

    with pytest.raises(SetupError, match="receipt seal does not match"):
        validate_startup_receipt(forged)


def test_recomputed_public_digests_cannot_forge_outer_business_authority() -> None:
    forged = copy.deepcopy(_receipt())
    forged["admission"]["business_authority"] = True
    unsigned_receipt = dict(forged)
    unsigned_receipt.pop("receipt_integrity_digest")
    unsigned_receipt.pop("receipt_seal")
    forged["receipt_integrity_digest"] = digest(unsigned_receipt)

    with pytest.raises(SetupError, match="receipt seal does not match"):
        validate_startup_receipt(forged)


def test_setup_rejects_subdirectory_and_strict_dirty_checkout(tmp_path: Path) -> None:
    with pytest.raises(SetupError, match="exact Git checkout root"):
        build_setup_contract("x", REPO_ROOT / "skills", surface="codex")

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "tracked").write_text("one", encoding="utf-8")
    subprocess.run(["git", "add", "tracked"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=repo, check=True)
    (repo / "dirty").write_text("two", encoding="utf-8")
    with pytest.raises(SetupError, match="clean Git checkout"):
        build_setup_contract(
            "x", repo, surface="codex", strict_clean=True, skill_search_roots=[REPO_ROOT / "skills"]
        )


def test_skill_change_invalidates_receipt(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills"
    for name in ("senior-harness", "model-router", "unlazy"):
        folder = skill_root / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test\n---\n", encoding="utf-8")
    receipt = admit_startup(
        build_setup_contract(
            "x", REPO_ROOT, surface="codex", skill_search_roots=[skill_root]
        )
    )
    (skill_root / "unlazy" / "SKILL.md").write_text("---\nname: unlazy\n---\nchanged\n", encoding="utf-8")
    with pytest.raises(SetupError, match="skill changed"):
        validate_startup_receipt(receipt)
    assert validate_startup_receipt(receipt, verify_control_bindings=False)["status"] == "valid"
    assert any("skill changed" in error for error in setup_driver_module._control_binding_errors(receipt))


def test_missing_or_misnamed_skill_fails_closed(tmp_path: Path) -> None:
    roots = tmp_path / "isolated"
    for name in ("senior-harness", "model-router", "unlazy"):
        folder = roots / name
        folder.mkdir(parents=True)
        declared = "wrong-name" if name == "unlazy" else name
        (folder / "SKILL.md").write_text(f"---\nname: {declared}\n---\n", encoding="utf-8")
    with pytest.raises(SetupError, match="declares name"):
        build_setup_contract("x", REPO_ROOT, surface="codex", skill_search_roots=[roots])


def test_repository_state_change_invalidates_receipt(tmp_path: Path) -> None:
    receipt = _receipt()
    altered = copy.deepcopy(receipt)
    altered["setup_contract"]["repository"]["head_sha"] = "0" * 40
    with pytest.raises(SetupError, match="integrity"):
        validate_startup_receipt(altered)


def test_dirty_file_byte_change_invalidates_receipt_even_when_status_shape_is_unchanged(tmp_path: Path) -> None:
    project = tmp_path / "dirty-project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True)
    tracked = project / "tracked.txt"
    tracked.write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=project, check=True)
    tracked.write_text("first dirty value\n", encoding="utf-8")
    receipt = admit_startup(
        build_setup_contract(
            "inspect dirty project",
            project,
            surface="codex",
            skill_search_roots=[REPO_ROOT / "skills"],
        )
    )

    tracked.write_text("second dirty value\n", encoding="utf-8")
    with pytest.raises(SetupError, match="worktree_state_digest changed"):
        validate_startup_receipt(receipt, project=project)


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
    payload["uncertainty_cases"] = [{
        "problem_id": "P-setup",
        "status": "open",
        "stop_current_path": True,
        "specialist_ids": ["a", "b"],
        "arbiter_id": "c",
        "evidence_ids": ["E1", "E2"],
        "experiment": "Independent replay",
        "resolution_criterion": "Replay agrees",
    }]

    with pytest.raises(SetupError, match="stopped by an open uncertainty case"):
        guard_dispatch(payload, receipt, "M07", problem_id="P-setup")


@pytest.mark.parametrize("surface", ["codex", "claude", "vscode-openrouter"])
def test_cli_start_is_machine_readable_read_only_and_conservative(surface: str) -> None:
    before = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    result = subprocess.run(
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
    after = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    receipt = json.loads(result.stdout)
    assert receipt["stage"] == "startup-admitted"
    setup = receipt["setup_contract"]
    assert setup["surface"] == surface
    assert setup["routing_request"]["capabilities"]["supports_parallel"] is False
    assert setup["routing_request"]["capabilities"]["supports_cancellation"] is False
    assert setup["route_decision"]["action"] == "delegate"
    assert setup["orchestration_policy"]["parallel_required"] is False
    assert before == after


def test_hook_lifecycle_freezes_first_prompt_and_denies_missing_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    base = {"session_id": "session-1", "cwd": str(REPO_ROOT)}

    denied = handle_hook({**base, "hook_event_name": "PreToolUse"}, surface="codex", event="PreToolUse")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"

    submitted = handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "  Primary objective  "},
        surface="codex",
        event="UserPromptSubmit",
    )
    assert "Primary objective" in submitted["hookSpecificOutput"]["additionalContext"]

    allowed = handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        surface="codex",
        event="PreToolUse",
    )
    assert "permissionDecision" not in allowed["hookSpecificOutput"]
    assert "Primary objective" in allowed["hookSpecificOutput"]["additionalContext"]
    assert "dispatch independent workers immediately" in allowed["hookSpecificOutput"]["additionalContext"]

    followup = handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Push an unrelated release"},
        surface="codex",
        event="UserPromptSubmit",
    )
    assert "remains frozen" in followup["hookSpecificOutput"]["additionalContext"]
    assert "Primary objective" in followup["hookSpecificOutput"]["additionalContext"]
    assert "dispatch independent workers immediately" in followup["hookSpecificOutput"]["additionalContext"]

    cleared = handle_hook(
        {**base, "hook_event_name": "SessionStart", "source": "clear"},
        surface="codex",
        event="SessionStart",
    )
    assert "cleared the prior objective lock" in cleared["hookSpecificOutput"]["additionalContext"]
    denied_after_clear = handle_hook(
        {**base, "hook_event_name": "PreToolUse"}, surface="codex", event="PreToolUse"
    )
    assert denied_after_clear["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize(
    ("surface", "parallel_expected"),
    [("codex", True), ("claude", False)],
)
def test_fresh_hook_session_routes_substantive_work_to_parallel_fanout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, surface: str, parallel_expected: bool
) -> None:
    """A host may claim parallel capacity only when its signed adapter exists."""
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    base = {"session_id": "fresh-parallel-window", "cwd": str(REPO_ROOT)}

    submitted = handle_hook(
        {
            **base,
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Repair the harness, test the runtime, and independently review the result",
        },
        surface=surface,
        event="UserPromptSubmit",
    )

    state_path = setup_driver_module._state_path(REPO_ROOT.resolve(), base["session_id"])
    receipt = json.loads(state_path.read_text(encoding="utf-8"))["receipt"]
    contract = receipt["setup_contract"]
    assert contract["routing_request"]["capabilities"]["supports_parallel"] is parallel_expected
    assert contract["routing_request"]["capabilities"]["supports_cancellation"] is parallel_expected
    assert contract["orchestration_policy"]["parallel_required"] is parallel_expected
    assert contract["orchestration_policy"]["requires_disjoint_ownership_proof"] is True
    context = submitted["hookSpecificOutput"]["additionalContext"]
    if parallel_expected:
        assert contract["routing_request"]["signals"]["ownership_disjoint"] is False
        assert contract["route_decision"]["action"] == "delegate"
        assert contract["route_decision"]["execution"]["max_parallel_workers"] == 4
        assert "parallel-first-capacity-pending-disjoint-proof" in contract["route_decision"]["reasons"]
        assert contract["orchestration_policy"]["root_mutation_authority"] is False
        assert "dispatch independent workers immediately" in context
        assert "Do not begin root implementation first" in context
    else:
        assert "dispatch independent workers immediately" not in context


def test_parallel_required_root_cannot_implement_but_can_dispatch_and_coordinate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    base = {"session_id": "parallel-root-boundary", "cwd": str(REPO_ROOT)}
    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Repair and verify the harness"},
        surface="codex",
        event="UserPromptSubmit",
    )

    for tool_name, tool_input in (
        ("Write", {"file_path": "app.py"}),
        ("Edit", {"file_path": "app.py"}),
        ("apply_patch", {"patch": "*** Begin Patch"}),
    ):
        denied = handle_hook(
            {**base, "hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input},
            surface="codex",
            event="PreToolUse",
        )
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "denied root implementation" in denied["hookSpecificOutput"]["permissionDecisionReason"]

    proof = handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "exec_command", "tool_input": {"cmd": "pytest -q"}},
        surface="codex",
        event="PreToolUse",
    )
    assert "permissionDecision" not in proof["hookSpecificOutput"]

    for tool_name in ("spawn_agent", "followup_task", "agent", "task"):
        denied = handle_hook(
            {**base, "hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": {}},
            surface="codex",
            event="PreToolUse",
        )
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "denied root implementation" in denied["hookSpecificOutput"]["permissionDecisionReason"]

    for tool_name in (
        "wait_agent",
        "list_agents",
        "interrupt_agent",
        "send_message",
        # The actual host emits PascalCase labels.  These must retain the same
        # coordination-only authority as the portable snake_case names.
        "WaitAgent",
        "ListAgents",
        "InterruptAgent",
        "SendMessage",
    ):
        allowed = handle_hook(
            {**base, "hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": {}},
            surface="codex",
            event="PreToolUse",
        )
        assert "permissionDecision" not in allowed["hookSpecificOutput"]

    dispatch = handle_hook(
        {
            **base,
            "hook_event_name": "PreToolUse",
            "tool_name": "senior-harness.dispatch",
            "tool_input": {"node_id": "1.1"},
        },
        surface="codex",
        event="PreToolUse",
    )
    assert dispatch["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "signed" in dispatch["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        "ruff check --fix app.py",
        "ruff format app.py",
        "pytest --junitxml=app.py",
        "pytest --basetemp=app",
        "pytest /tmp/attacker_owned_test.py",
        "pytest tests/../../tmp/attacker_owned_test.py",
        "pytest tests/{../app.py,test_ok.py}",
        "./attacker/pytest -q",
        "pnpm test -- --update",
    ],
)
def test_parallel_root_denies_mutating_or_unbounded_verifier_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    base = {"session_id": f"unsafe-verifier-{abs(hash(command))}", "cwd": str(REPO_ROOT)}
    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Repair and verify the harness"},
        surface="codex",
        event="UserPromptSubmit",
    )
    denied = handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "exec_command", "tool_input": {"cmd": command}},
        surface="codex",
        event="PreToolUse",
    )
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"


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
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "/grill-me shape recovery"},
        surface="claude",
        event="UserPromptSubmit",
    )
    state_path = setup_driver_module._state_path(REPO_ROOT.resolve(), base["session_id"])
    contract = json.loads(state_path.read_text(encoding="utf-8"))["receipt"]["setup_contract"]
    assert contract["orchestration_policy"]["parallel_required"] is False
    context = submitted["hookSpecificOutput"]["additionalContext"]
    assert "dispatch independent workers immediately" not in context
    assert "worker dispatch remain denied" in context


def test_hook_allows_only_exact_recovery_safe_reads_without_startup_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    base = {"session_id": "recovery-no-state", "cwd": str(REPO_ROOT), "hook_event_name": "PreToolUse"}

    for tool_name in (
        "Read",
        "ToolSearch",
        "ReadMcpResource",
        "mcp__exa__web_search_exa",
        "mcp__plugin_exa_exa__get_code_context_exa",
    ):
        result = handle_hook({**base, "tool_name": tool_name, "tool_input": {}}, surface="claude", event="PreToolUse")
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
        denied = handle_hook(
            {**base, "tool_name": tool_name, "tool_input": tool_input},
            surface="claude",
            event="PreToolUse",
        )
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_invalid_startup_state_allows_recovery_read_but_denies_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "state"
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(state_root))
    base = {"session_id": "recovery-invalid", "cwd": str(REPO_ROOT)}
    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Inspect the invalid state"},
        surface="claude",
        event="UserPromptSubmit",
    )
    state_path = next(state_root.rglob("*.json"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["receipt"]["stage"] = "tampered"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    read_result = handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        surface="claude",
        event="PreToolUse",
    )
    assert "permissionDecision" not in read_result["hookSpecificOutput"]
    assert "startup state is invalid" in read_result["hookSpecificOutput"]["additionalContext"]

    write_result = handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {}},
        surface="claude",
        event="PreToolUse",
    )
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
    assert "bound skill changed after startup admission" in first_read["hookSpecificOutput"]["additionalContext"]

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["first_tool_admitted"] is False

    first_write = _pretool(base, "Write")
    assert first_write["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "bound skill changed after startup admission" in first_write["hookSpecificOutput"]["permissionDecisionReason"]


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
    assert "setup driver changed after startup admission" in denied["hookSpecificOutput"]["permissionDecisionReason"]


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
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Continue the same objective"},
        surface="claude",
        event="UserPromptSubmit",
    )
    assert "Control-code drift is present" in followup["hookSpecificOutput"]["additionalContext"]


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
    assert "setup driver digest is missing or malformed" in binding_result.integrity_failures
    assert "bound skill changed after startup admission: senior-harness" in binding_result.drift

    denied = _pretool(base, "Write")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "setup driver digest is missing or malformed" in denied["hookSpecificOutput"]["permissionDecisionReason"]

    recovery_read = _pretool(base, "Read")
    assert "permissionDecision" not in recovery_read["hookSpecificOutput"]
    assert "recovery-only read" in recovery_read["hookSpecificOutput"]["additionalContext"]
    assert "setup driver digest is missing or malformed" in recovery_read["hookSpecificOutput"]["additionalContext"]


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
    assert "setup driver changed after startup admission" in denied["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize(
    ("objective", "interaction"),
    [
        ("/grill-me shape recovery", "grill-me"),
        ("  $grill-me shape recovery", "grill-me"),
        ("/grill-with-docs shape recovery", "grill-with-docs"),
        ("\t$grill-with-docs shape recovery", "grill-with-docs"),
        ("/grill-me: shape recovery", "grill-me"),
        ("Discuss /grill-me without invoking it", "delivery"),
    ],
)
def test_interaction_is_derived_from_the_exact_objective_prefix(
    objective: str, interaction: str
) -> None:
    receipt = admit_startup(
        build_setup_contract(objective, REPO_ROOT, surface="codex", interaction=interaction)
    )
    assert validate_startup_receipt(receipt)["status"] == "valid"


def test_trusted_reissued_receipt_still_cannot_mismatch_grill_interaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state",
        monkeypatch,
        session_id="rewritten-grill-interaction",
        prompt="$grill-with-docs shape recovery",
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["receipt"]["setup_contract"]["interaction"] = "delivery"
    _rehash_receipt(state["receipt"])
    state_path.write_text(json.dumps(state), encoding="utf-8")

    denied = _pretool(base, "Write")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "interaction does not match the frozen literal objective" in denied["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("shape", [[], "scalar"], ids=["list", "scalar"])
@pytest.mark.parametrize("layer", ["state", "receipt", "setup-contract"])
def test_non_object_startup_layers_enter_the_deterministic_invalid_state_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    layer: str,
    shape: object,
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state", monkeypatch, session_id=f"shape-{layer}-{type(shape).__name__}"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if layer == "state":
        stored: object = shape
    elif layer == "receipt":
        state["receipt"] = shape
        stored = state
    else:
        state["receipt"]["setup_contract"] = shape
        unsigned_receipt = dict(state["receipt"])
        unsigned_receipt.pop("receipt_integrity_digest")
        state["receipt"]["receipt_integrity_digest"] = digest(unsigned_receipt)
        stored = state
    state_path.write_text(json.dumps(stored), encoding="utf-8")

    recovery_read = _pretool(base, "Read")
    assert "permissionDecision" not in recovery_read["hookSpecificOutput"]
    assert "recovery-only read" in recovery_read["hookSpecificOutput"]["additionalContext"]
    denied = _pretool(base, "Write")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "invalid startup state" in denied["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("target", ["folder", "driver"])
@pytest.mark.parametrize(
    ("case", "malformed"),
    [
        ("missing", None),
        ("object", {"digest": "sha256:" + "0" * 64}),
        ("upper-case", "sha256:" + "A" * 64),
        ("short", "sha256:abc"),
        ("wrong-prefix", "sha512:" + "0" * 64),
    ],
)
def test_malformed_binding_digests_deny_mutation_after_public_rehash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    case: str,
    malformed: object,
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state", monkeypatch, session_id=f"malformed-{target}-{case}"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    receipt = state["receipt"]
    if target == "folder":
        binding = receipt["setup_contract"]["required_skills"]["senior-harness"]
        key = "folder_digest"
    else:
        binding = receipt
        key = "driver_digest"
    if case == "missing":
        binding.pop(key)
    else:
        binding[key] = malformed
    _rehash_receipt(receipt)
    state_path.write_text(json.dumps(state), encoding="utf-8")

    denied = _pretool(base, "Write")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "digest is missing or malformed" in denied["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("skills-list", "no required-skill evidence"),
        ("skill-list", "missing skill senior-harness"),
        ("missing-path", "path is missing or invalid"),
        ("object-path", "path is missing or invalid"),
        ("relative-path", "path is missing or invalid"),
        ("unavailable-path", "skill is unavailable or invalid"),
        ("wrong-name", "skill name is missing or invalid"),
    ],
)
def test_malformed_or_unavailable_skill_bindings_deny_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected_error: str,
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state", monkeypatch, session_id=f"binding-{case}"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    receipt = state["receipt"]
    skills = receipt["setup_contract"]["required_skills"]
    if case == "skills-list":
        receipt["setup_contract"]["required_skills"] = []
    elif case == "skill-list":
        skills["senior-harness"] = []
    elif case == "missing-path":
        skills["senior-harness"].pop("path")
    elif case == "object-path":
        skills["senior-harness"]["path"] = {"path": str(REPO_ROOT)}
    elif case == "relative-path":
        skills["senior-harness"]["path"] = "skills/senior-harness"
    elif case == "unavailable-path":
        skills["senior-harness"]["path"] = str(tmp_path / "missing-skill")
    else:
        skills["senior-harness"]["name"] = "delivery"
    _rehash_receipt(receipt)
    state_path.write_text(json.dumps(state), encoding="utf-8")

    denied = _pretool(base, "Write")
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert expected_error in denied["hookSpecificOutput"]["permissionDecisionReason"]

    recovery_read = _pretool(base, "Read")
    assert "permissionDecision" not in recovery_read["hookSpecificOutput"]
    assert "recovery-only read" in recovery_read["hookSpecificOutput"]["additionalContext"]


def test_invalid_utf8_bound_skill_enters_recovery_or_deny_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, state_path = _start_hook_session(
        tmp_path / "state", monkeypatch, session_id="invalid-utf8-skill"
    )
    invalid_skill = tmp_path / "invalid-senior-harness"
    invalid_skill.mkdir()
    (invalid_skill / "SKILL.md").write_bytes(
        b"---\nname: senior-harness\n---\ninvalid utf-8: \xff\n"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    receipt = state["receipt"]
    binding = receipt["setup_contract"]["required_skills"]["senior-harness"]
    binding["path"] = str(invalid_skill)
    binding["folder_digest"] = setup_driver_module._folder_digest(invalid_skill)
    _rehash_receipt(receipt)
    state_path.write_text(json.dumps(state), encoding="utf-8")

    recovery_read = _pretool(base, "Read")
    read_output = recovery_read["hookSpecificOutput"]
    assert "permissionDecision" not in read_output
    assert "recovery-only read" in read_output["additionalContext"]
    assert "grants no mutation" in read_output["additionalContext"]
    assert "bound skill is unavailable or invalid: senior-harness" in read_output["additionalContext"]

    denied = _pretool(base, "Write")
    deny_output = denied["hookSpecificOutput"]
    assert deny_output["permissionDecision"] == "deny"
    assert "bound skill is unavailable or invalid: senior-harness" in deny_output["permissionDecisionReason"]


def test_hook_rejects_malformed_or_mismatched_input() -> None:
    with pytest.raises(SetupError, match="missing session_id"):
        handle_hook({}, surface="claude", event="PreToolUse")
    with pytest.raises(SetupError, match="event mismatch"):
        handle_hook(
            {"session_id": "s", "cwd": str(REPO_ROOT), "hook_event_name": "SessionStart"},
            surface="claude",
            event="PreToolUse",
        )


def test_project_hook_manifests_preserve_existing_claude_gate() -> None:
    codex = json.loads((REPO_ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    claude = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))

    for manifest in (codex, claude):
        assert {"SessionStart", "UserPromptSubmit", "PreToolUse"} <= set(manifest["hooks"])
    claude_pretool_commands = [
        hook["command"]
        for group in claude["hooks"]["PreToolUse"]
        for hook in group["hooks"]
    ]
    assert any("setup_driver.py" in command for command in claude_pretool_commands)
    assert any("autonomy_gate_hook.py" in command for command in claude_pretool_commands)


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


def test_global_hook_can_skip_non_git_tasks_without_making_an_admission_claim(tmp_path: Path) -> None:
    payload = json.dumps({
        "session_id": "outside-git",
        "cwd": str(tmp_path),
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
    })
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


def _global_hook(event: str, payload: dict, env: dict[str, str]) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "setup_driver.py"),
            "hook",
            "--surface",
            "claude",
            "--event",
            event,
            "--allow-non-git",
        ],
        input=json.dumps({**payload, "hook_event_name": event}),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["hookSpecificOutput"]


def test_global_hook_recovers_original_prompt_after_entering_git(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    outside = tmp_path / "outside"
    outside.mkdir()
    env = dict(
        os.environ,
        SENIOR_HARNESS_STATE_DIR=str(state_root),
        SENIOR_HARNESS_SEAL_KEY_FILE=str(tmp_path / "seal.key"),
    )
    prompt = "Repair the startup receipt loop"

    submitted = _global_hook(
        "UserPromptSubmit",
        {
            "session_id": "outside-then-git",
            "cwd": str(outside),
            "prompt": prompt,
        },
        env,
    )
    assert "pending" in submitted["additionalContext"]
    repeated = _global_hook(
        "UserPromptSubmit",
        {"session_id": "outside-then-git", "cwd": str(outside), "prompt": "Replace it"},
        env,
    )
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


def test_grill_interaction_binds_skill_and_routes_as_research() -> None:
    contract = build_setup_contract(
        "/grill-me shape the recovery workflow",
        REPO_ROOT,
        surface="codex",
        interaction="grill-me",
    )

    assert contract["interaction"] == "grill-me"
    assert contract["required_skills"]["grill-me"]["name"] == "grill-me"
    assert contract["routing_request"]["signals"]["modalities"] == ["text"]
    assert contract["routing_request"]["signals"]["required_tools"] == ["read", "research"]


def test_grill_hook_denies_project_action_but_allows_evidence_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    base = {"session_id": "grill-1", "cwd": str(REPO_ROOT)}
    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "/grill-me shape recovery"},
        surface="codex",
        event="UserPromptSubmit",
    )

    read_result = handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "CONTEXT.md"}},
        surface="codex",
        event="PreToolUse",
    )
    assert "permissionDecision" not in read_result["hookSpecificOutput"]

    search_result = handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "exec_command", "tool_input": {"cmd": "rg -n recovery CONTEXT.md"}},
        surface="codex",
        event="PreToolUse",
    )
    assert "permissionDecision" not in search_result["hookSpecificOutput"]

    for tool_name, tool_input in (
        ("Edit", {"file_path": "CONTEXT.md"}),
        ("exec_command", {"cmd": "git push origin main"}),
        ("exec_command", {"cmd": "rg recovery $(touch escaped)"}),
        ("exec_command", {"cmd": "sed -i backup CONTEXT.md"}),
        ("exec_command", {"cmd": "sed -n 'w /tmp/grill-sed-write' CONTEXT.md"}),
        ("exec_command", {"cmd": "git diff --output=escaped.diff"}),
        ("exec_command", {"cmd": "python3 /tmp/grill_session.py show --state /tmp/state.json"}),
        ("mcp__attacker__read", {"action": "mutate"}),
        ("spawn_agent", {"task": "change the project"}),
    ):
        denied = handle_hook(
            {**base, "hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input},
            surface="codex",
            event="PreToolUse",
        )
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_grill_blocks_dispatch_until_exact_shared_understanding_and_sketch_remains_bound(tmp_path: Path) -> None:
    objective = "/grill-me shape recovery"
    receipt = admit_startup(
        build_setup_contract(objective, REPO_ROOT, surface="codex", interaction="grill-me")
    )
    payload = _delivery(objective)
    for move in payload["move_graph"][:6]:
        move["status"] = "passed"
    payload["move_graph"][6]["status"] = "ready"
    sketch = tmp_path / "vault" / "Sketches" / "01-recovery.md"
    sketch.parent.mkdir(parents=True)
    sketch.write_text("# Recovery\n", encoding="utf-8")
    target = sketch.parent.parent / "Grills" / "01-recovery.md"
    grill = start_session(
        objective,
        sketch,
        [{
            "leaf_id": "market",
            "kind": "human-decision",
            "depends_on": [],
            "question": "Which market ships first?",
            "recommendation": "Start with the internal proving ground.",
            "rationale": "It produces evidence before external commitments.",
        }],
        materialization_path=target,
    )

    with pytest.raises(SetupError, match="shared-understanding session"):
        guard_dispatch(payload, receipt, "M07")
    with pytest.raises(SetupError, match="shared understanding is confirmed"):
        guard_dispatch(payload, receipt, "M07", grill_session=grill)

    grill = answer_pending_question(grill, "Internal proving ground first.", "DECIDED")
    grill = confirm_shared_understanding(grill, SHARED_UNDERSTANDING_PHRASE)
    assert guard_dispatch(payload, receipt, "M07", grill_session=grill)["status"] == "admitted"
    with pytest.raises(SetupError, match="cannot authorize mutating"):
        guard_dispatch(payload, receipt, "M12", grill_session=grill)

    sketch.write_text("# Drifted recovery\n", encoding="utf-8")
    with pytest.raises(SetupError, match="sketch changed"):
        guard_dispatch(payload, receipt, "M07", grill_session=grill)


def test_explicit_grill_setup_admits_a_fresh_external_project(tmp_path: Path) -> None:
    project = tmp_path / "fresh-project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True)
    (project / "README.md").write_text("# Fresh project\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=project, check=True)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "setup_driver.py"),
            "start",
            "/grill-me shape the fresh project",
            "--project",
            str(project),
            "--surface",
            "codex",
            "--interaction",
            "grill-me",
            "--strict-clean",
            "--skill-root",
            str(REPO_ROOT / "skills"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    setup = json.loads(result.stdout)["setup_contract"]
    assert setup["repository"]["worktree"] == str(project.resolve())
    assert setup["repository"]["dirty"] is False
    assert setup["interaction"] == "grill-me"
    assert set(setup["required_skills"]) == {"senior-harness", "model-router", "unlazy", "grill-me"}


def test_grill_hook_rechecks_project_bytes_after_first_tool_and_session_ids_do_not_collide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "hook-project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True)
    tracked = project / "README.md"
    tracked.write_text("# Base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=project, check=True)
    state_root = tmp_path / "state"
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(state_root))

    for session_id in ("a/b", "a_b"):
        base = {"session_id": session_id, "cwd": str(project)}
        handle_hook(
            {**base, "hook_event_name": "UserPromptSubmit", "prompt": "/grill-me shape hook project"},
            surface="codex",
            event="UserPromptSubmit",
        )
    assert len(list(state_root.rglob("*.json"))) == 2

    base = {"session_id": "a/b", "cwd": str(project)}
    first = handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        surface="codex",
        event="PreToolUse",
    )
    assert "permissionDecision" not in first["hookSpecificOutput"]
    tracked.write_text("# Drifted\n", encoding="utf-8")
    second = handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        surface="codex",
        event="PreToolUse",
    )
    assert "permissionDecision" not in second["hookSpecificOutput"]
    assert "recovery-only read" in second["hookSpecificOutput"]["additionalContext"]
    assert "worktree_state_digest changed" in second["hookSpecificOutput"]["additionalContext"]

    denied_write = handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {}},
        surface="codex",
        event="PreToolUse",
    )
    assert denied_write["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "worktree_state_digest changed" in denied_write["hookSpecificOutput"]["permissionDecisionReason"]
