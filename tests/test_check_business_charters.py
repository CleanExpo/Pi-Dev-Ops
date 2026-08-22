"""The business-charter gate must decide from the repository, never from the machine.

One Git SHA used to get two verdicts: exit 1 on a laptop holding
`~/.hermes/business-charters/restoreassist.md`, exit 0 in CI where that file cannot
exist. The repair the gate itself printed — drop `restoreassist` from `_KNOWN_MISSING`
— would have inverted the pair rather than fixing it. These tests pin the property that
makes the gate satisfiable at all: the verdict, and the stdout it is read from, are a
function of the checked-out tree alone.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "check_business_charters.py"


def _run(script: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        env=env,
        capture_output=True,
        text=True,
    )


def _env(**overrides: str | None) -> dict[str, str]:
    env = dict(os.environ)
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def _hermes_with_charter(tmp_path: Path, name: str) -> Path:
    """A machine-local store that DOES carry a charter the repository does not."""
    root = tmp_path / "hermes-present"
    (root / "business-charters").mkdir(parents=True, exist_ok=True)
    (root / "business-charters" / f"{name}.md").write_text(
        "# local only\n", encoding="utf-8"
    )
    return root


def _three_environments(tmp_path: Path) -> dict[str, dict[str, str]]:
    """The three environments one SHA has to agree across."""
    empty_hermes = tmp_path / "hermes-absent"
    empty_hermes.mkdir()
    clean_home = tmp_path / "ci-home"
    clean_home.mkdir()
    return {
        "local charter present": _env(
            HERMES_ROOT=str(_hermes_with_charter(tmp_path, "restoreassist"))
        ),
        "local charter absent": _env(HERMES_ROOT=str(empty_hermes)),
        "clean CI-shaped HOME": _env(HERMES_ROOT=None, HOME=str(clean_home)),
    }


def test_same_sha_gets_the_same_verdict_in_every_environment(tmp_path: Path) -> None:
    results = {
        label: _run(CHECKER, env=env) for label, env in _three_environments(tmp_path).items()
    }
    exits = {label: r.returncode for label, r in results.items()}
    assert set(exits.values()) == {0}, exits
    stdouts = {label: r.stdout for label, r in results.items()}
    assert len(set(stdouts.values())) == 1, (
        "stdout differs between environments, so two people cannot compare gate logs "
        f"for one SHA:\n{json.dumps(stdouts, indent=2)}"
    )


def test_a_machine_local_charter_does_not_flip_the_verdict(tmp_path: Path) -> None:
    """The exact 2026-08-22 failure: restoreassist present locally forced exit 1."""
    present = _run(
        CHECKER, env=_env(HERMES_ROOT=str(_hermes_with_charter(tmp_path, "restoreassist")))
    )
    assert present.returncode == 0, present.stdout
    assert "[FIXED] restoreassist" not in present.stdout
    assert "must leave _KNOWN_MISSING" not in present.stdout


def test_explain_local_reports_the_machine_state_without_scoring_it(tmp_path: Path) -> None:
    hermes = _hermes_with_charter(tmp_path, "restoreassist")
    plain = _run(CHECKER, env=_env(HERMES_ROOT=str(hermes)))
    explained = _run(CHECKER, "--explain-local", env=_env(HERMES_ROOT=str(hermes)))
    assert explained.returncode == plain.returncode == 0
    assert explained.stdout == plain.stdout, "the diagnostic leaked into the scored output"
    assert "restoreassist" in explained.stderr
    assert str(hermes) in explained.stderr


# ---- the ratchet itself, exercised against synthetic repositories -----------------


def _synthetic_repo(tmp_path: Path, projects: list[dict], *, charters: dict[str, str] | None = None) -> Path:
    """A throwaway checkout carrying the real, unmodified checker."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "config" / "harness").mkdir(parents=True)
    shutil.copy2(CHECKER, root / "scripts" / CHECKER.name)
    (root / "config" / "harness" / "projects.json").write_text(
        json.dumps({"projects": projects}, indent=2), encoding="utf-8"
    )
    for relative, body in (charters or {}).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return root


def test_a_charter_the_repository_now_carries_must_leave_the_known_set(tmp_path: Path) -> None:
    repo = _synthetic_repo(
        tmp_path,
        [{"id": "carsi", "business_charter": "business-charters/carsi.md"}],
        charters={"business-charters/carsi.md": "# carsi\n"},
    )
    result = _run(repo / "scripts" / CHECKER.name, env=_env())
    assert result.returncode == 1, result.stdout
    assert "[FIXED] carsi" in result.stdout


