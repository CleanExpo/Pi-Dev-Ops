"""
push_helper.py — Atomic multi-file commit via GitHub Git Data API (RA-883).

Uses PyGithub (HTTPS + fine-grained PAT) so no git binary or SSH key is needed.
Works identically on Railway, Cowork sandbox, and local dev.

Environment variables:
  GITHUB_TOKEN — fine-grained PAT with Contents=Read/Write, Metadata=Read
  GITHUB_REPO  — owner/repo slug (e.g. "CleanExpo/Pi-Dev-Ops")

Usage:
    from app.server.push_helper import push_files_atomic, is_push_available

    if is_push_available():
        sha = push_files_atomic(
            files={"path/to/file.py": "file contents..."},
            message="feat: auto-generated change [skip ci]",
            branch="feature/ra-123-fix",
        )
"""
from __future__ import annotations

import logging
import os
from typing import Optional

_log = logging.getLogger("pi-ceo.push_helper")


def is_push_available() -> bool:
    """Return True when GITHUB_TOKEN and GITHUB_REPO are set and PyGithub is installed."""
    if not os.environ.get("GITHUB_TOKEN") or not os.environ.get("GITHUB_REPO"):
        return False
    try:
        import github  # noqa: F401

        return True
    except ImportError:
        return False


def push_files_atomic(
    files: dict[str, str],
    message: str,
    branch: str = "main",
    create_branch_from: Optional[str] = None,
) -> str:
    """Atomic multi-file commit via GitHub Git Data API.

    Creates a single commit touching all files in `files` atomically — no
    intermediate states visible on the branch. Optionally creates `branch`
    from `create_branch_from` if it doesn't already exist.

    Args:
        files: {path: content} mapping. Paths are relative to repo root.
        message: Commit message. Append "[skip ci]" to prevent deploy loops.
        branch: Target branch name. Defaults to "main".
        create_branch_from: If set and `branch` doesn't exist, create it from
                            this ref (e.g. "main"). Pass None to skip creation.

    Returns:
        SHA of the new commit.

    Raises:
        ImportError: PyGithub not installed.
        KeyError: GITHUB_TOKEN or GITHUB_REPO not set.
        github.GithubException: API-level error (auth, repo not found, etc.).
    """
    import github

    token = os.environ["GITHUB_TOKEN"]
    repo_slug = os.environ["GITHUB_REPO"]

    gh = github.Github(token)
    repo = gh.get_repo(repo_slug)

    # Create branch if requested and it doesn't already exist
    if create_branch_from:
        try:
            repo.get_branch(branch)
        except github.GithubException:
            source_sha = repo.get_branch(create_branch_from).commit.sha
            repo.create_git_ref(f"refs/heads/{branch}", source_sha)
            _log.info("push_helper: created branch %s from %s", branch, create_branch_from)

    # Build tree elements — one blob per file
    branch_sha = repo.get_branch(branch).commit.sha
    base_tree = repo.get_git_tree(sha=branch_sha)

    elements: list[github.InputGitTreeElement] = []
    for path, content in files.items():
        blob = repo.create_git_blob(content, "utf-8")
        elements.append(
            github.InputGitTreeElement(
                path=path,
                mode="100644",
                type="blob",
                sha=blob.sha,
            )
        )

    tree = repo.create_git_tree(elements, base_tree)
    parent = repo.get_git_commit(sha=branch_sha)
    commit = repo.create_git_commit(message, tree, [parent])
    repo.get_git_ref(f"heads/{branch}").edit(sha=commit.sha)

    _log.info(
        "push_helper: committed %d file(s) to %s/%s sha=%s",
        len(files),
        repo_slug,
        branch,
        commit.sha[:8],
    )
    return commit.sha
