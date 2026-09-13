"""Project-coverage gate for tao_loop termination.

`coverage_check.py` already knows how to score a Definition of Done. This
module is the loop-facing adapter: resolve which DoD applies to a workspace,
run those probes, and say whether completion is allowed.

No DoD in the workspace is a skip, not a pass-by-silence on a failed check.
A resolved DoD with any machine-checkable FAIL blocks completion.
"""
from __future__ import annotations

import importlib.util
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final

log = logging.getLogger("pi-ceo.coverage_gate")

_SCRIPT: Final[Path] = (
    Path(__file__).resolve().parents[2] / "scripts" / "coverage_check.py"
)
_DOD_DIRS: Final[tuple[str, ...]] = ("config/harness/dod", ".harness/dod")
_checker: ModuleType | None = None


@dataclass(frozen=True)
class CoverageOutcome:
    """Result of scoring workspace DoD probes."""

    satisfied: bool
    skipped: bool
    failed: int
    dod_paths: tuple[str, ...]
    evidence: str


def _coverage_check() -> ModuleType:
    """Load scripts/coverage_check.py once. Raises if the script is missing."""
    global _checker
    if _checker is not None:
        return _checker
    spec = importlib.util.spec_from_file_location("coverage_check_gate", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load coverage_check: {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _checker = module
    return module


def _dod_project_id(path: Path) -> str:
    try:
        data = _coverage_check()._load_yaml(path)
    except Exception:
        return ""
    if isinstance(data, dict):
        return str(data.get("project_id") or "")
    return ""


def resolve_dod_paths(
    workspace: str,
    dod_path: str | None = None,
    project_id: str | None = None,
) -> list[Path]:
    """Return the DoD files that apply to this workspace.

    Explicit ``dod_path`` / ``TAO_DOD_PATH`` wins. Otherwise discover the two
    standard dirs. A project id filters a multi-file tree; a single file is
    used as-is. Ambiguous multi-file trees without a project id return empty
    so this repo's RestoreAssist seed cannot silently gate a Pi-Dev-Ops loop.
    """
    explicit = (dod_path or os.environ.get("TAO_DOD_PATH") or "").strip()
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = Path(workspace) / explicit
        return [path] if path.is_file() else []

    found: list[Path] = []
    root = Path(workspace)
    for rel in _DOD_DIRS:
        directory = root / rel
        if directory.is_dir():
            found.extend(sorted(directory.glob("*.dod.yaml")))
    pid = (project_id or os.environ.get("TAO_PROJECT_ID") or "").strip()
    if pid:
        return [path for path in found if _dod_project_id(path) == pid]
    return found if len(found) == 1 else []


def evaluate_workspace(
    workspace: str,
    dod_path: str | None = None,
    project_id: str | None = None,
) -> CoverageOutcome:
    """Score resolved DoD files against ``workspace``. Fail-closed on errors."""
    paths = resolve_dod_paths(workspace, dod_path, project_id)
    if not paths:
        return CoverageOutcome(True, True, 0, (), "no DoD spec")
    try:
        return _score_paths(Path(workspace), paths)
    except Exception as exc:
        log.warning("coverage_gate evaluate failed: %s", exc)
        return CoverageOutcome(
            False, False, -1, tuple(str(p) for p in paths), str(exc),
        )


def _score_paths(repo: Path, paths: list[Path]) -> CoverageOutcome:
    checker = _coverage_check()
    failed = 0
    notes: list[str] = []
    for path in paths:
        dod = checker._load_yaml(path)
        report = checker.report(dod, checker.evaluate(dod, repo))
        failed += int(report.get("failed") or 0)
        notes.append(f"{path.name}:{report.get('failed', 0)} fail")
    return CoverageOutcome(
        failed == 0, False, failed, tuple(str(p) for p in paths), "; ".join(notes),
    )


def workspace_coverage_failed(
    workspace: str,
    dod_path: str | None = None,
    project_id: str | None = None,
) -> bool:
    """True when a coverage check ran and blocked completion."""
    return not evaluate_workspace(workspace, dod_path, project_id).satisfied


__all__ = [
    "CoverageOutcome",
    "evaluate_workspace",
    "resolve_dod_paths",
    "workspace_coverage_failed",
]
