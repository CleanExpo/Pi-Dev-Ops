from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "senior-harness" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from senior_harness import digest  # noqa: E402
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
    forged["receipt_integrity_digest"] = digest(unsigned_receipt)

    with pytest.raises(SetupError, match="cannot grant mutation"):
        validate_startup_receipt(forged)


def test_recomputed_public_digests_cannot_forge_outer_business_authority() -> None:
    forged = copy.deepcopy(_receipt())
    forged["admission"]["business_authority"] = True
    unsigned_receipt = dict(forged)
    unsigned_receipt.pop("receipt_integrity_digest")
    forged["receipt_integrity_digest"] = digest(unsigned_receipt)

    with pytest.raises(SetupError, match="cannot grant mutation, business"):
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


def test_cli_start_is_machine_readable_and_read_only() -> None:
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
            "codex",
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

    assert json.loads(result.stdout)["stage"] == "startup-admitted"
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

    allowed = handle_hook({**base, "hook_event_name": "PreToolUse"}, surface="codex", event="PreToolUse")
    assert "permissionDecision" not in allowed["hookSpecificOutput"]
    assert "Primary objective" in allowed["hookSpecificOutput"]["additionalContext"]

    followup = handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Push an unrelated release"},
        surface="codex",
        event="UserPromptSubmit",
    )
    assert "remains frozen" in followup["hookSpecificOutput"]["additionalContext"]
    assert "Primary objective" in followup["hookSpecificOutput"]["additionalContext"]

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
