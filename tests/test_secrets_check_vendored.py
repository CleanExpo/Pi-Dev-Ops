"""Regression coverage for the vendored-dependency exclusion in secrets_check.py.

The heavy-path filter used to name each virtualenv directory ('.venv/', 'venv/').
That missed this repo's own `.venv-verify/` — `'.venv/' in '.venv-verify/lib/...'`
is False, because the next character is '-' rather than '/'. 8,099 vendored files
entered every local scan and 102 third-party matches were reported as exposed
secrets, so the gate exited 1 on a clean tree.

Both arms matter. Asserting only that vendored files are skipped would also pass
if the scanner had stopped detecting anything at all, so each test plants the same
secret in a scanned path and asserts it is still found.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "secrets_check.py"

# Invented, non-functional AWS access key ID. Deliberately avoids the placeholder
# vocabulary (fake/dummy/sample/test/EXAMPLE) that the scanner suppresses by design.
CANARY = "AKIA3RQZ7WBN2KLPXV4C"


def _scan(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo), "--dry-run"],
        text=True,
        capture_output=True,
        check=False,
    )


def _repo_with(tmp_path: Path, *relative_paths: str) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for rel in relative_paths:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f'aws_access = "{CANARY}"\n', encoding="utf-8")
    return tmp_path


def test_secret_in_a_normal_path_is_reported(tmp_path: Path) -> None:
    """Positive control: without this passing, the exclusion tests below prove nothing."""
    result = _scan(_repo_with(tmp_path, "app/handler.py"))

    assert result.returncode == 1, result.stdout + result.stderr
    assert "app/handler.py" in result.stdout


def test_secret_inside_vendored_site_packages_is_not_reported(tmp_path: Path) -> None:
    """A virtualenv whose directory name no filter enumerates must still be skipped."""
    result = _scan(
        _repo_with(tmp_path, ".venv-verify/lib/python3.11/site-packages/authlib/sig.py")
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "site-packages" not in result.stdout


def test_vendored_exclusion_does_not_mask_a_real_finding(tmp_path: Path) -> None:
    """The exclusion must drop only the vendored tree, never the repo's own source."""
    result = _scan(
        _repo_with(
            tmp_path,
            "app/handler.py",
            ".venv-verify/lib/python3.11/site-packages/authlib/sig.py",
        )
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "app/handler.py" in result.stdout
    assert "site-packages" not in result.stdout


def test_committed_site_packages_fails_the_run_instead_of_being_skipped(
    tmp_path: Path,
) -> None:
    """The exclusion is verified, not trusted.

    Skipping vendored files is only sound while none are committed. If they ever are,
    the precondition must fail the run (exit 2) rather than leave them unscanned.
    """
    repo = _repo_with(tmp_path, ".venv-verify/lib/python3.11/site-packages/authlib/sig.py")
    subprocess.run(
        ["git", "add", "-f", ".venv-verify/lib/python3.11/site-packages/authlib/sig.py"],
        cwd=repo,
        check=True,
    )

    result = _scan(repo)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "VIOLATION" in result.stdout
