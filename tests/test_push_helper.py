"""tests/test_push_helper.py — Unit tests for push_helper (RA-883)."""
from unittest.mock import MagicMock, patch
import pytest


def test_is_push_available_missing_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    from app.server.push_helper import is_push_available

    assert is_push_available() is False


def test_is_push_available_missing_repo(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    from app.server.push_helper import is_push_available

    assert is_push_available() is False


def test_is_push_available_no_pygithub(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.setenv("GITHUB_REPO", "org/repo")
    with patch.dict("sys.modules", {"github": None}):
        # Re-import to pick up mocked module
        import importlib

        import app.server.push_helper as mod

        importlib.reload(mod)
        # With github=None in sys.modules, import will fail
        result = mod.is_push_available()
        assert result is False


def test_push_files_atomic_missing_env():
    """push_files_atomic raises KeyError when GITHUB_TOKEN not set."""
    import os

    old_token = os.environ.pop("GITHUB_TOKEN", None)
    old_repo = os.environ.pop("GITHUB_REPO", None)
    try:
        from app.server.push_helper import push_files_atomic

        with pytest.raises((KeyError, Exception)):
            push_files_atomic({"file.py": "content"}, "test commit")
    finally:
        if old_token:
            os.environ["GITHUB_TOKEN"] = old_token
        if old_repo:
            os.environ["GITHUB_REPO"] = old_repo


def test_push_files_atomic_calls_github_api(monkeypatch):
    """push_files_atomic correctly calls GitHub Git Data API."""
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.setenv("GITHUB_REPO", "org/repo")

    mock_blob = MagicMock()
    mock_blob.sha = "blob-sha-123"

    mock_tree = MagicMock()
    mock_tree_obj = MagicMock()

    mock_commit = MagicMock()
    mock_commit.sha = "commit-sha-abc123"

    mock_parent = MagicMock()
    mock_branch = MagicMock()
    mock_branch.commit.sha = "branch-sha-xyz"

    mock_repo = MagicMock()
    mock_repo.get_branch.return_value = mock_branch
    mock_repo.get_git_tree.return_value = mock_tree_obj
    mock_repo.create_git_blob.return_value = mock_blob
    mock_repo.create_git_tree.return_value = mock_tree
    mock_repo.get_git_commit.return_value = mock_parent
    mock_repo.create_git_commit.return_value = mock_commit

    mock_gh = MagicMock()
    mock_gh.get_repo.return_value = mock_repo

    mock_github_module = MagicMock()
    mock_github_module.Github.return_value = mock_gh
    mock_github_module.InputGitTreeElement = MagicMock(return_value=MagicMock())

    with patch.dict("sys.modules", {"github": mock_github_module}):
        import importlib

        import app.server.push_helper as mod

        importlib.reload(mod)
        sha = mod.push_files_atomic(
            files={"app/foo.py": "print('hello')"},
            message="feat: test [skip ci]",
            branch="main",
        )

    assert sha == "commit-sha-abc123"
    mock_repo.create_git_blob.assert_called_once_with("print('hello')", "utf-8")
    mock_repo.create_git_commit.assert_called_once()
