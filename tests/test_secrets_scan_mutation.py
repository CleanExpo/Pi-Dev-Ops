"""UNI-2651 — the secrets-scan mutation must be able to go red, then recover."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MUTATION = REPO_ROOT / "scripts" / "secrets_scan_mutation.py"
SCANNER = REPO_ROOT / "scripts" / "secrets_check.py"
PLANT_REL = "docs/.secrets-scan-mutation-plant.ts"


def _run_mutation(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MUTATION), "--repo-root", str(repo)],
        text=True,
        capture_output=True,
        check=False,
    )


def _init_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README"], cwd=tmp_path, check=True)
    return tmp_path


def test_mutation_detects_plant_then_removes_it(tmp_path: Path) -> None:
    result = _run_mutation(_init_repo(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "RED" in result.stdout
    assert "GREEN" in result.stdout
    assert not (tmp_path / PLANT_REL).exists()


def test_mutation_does_not_rewrite_gitignore(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    gitignore = repo / ".gitignore"
    gitignore.write_text(".env\n", encoding="utf-8")

    result = _run_mutation(repo)

    assert result.returncode == 0, result.stdout + result.stderr
    assert gitignore.read_text(encoding="utf-8") == ".env\n"


def test_source_does_not_contain_the_contiguous_token() -> None:
    """If the token is written whole, the scanner fails this tree forever."""
    token = "AKIA" + "00UNI2651PROOFZZ"
    mutation_src = MUTATION.read_text(encoding="utf-8")
    scanner_src = SCANNER.read_text(encoding="utf-8")

    assert token not in mutation_src
    assert token not in scanner_src
    assert PLANT_REL.startswith("docs/")
    assert not PLANT_REL.startswith("tests/")
