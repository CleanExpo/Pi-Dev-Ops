from __future__ import annotations

import copy
import json
import os
import shlex
import stat
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
from senior_harness import ContractError, digest, validate_contract  # noqa: E402
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


def _checkout_base_sha(head: str) -> str:
    """The deepest ancestor of HEAD that this checkout actually contains.

    The fixture ships a literal base commit, but the contract requires
    ``repository.base_sha`` to resolve *inside* ``repository.worktree`` and to be an
    ancestor of the candidate.  CI runs ``actions/checkout`` at its default depth of 1,
    so neither the pinned commit nor ``HEAD~1`` exists there and every delivery test
    fails on an ancestry rule it was never meant to exercise.

    Prefer a genuine parent so base and candidate stay distinct wherever history is
    present, and fall back to HEAD only in a shallow checkout, where HEAD is the sole
    commit and therefore the only base that can satisfy the rule at all.  The rule
    itself is covered on its own terms by the hermetic repository tests below, which
    build their own history instead of depending on how the host cloned this one.
    """
    parent = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD~1^{commit}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    resolved = parent.stdout.strip()
    return resolved if parent.returncode == 0 and resolved else head


def _delivery(objective: str = "Create the setup driver") -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["literal_request"] = objective
    payload["authorized_scope"] = [objective]
    payload["task_id"] = digest({"task": objective})[7:23]
    payload["repository"]["worktree"] = str(REPO_ROOT)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    payload["repository"]["candidate_sha"] = head
    payload["repository"]["base_sha"] = _checkout_base_sha(head)
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


def _observe_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, surface: str = "codex"
) -> Path:
    """Publish an observed adapter receipt so the surface may claim capacity.

    Hook presence alone proves nothing, so the parallel regime is unreachable
    without this receipt.  Tests that exercise the regime must observe an
    adapter first, exactly as a real host would.
    """
    receipt_path = tmp_path / f"{surface}-adapter-receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "surface": surface,
                "capacity": True,
                "isolation": True,
                "signed_dispatch": True,
                "cancellation": True,
                "adapter_signature": "test-observed-adapter-signature",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(setup_driver_module.ADAPTER_RECEIPT_ENV, str(receipt_path))
    return receipt_path


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
    _observe_adapter(tmp_path, monkeypatch)
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
    monkeypatch.setenv(setup_driver_module.ADAPTER_RECEIPT_ENV, str(tmp_path / "absent.json"))
    assert setup_driver_module._read_adapter_receipt("codex") is None

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(setup_driver_module.ADAPTER_RECEIPT_ENV, str(broken))
    assert setup_driver_module._read_adapter_receipt("codex") is None

    monkeypatch.delenv(setup_driver_module.ADAPTER_RECEIPT_ENV, raising=False)
    assert setup_driver_module._read_adapter_receipt("codex") is None


