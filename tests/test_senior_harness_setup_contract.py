"""Focused tests for setup contract integrity."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    REPO_ROOT,
    SetupError,
    _receipt,
    admit_startup,
    build_setup_contract,
    copy,
    digest,
    pytest,
    setup_driver_module,
    subprocess,
    validate_startup_receipt,
)


def test_setup_freezes_literal_objective_and_issues_no_authority() -> None:
    objective = "  Create the setup driver — exactly.  "
    receipt = _receipt(objective)

    setup = receipt["setup_contract"]
    assert setup["literal_objective"] == objective
    assert setup["authority"]["mutation_authority"] is False
    assert receipt["admission"]["startup_only"] is True
    assert receipt["admission"]["mutation_authority"] is False
    assert (
        validate_startup_receipt(receipt, literal_objective=objective)["status"]
        == "valid"
    )


def test_setup_binds_exact_checkout_head_state_skills_and_driver() -> None:
    receipt = _receipt()
    setup = receipt["setup_contract"]

    assert setup["repository"]["worktree"] == str(REPO_ROOT.resolve())
    assert len(setup["repository"]["head_sha"]) == 40
    assert set(setup["required_skills"]) == {"senior-harness", "model-router", "unlazy"}
    assert all(
        item["folder_digest"].startswith("sha256:")
        for item in setup["required_skills"].values()
    )
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
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "tracked").write_text("one", encoding="utf-8")
    subprocess.run(["git", "add", "tracked"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=repo, check=True)
    (repo / "dirty").write_text("two", encoding="utf-8")
    with pytest.raises(SetupError, match="clean Git checkout"):
        build_setup_contract(
            "x",
            repo,
            surface="codex",
            strict_clean=True,
            skill_search_roots=[REPO_ROOT / "skills"],
        )


def test_skill_change_invalidates_receipt(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills"
    for name in ("senior-harness", "model-router", "unlazy"):
        folder = skill_root / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test\n---\n", encoding="utf-8"
        )
    receipt = admit_startup(
        build_setup_contract(
            "x", REPO_ROOT, surface="codex", skill_search_roots=[skill_root]
        )
    )
    (skill_root / "unlazy" / "SKILL.md").write_text(
        "---\nname: unlazy\n---\nchanged\n", encoding="utf-8"
    )
    with pytest.raises(SetupError, match="skill changed"):
        validate_startup_receipt(receipt)
    assert (
        validate_startup_receipt(receipt, verify_control_bindings=False)["status"]
        == "valid"
    )
    assert any(
        "skill changed" in error
        for error in setup_driver_module._control_binding_errors(receipt)
    )


def test_missing_or_misnamed_skill_fails_closed(tmp_path: Path) -> None:
    roots = tmp_path / "isolated"
    for name in ("senior-harness", "model-router", "unlazy"):
        folder = roots / name
        folder.mkdir(parents=True)
        declared = "wrong-name" if name == "unlazy" else name
        (folder / "SKILL.md").write_text(
            f"---\nname: {declared}\n---\n", encoding="utf-8"
        )
    with pytest.raises(SetupError, match="declares name"):
        build_setup_contract(
            "x", REPO_ROOT, surface="codex", skill_search_roots=[roots]
        )


def test_repository_state_change_invalidates_receipt(tmp_path: Path) -> None:
    receipt = _receipt()
    altered = copy.deepcopy(receipt)
    altered["setup_contract"]["repository"]["head_sha"] = "0" * 40
    with pytest.raises(SetupError, match="integrity"):
        validate_startup_receipt(altered)


def test_dirty_file_byte_change_invalidates_receipt_even_when_status_shape_is_unchanged(
    tmp_path: Path,
) -> None:
    project = tmp_path / "dirty-project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=project, check=True
    )
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