def test_a_newly_declared_charter_with_no_repository_file_fails(tmp_path: Path) -> None:
    repo = _synthetic_repo(
        tmp_path, [{"id": "brand-new", "business_charter": "business-charters/brand-new.md"}]
    )
    result = _run(repo / "scripts" / CHECKER.name, env=_env())
    assert result.returncode == 1, result.stdout
    assert "[MISSING] brand-new" in result.stdout


def test_everything_resolving_with_nothing_known_missing_passes(tmp_path: Path) -> None:
    repo = _synthetic_repo(
        tmp_path,
        [{"id": "brand-new", "business_charter": "business-charters/brand-new.md"}],
        charters={"business-charters/brand-new.md": "# new\n"},
    )
    result = _run(repo / "scripts" / CHECKER.name, env=_env())
    assert result.returncode == 0, result.stdout
    assert "[PASS] no new unresolvable charters" in result.stdout


def test_an_absolute_declared_path_never_resolves(tmp_path: Path) -> None:
    """Absolute means machine-local, which is the input this gate must not read."""
    outside = tmp_path / "outside" / "brand-new.md"
    outside.parent.mkdir(parents=True)
    outside.write_text("# outside\n", encoding="utf-8")
    repo = _synthetic_repo(tmp_path, [{"id": "brand-new", "business_charter": str(outside)}])
    result = _run(repo / "scripts" / CHECKER.name, env=_env())
    assert result.returncode == 1, result.stdout
    assert "[MISSING] brand-new" in result.stdout


def test_a_declared_path_escaping_the_repository_never_resolves(tmp_path: Path) -> None:
    escape = tmp_path / "escape.md"
    escape.write_text("# escape\n", encoding="utf-8")
    repo = _synthetic_repo(
        tmp_path, [{"id": "brand-new", "business_charter": "../escape.md"}]
    )
    result = _run(repo / "scripts" / CHECKER.name, env=_env())
    assert result.returncode == 1, result.stdout
    assert "[MISSING] brand-new" in result.stdout


def test_an_unreadable_registry_is_exit_2(tmp_path: Path) -> None:
    repo = _synthetic_repo(tmp_path, [])
    (repo / "config" / "harness" / "projects.json").write_text("{not json", encoding="utf-8")
    result = _run(repo / "scripts" / CHECKER.name, env=_env())
    assert result.returncode == 2, result.stdout
    assert "registry unreadable" in result.stdout


# ---- mutation control ------------------------------------------------------------


def test_the_determinism_test_catches_a_return_to_machine_dependence(tmp_path: Path) -> None:
    """Reintroduce the old machine-consulting resolver and prove the gate splits again.

    Without this, `test_same_sha_gets_the_same_verdict_in_every_environment` could pass
    for a reason unrelated to the repair — for instance if no environment on the runner
    happened to carry a local charter at all.
    """
    repo = _synthetic_repo(
        tmp_path, [{"id": "carsi", "business_charter": "business-charters/carsi.md"}]
    )
    mutant = repo / "scripts" / CHECKER.name
    source = mutant.read_text(encoding="utf-8")
    marker = "    path = Path(declared)\n    if path.is_absolute():\n        return False"
    assert source.count(marker) == 1, "the resolver's shape changed; update this control"
    mutant.write_text(
        source.replace(
            marker,
            "    path = Path(declared)\n"
            "    if (_charters_dir() / path.name).exists():\n"
            "        return True\n"
            "    if path.is_absolute():\n"
            "        return False",
        ),
        encoding="utf-8",
    )

    hermes = _hermes_with_charter(tmp_path, "carsi")
    empty = tmp_path / "hermes-empty"
    empty.mkdir()
    with_local = _run(mutant, env=_env(HERMES_ROOT=str(hermes)))
    without_local = _run(mutant, env=_env(HERMES_ROOT=str(empty)))

    assert with_local.returncode == 1, with_local.stdout
    assert "[FIXED] carsi" in with_local.stdout
    assert without_local.returncode == 0, without_local.stdout
    assert with_local.returncode != without_local.returncode, (
        "the mutant did not split the verdict, so the determinism test above is not "
        "actually pinned to repository-only resolution"
    )