@pytest.mark.parametrize(
    ("surface", "observed_adapter", "parallel_expected"),
    [
        # Codex with an observed adapter receipt is the only capacity claim.
        ("codex", True, True),
        # Planted: configured hooks and no observed adapter.  Hook presence is
        # not a probe, so this must fail closed to serial rather than reserve
        # parallel capacity the host was never measured to have.
        ("codex", False, False),
        # A receipt cannot buy Claude capacity it has no signed dispatch for.
        ("claude", True, False),
        ("claude", False, False),
    ],
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
    _observe_adapter(tmp_path, monkeypatch)
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
    _observe_adapter(tmp_path, monkeypatch)
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

    # The project under test is a throwaway checkout, so name this repository's
    # canonical skills root explicitly instead of relying on a host install that a
    # clean CI HOME does not have.
    roots = [REPO_ROOT / "skills"]

    for session_id in ("a/b", "a_b"):
        base = {"session_id": session_id, "cwd": str(project)}
        handle_hook(
            {**base, "hook_event_name": "UserPromptSubmit", "prompt": "/grill-me shape hook project"},
            surface="codex",
            event="UserPromptSubmit",
            skill_search_roots=roots,
        )
    assert len(list(state_root.rglob("*.json"))) == 2

    base = {"session_id": "a/b", "cwd": str(project)}
    first = handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        surface="codex",
        event="PreToolUse",
        skill_search_roots=roots,
    )
    assert "permissionDecision" not in first["hookSpecificOutput"]
    tracked.write_text("# Drifted\n", encoding="utf-8")
    second = handle_hook(
        {**base, "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        surface="codex",
        event="PreToolUse",
        skill_search_roots=roots,
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


def _global_hook_result(event: str, payload: dict, env: dict[str, str]) -> dict:
    """Full driver output, including the top-level refusal channel."""
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
    return json.loads(result.stdout)


def _tamper_env(tmp_path: Path) -> dict[str, str]:
    return dict(
        os.environ,
        SENIOR_HARNESS_STATE_DIR=str(tmp_path / "state"),
        SENIOR_HARNESS_SEAL_KEY_FILE=str(tmp_path / "seal.key"),
    )


def _pending_file(tmp_path: Path) -> Path:
    pending = list((tmp_path / "state" / "pending-project").glob("*.json"))
    assert len(pending) == 1, pending
    return pending[0]


def test_a_later_prompt_cannot_launder_a_tampered_pending_objective(tmp_path: Path) -> None:
    """tampered state -> another prompt -> first tool attempt stays denied."""
    env = _tamper_env(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    session = "tamper-then-prompt"

    _global_hook(
        "UserPromptSubmit",
        {"session_id": session, "cwd": str(outside), "prompt": "Inspect only"},
        env,
    )
    pending_path = _pending_file(tmp_path)
    tampered = json.loads(pending_path.read_text(encoding="utf-8"))
    tampered["literal_objective"] = "Deploy instead"
    pending_path.write_text(json.dumps(tampered), encoding="utf-8")

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

    # The tampered record is preserved verbatim: neither prompt overwrote it, and
    # neither prompt was promoted into an objective of its own.
    assert json.loads(pending_path.read_text(encoding="utf-8")) == tampered
    assert not setup_driver_module._state_path(REPO_ROOT.resolve(), session).exists()

    for tool in ("Write", "Bash", "Read"):
        denied = _global_hook(
            "PreToolUse",
            {
                "session_id": session,
                "cwd": str(REPO_ROOT),
                "tool_name": tool,
                "tool_input": {},
            },
            env,
        )
        assert denied["permissionDecision"] == "deny", tool
        assert "pending startup objective is invalid" in denied["permissionDecisionReason"]
    assert not setup_driver_module._state_path(REPO_ROOT.resolve(), session).exists()


def test_session_start_clear_is_the_one_recovery_from_a_tampered_pending_objective(
    tmp_path: Path,
) -> None:
    """Positive control: the terminal denial is escapable exactly as documented."""
    env = _tamper_env(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    session = "tamper-then-clear"

    _global_hook(
        "UserPromptSubmit",
        {"session_id": session, "cwd": str(outside), "prompt": "Inspect only"},
        env,
    )
    pending_path = _pending_file(tmp_path)
    tampered = json.loads(pending_path.read_text(encoding="utf-8"))
    tampered["literal_objective"] = "Deploy instead"
    pending_path.write_text(json.dumps(tampered), encoding="utf-8")

    denied = _global_hook(
        "PreToolUse",
        {"session_id": session, "cwd": str(REPO_ROOT), "tool_name": "Write", "tool_input": {}},
        env,
    )
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

    admitted = _global_hook(
        "PreToolUse",
        {"session_id": session, "cwd": str(REPO_ROOT), "tool_name": "Read", "tool_input": {}},
        env,
    )
    assert "permissionDecision" not in admitted
    assert "recovered pending objective" in admitted["additionalContext"]
    assert repr(recovered_prompt) in admitted["additionalContext"]


def _grill_command(*argv: str) -> dict:
    return {
        "session_id": "grill-classification",
        "cwd": str(REPO_ROOT),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": shlex.join(
                [sys.executable, str(SCRIPT_DIR / "grill_session.py"), *argv]
            )
        },
    }


def test_recovery_read_admits_only_the_read_only_grill_subcommands() -> None:
    for command in sorted(setup_driver_module.GRILL_READ_ONLY_COMMANDS):
        payload = _grill_command(command, "--state", "/tmp/grill-state.json")
        assert setup_driver_module._tool_is_recovery_safe(payload) is True, command


def test_recovery_read_denies_every_state_writing_grill_subcommand() -> None:
    for command in ("start", "evidence", "answer", "confirm", "materialize"):
        payload = _grill_command(command, "--state", "/tmp/grill-state.json")
        assert setup_driver_module._tool_is_recovery_safe(payload) is False, command
    # A bare invocation and an unrecognised subcommand are denied by omission.
    assert setup_driver_module._tool_is_recovery_safe(_grill_command()) is False
    assert setup_driver_module._tool_is_recovery_safe(_grill_command("purge")) is False


def test_grill_read_only_allowlist_tracks_the_grill_cli(tmp_path: Path) -> None:
    """Every shipped subcommand is classified, and new ones are denied by default."""
    import argparse

    import grill_session as grill_session_module

    subparsers = [
        action
        for action in grill_session_module._parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparsers) == 1
    shipped = set(subparsers[0].choices)
    assert setup_driver_module.GRILL_READ_ONLY_COMMANDS <= shipped
    for command in sorted(shipped - setup_driver_module.GRILL_READ_ONLY_COMMANDS):
        assert setup_driver_module._tool_is_recovery_safe(_grill_command(command)) is False, command


def test_allowlisted_grill_subcommands_do_not_write_state_but_denied_ones_do(
    tmp_path: Path,
) -> None:
    """Prove the classification against the real CLI rather than trusting its name."""
    sketch = tmp_path / "Sketches" / "01-recovery.md"
    sketch.parent.mkdir(parents=True)
    sketch.write_text("# Recovery\n", encoding="utf-8")
    session = start_session(
        "Shape the recovery",
        sketch,
        [{
            "leaf_id": "market",
            "kind": "human-decision",
            "depends_on": [],
            "question": "Which market ships first?",
            "recommendation": "Start with the internal proving ground.",
            "rationale": "It produces evidence before external commitments.",
        }],
        materialization_path=sketch.parent.parent / "Grills" / "01-recovery.md",
    )
    control_root = tmp_path / "state"
    control_root.mkdir()
    env = dict(os.environ, SENIOR_HARNESS_STATE_DIR=str(control_root))
    state_path = control_root / "grill-state.json"
    state_path.write_text(json.dumps(session, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    before = state_path.read_bytes()

    for command in sorted(setup_driver_module.GRILL_READ_ONLY_COMMANDS):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "grill_session.py"), command, "--state", str(state_path)],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (command, result.stderr)
        assert state_path.read_bytes() == before, command

    answered = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "grill_session.py"),
            "answer",
            "--state",
            str(state_path),
            "--answer",
            "Internal proving ground first.",
            "--resolution",
            "DECIDED",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert answered.returncode == 0, answered.stderr
    assert state_path.read_bytes() != before


def test_recovery_read_denies_a_grill_write_when_no_receipt_exists(tmp_path: Path) -> None:
    env = _tamper_env(tmp_path)
    for command, expect_deny in (("show", False), ("materialize", True)):
        payload = _grill_command(command, "--state", str(tmp_path / "grill-state.json"))
        payload["session_id"] = f"no-receipt-{command}"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "setup_driver.py"),
                "hook",
                "--surface",
                "claude",
                "--event",
                "PreToolUse",
            ],
            input=json.dumps(payload),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        output = json.loads(result.stdout)["hookSpecificOutput"]
        if expect_deny:
            assert output["permissionDecision"] == "deny", command
            assert "no startup receipt exists" in output["permissionDecisionReason"]
        else:
            assert "permissionDecision" not in output, command
            assert "recovery-only read" in output["additionalContext"]


