"""Focused tests for repository ancestry validation."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    ContractError,
    Path,
    REPO_ROOT,
    _delivery,
    _hermetic_repository_contract,
    pytest,
    subprocess,
    validate_contract,
)


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
        [
            "git",
            "merge-base",
            "--is-ancestor",
            repository["base_sha"],
            repository["candidate_sha"],
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    assert ancestry.returncode == 0


def test_repository_contract_accepts_a_base_that_is_a_real_ancestor(
    tmp_path: Path,
) -> None:
    contract, _project, _first, _second = _hermetic_repository_contract(tmp_path)
    assert validate_contract(contract)["status"] == "valid"


def test_repository_contract_rejects_a_base_that_is_not_an_ancestor(
    tmp_path: Path,
) -> None:
    contract, project, _first, _second = _hermetic_repository_contract(tmp_path)
    subprocess.run(
        ["git", "checkout", "-q", "--orphan", "sidebranch"], cwd=project, check=True
    )
    (project / "SIDE.md").write_text("# Side\n", encoding="utf-8")
    subprocess.run(["git", "add", "SIDE.md"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "side"], cwd=project, check=True)
    unrelated = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    contract["repository"]["base_sha"] = unrelated

    with pytest.raises(ContractError) as excinfo:
        validate_contract(contract)
    assert any("must be an ancestor" in error for error in excinfo.value.errors)


def test_repository_contract_rejects_a_base_absent_from_the_worktree(
    tmp_path: Path,
) -> None:
    contract, _project, _first, _second = _hermetic_repository_contract(tmp_path)
    contract["repository"]["base_sha"] = "0" * 40

    with pytest.raises(ContractError) as excinfo:
        validate_contract(contract)
    assert any(
        "does not resolve to a commit" in error for error in excinfo.value.errors
    )
