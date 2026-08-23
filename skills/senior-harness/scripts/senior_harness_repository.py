"""Repository identity and Git ancestry validation."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from senior_harness_core import require_mapping


def _valid_sha(value: Any, *, nullable: bool = False) -> bool:
    if nullable and value is None:
        return True
    return (
        isinstance(value, str)
        and len(value) == 40
        and not any(character not in "0123456789abcdef" for character in value)
    )


def _resolve_checkout(worktree_path: Path, errors: list[str]) -> Path | None:
    try:
        top_level = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=worktree_path,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        errors.append(f"repository.worktree could not be checked: {exc}")
        return None
    if top_level.returncode != 0:
        errors.append("repository.worktree must be a Git checkout")
        return None
    try:
        declared_root = worktree_path.resolve(strict=True)
        actual_root = Path(top_level.stdout.strip()).resolve(strict=True)
    except OSError as exc:
        errors.append(f"repository.worktree could not be resolved: {exc}")
        return None
    if declared_root != actual_root:
        errors.append("repository.worktree must name the Git checkout root")
    return actual_root


def _probe_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    environment["GIT_GRAFT_FILE"] = os.devnull
    return environment


def _probe_commits(actual_root: Path, base_sha: Any, candidate_sha: Any, errors: list[str], environment: dict[str, str]) -> None:
    for label, sha in (("base_sha", base_sha), ("candidate_sha", candidate_sha)):
        if not isinstance(sha, str) or len(sha) != 40:
            continue
        try:
            result = subprocess.run(
                ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                cwd=actual_root,
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )
        except OSError as exc:
            errors.append(f"repository.{label} could not be checked: {exc}")
            continue
        if result.returncode != 0:
            errors.append(f"repository.{label} does not resolve to a commit in repository.worktree")


def _read_head(actual_root: Path, errors: list[str]) -> str | None:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=actual_root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        errors.append(f"repository HEAD could not be checked: {exc}")
        return None
    if head.returncode != 0:
        errors.append("repository.worktree HEAD could not be resolved")
        return None
    return head.stdout.strip()


def _validate_ancestry(actual_root: Path, base_sha: Any, tip: str, errors: list[str], environment: dict[str, str]) -> None:
    if not isinstance(base_sha, str) or len(base_sha) != 40:
        return
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, tip],
        cwd=actual_root,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    if ancestry.returncode != 0:
        errors.append("repository.base_sha must be an ancestor of the checked candidate or worktree HEAD")


def validate_repository(contract: dict[str, Any], errors: list[str]) -> None:
    repository = require_mapping(contract.get("repository"), "repository", errors)
    base_sha = repository.get("base_sha")
    candidate_sha = repository.get("candidate_sha")
    if not _valid_sha(base_sha):
        errors.append("repository.base_sha must be a 40-character lowercase Git SHA")
    if not _valid_sha(candidate_sha, nullable=True):
        errors.append("repository.candidate_sha must be null or a 40-character lowercase Git SHA")
    worktree = repository.get("worktree")
    if not isinstance(worktree, str) or not Path(worktree).is_absolute():
        errors.append("repository.worktree must be an absolute path")
        return
    worktree_path = Path(worktree)
    if not worktree_path.is_dir():
        errors.append("repository.worktree must exist and be a directory")
        return
    actual_root = _resolve_checkout(worktree_path, errors)
    if actual_root is None:
        return
    environment = _probe_environment()
    _probe_commits(actual_root, base_sha, candidate_sha, errors, environment)
    head_sha = _read_head(actual_root, errors)
    if head_sha is None:
        return
    if isinstance(candidate_sha, str) and len(candidate_sha) == 40 and candidate_sha != head_sha:
        errors.append("repository.candidate_sha must equal repository.worktree HEAD")
    tip = candidate_sha if isinstance(candidate_sha, str) and len(candidate_sha) == 40 else head_sha
    _validate_ancestry(actual_root, base_sha, tip, errors, environment)