# ── Regressions for the exact-SHA review findings ────────────────────────────


def _init_repo(project: Path) -> str:
    """Create a one-commit checkout owned by the caller and return its HEAD."""
    project.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True)
    (project / "README.md").write_text("# Base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=project, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_review_later_pending_objective_is_not_discarded_by_older_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A receipt proves integrity, never chronology.

    Admit an objective in a Git project, then seal a LATER objective for the same
    session while outside Git, then return to the project.  The receipt predates the
    pending record, so it cannot supersede it.  Before the fix the newer objective was
    silently deleted while the hook reported the older one still frozen.  Neither may
    be destroyed: the session blocks for explicit reconciliation.
    """
    project = tmp_path / "live-project"
    _init_repo(project)
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SENIOR_HARNESS_SEAL_KEY_FILE", str(tmp_path / "seal.key"))
    session_id = "orphaned-pending-session"
    roots = [REPO_ROOT / "skills"]
    base = {"session_id": session_id, "cwd": str(project)}

    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Older admitted objective"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )
    state_path = setup_driver_module._state_path(project.resolve(), session_id)
    assert state_path.is_file()

    outside = tmp_path / "outside-any-checkout"
    outside.mkdir()
    setup_driver_module._record_pending_objective(
        {
            "session_id": session_id,
            "cwd": str(outside),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Later pending objective",
        },
        surface="codex",
        event="UserPromptSubmit",
    )
    pending_path = setup_driver_module._pending_state_path(session_id)
    assert pending_path.is_file()

    blocked = handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "a later subordinate prompt"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )

    # The newer objective survives -- this is the assertion that failed before.
    assert pending_path.is_file()
    sealed = json.loads(pending_path.read_text(encoding="utf-8"))
    assert sealed["literal_objective"] == "Later pending objective"

    # UserPromptSubmit refuses through the top-level decision/reason pair.
    assert blocked["decision"] == "block"
    reason = blocked["reason"]
    assert reason == blocked["hookSpecificOutput"]["additionalContext"]
    assert "order cannot be established" in reason
    assert "Later pending objective" in reason
    assert "Older admitted objective" in reason
    # It must not claim the pending record was retired.
    assert "was retired" not in reason


@pytest.mark.parametrize("drop", ["admitted_at_ns", "recorded_at_ns"])
def test_unstamped_state_or_pending_record_blocks_instead_of_retiring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drop: str
) -> None:
    """Ordering must be proven, not assumed, when a stamp is absent.

    A state file or pending record written by an older driver carries no issuance
    stamp.  Absence of evidence is not evidence of supersession, so these must block
    for reconciliation rather than fall back to the old always-retire behaviour.
    """
    project = tmp_path / "live-project"
    _init_repo(project)
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SENIOR_HARNESS_SEAL_KEY_FILE", str(tmp_path / "seal.key"))
    session_id = f"legacy-stamp-{drop}"
    roots = [REPO_ROOT / "skills"]
    base = {"session_id": session_id, "cwd": str(project)}

    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Admitted objective"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )
    state_path = setup_driver_module._state_path(project.resolve(), session_id)

    setup_driver_module._record_pending_objective(
        {
            "session_id": session_id,
            "cwd": str(tmp_path),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Pending objective",
        },
        surface="codex",
        event="UserPromptSubmit",
    )
    pending_path = setup_driver_module._pending_state_path(session_id)

    if drop == "admitted_at_ns":
        # Simulate a receipt from a driver predating the sealed order field: remove it
        # and re-seal, so the receipt is genuinely valid but carries no ordering proof.
        state = json.loads(state_path.read_text(encoding="utf-8"))
        receipt = state["receipt"]
        assert receipt.pop("admission_order_ns", None) is not None
        receipt.pop("receipt_integrity_digest", None)
        receipt.pop("receipt_seal", None)
        receipt["receipt_integrity_digest"] = digest(receipt)
        receipt["receipt_seal"] = setup_driver_module._receipt_seal(receipt)
        state_path.write_text(json.dumps(state), encoding="utf-8")
    else:
        # A legacy pending record: unstamped, but still correctly sealed.
        sealed = json.loads(pending_path.read_text(encoding="utf-8"))
        sealed.pop("recorded_at_ns", None)
        sealed["pending_seal"] = setup_driver_module._pending_objective_seal(sealed)
        pending_path.write_text(json.dumps(sealed), encoding="utf-8")

    blocked = handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "a later subordinate prompt"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )
    # Substantive claim first: the record survives.  Assert this before the output
    # shape so a regression fails on the destroyed record, not on a missing key.
    assert pending_path.is_file(), "an unstamped record must never be destroyed"
    assert blocked["decision"] == "block"
    assert "order cannot be established" in blocked["reason"]


def test_refusal_discloses_that_clear_discards_both_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stated operator exit must not understate what it destroys.

    The refusal points the operator at SessionStart source=clear.  That call unlinks
    the project state AND the pending record, so describing it as discarding only the
    pending record would understate a destructive action to the person about to run it.
    """
    project = tmp_path / "live-project"
    _init_repo(project)
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SENIOR_HARNESS_SEAL_KEY_FILE", str(tmp_path / "seal.key"))
    session_id = "clear-discloses-both"
    roots = [REPO_ROOT / "skills"]
    base = {"session_id": session_id, "cwd": str(project)}

    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Frozen project objective"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )
    state_path = setup_driver_module._state_path(project.resolve(), session_id)

    outside = tmp_path / "outside-any-checkout"
    outside.mkdir()
    setup_driver_module._record_pending_objective(
        {
            "session_id": session_id,
            "cwd": str(outside),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Pending objective",
        },
        surface="codex",
        event="UserPromptSubmit",
    )
    pending_path = setup_driver_module._pending_state_path(session_id)

    blocked = handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "a later subordinate prompt"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )
    reason = blocked["reason"]
    assert "DISCARDS BOTH" in reason
    assert "pending" in reason and "receipt" in reason

    # Positive control: the disclosure is accurate, both files really do go.
    assert state_path.is_file() and pending_path.is_file()
    handle_hook(
        {**base, "hook_event_name": "SessionStart", "source": "clear"},
        surface="codex",
        event="SessionStart",
        skill_search_roots=roots,
    )
    assert not state_path.is_file(), "clear removes the project state too"
    assert not pending_path.is_file(), "clear removes the pending record"


def test_clock_rollback_between_writes_cannot_delete_the_later_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wall-clock samples are not chronology, so they must not authorise deletion.

    ``time.time_ns`` reads CLOCK_REALTIME, which this host reports as adjustable and
    non-monotonic.  If the earlier admission happens to sample a LARGER value than the
    later pending write, a comparison-based rule reads the newer record as older and
    destroys it.  Both records are produced through the normal integrity-covered paths
    here: nothing is forged, the clock simply moved.
    """
    project = tmp_path / "live-project"
    _init_repo(project)
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SENIOR_HARNESS_SEAL_KEY_FILE", str(tmp_path / "seal.key"))
    session_id = "clock-rollback"
    roots = [REPO_ROOT / "skills"]
    base = {"session_id": session_id, "cwd": str(project)}

    monkeypatch.setattr(setup_driver_module.time, "time_ns", lambda: 200)
    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Older admitted objective"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )

    # The clock is adjusted backwards before the later write.
    monkeypatch.setattr(setup_driver_module.time, "time_ns", lambda: 100)
    outside = tmp_path / "outside-any-checkout"
    outside.mkdir()
    setup_driver_module._record_pending_objective(
        {
            "session_id": session_id,
            "cwd": str(outside),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Later pending objective",
        },
        surface="codex",
        event="UserPromptSubmit",
    )
    pending_path = setup_driver_module._pending_state_path(session_id)
    assert pending_path.is_file()

    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "a later subordinate prompt"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )

    assert pending_path.is_file(), (
        "a backwards clock adjustment must never delete the later sealed objective"
    )
    survived = json.loads(pending_path.read_text(encoding="utf-8"))
    assert survived["literal_objective"] == "Later pending objective"


def test_tampered_outer_admission_stamp_cannot_retire_a_newer_pending_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ordering evidence must live under the seal, not beside it.

    The state-file holder can rewrite any unsealed field -- the receipt seal exists
    precisely because that party is in the threat model.  Editing only the outer
    admission stamp, leaving the HMAC-sealed receipt untouched, must not be able to
    make an older admission look newer and delete a newer sealed objective.
    """
    project = tmp_path / "live-project"
    _init_repo(project)
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SENIOR_HARNESS_SEAL_KEY_FILE", str(tmp_path / "seal.key"))
    session_id = "outer-stamp-tamper"
    roots = [REPO_ROOT / "skills"]
    base = {"session_id": session_id, "cwd": str(project)}

    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Older admitted objective"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )
    state_path = setup_driver_module._state_path(project.resolve(), session_id)

    outside = tmp_path / "outside-any-checkout"
    outside.mkdir()
    setup_driver_module._record_pending_objective(
        {
            "session_id": session_id,
            "cwd": str(outside),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Later pending objective",
        },
        surface="codex",
        event="UserPromptSubmit",
    )
    pending_path = setup_driver_module._pending_state_path(session_id)
    sealed_pending = json.loads(pending_path.read_text(encoding="utf-8"))

    # Tamper with ONLY the unsealed outer field; the sealed receipt is untouched.
    state = json.loads(state_path.read_text(encoding="utf-8"))
    sealed_receipt_before = json.dumps(state["receipt"], sort_keys=True)
    state["admitted_at_ns"] = sealed_pending["recorded_at_ns"] + 1
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert json.dumps(
        json.loads(state_path.read_text(encoding="utf-8"))["receipt"], sort_keys=True
    ) == sealed_receipt_before, "the receipt itself must be unchanged by this tamper"

    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "a later subordinate prompt"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )

    assert pending_path.is_file(), (
        "a forged outer admission stamp must not retire the newer sealed objective"
    )
    survived = json.loads(pending_path.read_text(encoding="utf-8"))
    assert survived["literal_objective"] == "Later pending objective"


def test_even_a_genuinely_older_sealed_record_is_preserved_not_retired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retirement is removed entirely; this supersedes the old retire-on-order test.

    That test asserted a genuinely-older sealed record WAS deleted.  Deciding this
    needs an authoritative, rollback-resistant sequence.  One is constructible --
    a ledger beside the HMAC key, outside the state root -- but is not built yet,
    so no trusted order evidence is available at runtime.  Both stamps are CLOCK_REALTIME samples, so
    "genuinely older" is not something this code can establish.  The guarantee is now
    strictly stronger -- no sealed objective is ever destroyed automatically -- and the
    operator clears the record explicitly instead.
    """
    project = tmp_path / "live-project"
    _init_repo(project)
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SENIOR_HARNESS_SEAL_KEY_FILE", str(tmp_path / "seal.key"))
    session_id = "ordered-pending-session"
    roots = [REPO_ROOT / "skills"]
    base = {"session_id": session_id, "cwd": str(project)}

    outside = tmp_path / "outside-any-checkout"
    outside.mkdir()
    # Pin the clock rather than trusting CLOCK_REALTIME to advance between the two
    # writes: "genuinely earlier" must be a fact of the fixture, not of the host.
    monkeypatch.setattr(setup_driver_module.time, "time_ns", lambda: 100)
    setup_driver_module._record_pending_objective(
        {
            "session_id": session_id,
            "cwd": str(outside),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Genuinely earlier pending objective",
        },
        surface="codex",
        event="UserPromptSubmit",
    )
    pending_path = setup_driver_module._pending_state_path(session_id)
    sealed = json.loads(pending_path.read_text(encoding="utf-8"))

    monkeypatch.setattr(setup_driver_module.time, "time_ns", lambda: 200)
    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Objective admitted here"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )
    state_path = setup_driver_module._state_path(project.resolve(), session_id)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    # Its stamp really is earlier than the admission's, and it is STILL preserved.
    assert sealed["recorded_at_ns"] < state["receipt"]["admission_order_ns"]
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(json.dumps(sealed), encoding="utf-8")

    blocked = handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "a later subordinate prompt"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )

    assert pending_path.is_file(), "no sealed objective may be destroyed automatically"
    assert blocked["decision"] == "block"
    assert "order cannot be established" in blocked["reason"]
    # The stamps are still surfaced, explicitly as non-authoritative evidence.
    assert "NOT authoritative" in blocked["reason"]


def test_tampered_pending_record_still_quarantines_after_a_valid_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tampered pending record must not become a laundering route."""
    project = tmp_path / "quarantine-project"
    _init_repo(project)
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SENIOR_HARNESS_SEAL_KEY_FILE", str(tmp_path / "seal.key"))
    session_id = "quarantine-session"
    roots = [REPO_ROOT / "skills"]
    base = {"session_id": session_id, "cwd": str(project)}

    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Live objective for this project"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )
    pending_path = setup_driver_module._pending_state_path(session_id)
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(
        json.dumps(
            {
                "session_key": setup_driver_module._session_key(session_id),
                "literal_objective": "Injected objective",
                "surface": "codex",
                "pending_seal": "sha256-hmac:" + "0" * 64,
            }
        ),
        encoding="utf-8",
    )

    denied = handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "a later prompt"},
        surface="codex",
        event="UserPromptSubmit",
        skill_search_roots=roots,
    )
    assert denied["decision"] == "block"
    assert "pending startup objective is invalid" in denied["reason"]
    assert pending_path.is_file()


def test_write_state_uses_a_temporary_path_unique_to_each_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "session.json"
    observed: list[Path] = []
    real_replace = Path.replace

    def recording_replace(self: Path, other) -> None:
        observed.append(Path(self))
        return real_replace(self, other)

    monkeypatch.setattr(Path, "replace", recording_replace)
    setup_driver_module._write_state(target, {"writer": "a"})
    setup_driver_module._write_state(target, {"writer": "b"})

    assert len(observed) == 2
    assert observed[0] != observed[1]
    assert target.with_suffix(".tmp") not in observed


def test_concurrent_writers_cannot_publish_each_others_session_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interleave two writers in the exact window a shared temp name makes fatal.

    Claude and Codex PreToolUse matchers fire on every tool, so a second hook process
    can complete a whole write between the first writer's temp write and its replace.
    With one fixed sibling ``.tmp`` the second writer overwrites and then consumes the
    first writer's temp file, so the first replace fails outright.
    """
    target = tmp_path / "session.json"
    real_replace = Path.replace
    interleaved = {"done": False}

    def interleaving_replace(self: Path, other) -> None:
        if not interleaved["done"]:
            interleaved["done"] = True
            setup_driver_module._write_state(target, {"writer": "b"})
        return real_replace(self, other)

    monkeypatch.setattr(Path, "replace", interleaving_replace)
    setup_driver_module._write_state(target, {"writer": "a"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"writer": "a"}
    assert not list(tmp_path.glob("*.tmp"))
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_delivery_repository_shas_resolve_and_are_ordered_in_this_checkout() -> None:
    """The fixture's repository block must be valid in whatever checkout is running.

    CI clones at ``actions/checkout`` depth 1, where the fixture's pinned base commit
    does not exist at all.
    """
    repository = _delivery()["repository"]
    for label in ("base_sha", "candidate_sha"):
        resolved = subprocess.run(
            ["git", "cat-file", "-e", f"{repository[label]}^{{commit}}"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
        )
        assert resolved.returncode == 0, f"{label} does not resolve in this checkout"
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", repository["base_sha"], repository["candidate_sha"]],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    assert ancestry.returncode == 0


def _hermetic_repository_contract(tmp_path: Path) -> tuple[dict, Path, str, str]:
    """A delivery contract bound to a two-commit checkout the test owns outright."""
    project = tmp_path / "ancestry-project"
    first = _init_repo(project)
    (project / "README.md").write_text("# Candidate\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "candidate"], cwd=project, check=True)
    second = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project, check=True, capture_output=True, text=True
    ).stdout.strip()
    contract = _delivery()
    contract["repository"] = {
        "base_sha": first,
        "candidate_sha": second,
        "worktree": str(project.resolve()),
    }
    return contract, project, first, second


def test_repository_contract_accepts_a_base_that_is_a_real_ancestor(tmp_path: Path) -> None:
    contract, _project, _first, _second = _hermetic_repository_contract(tmp_path)
    assert validate_contract(contract)["status"] == "valid"


def test_repository_contract_rejects_a_base_that_is_not_an_ancestor(tmp_path: Path) -> None:
    contract, project, _first, _second = _hermetic_repository_contract(tmp_path)
    subprocess.run(["git", "checkout", "-q", "--orphan", "sidebranch"], cwd=project, check=True)
    (project / "SIDE.md").write_text("# Side\n", encoding="utf-8")
    subprocess.run(["git", "add", "SIDE.md"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "side"], cwd=project, check=True)
    unrelated = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project, check=True, capture_output=True, text=True
    ).stdout.strip()
    contract["repository"]["base_sha"] = unrelated

    with pytest.raises(ContractError) as excinfo:
        validate_contract(contract)
    assert any("must be an ancestor" in error for error in excinfo.value.errors)


def test_repository_contract_rejects_a_base_absent_from_the_worktree(tmp_path: Path) -> None:
    contract, _project, _first, _second = _hermetic_repository_contract(tmp_path)
    contract["repository"]["base_sha"] = "0" * 40

    with pytest.raises(ContractError) as excinfo:
        validate_contract(contract)
    assert any("does not resolve to a commit" in error for error in excinfo.value.errors)

