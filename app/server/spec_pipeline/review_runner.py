"""Automated review-command lens runner."""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("pi-ceo.spec_pipeline.review_runner")


@dataclass
class ReviewPacket:
    verdict: str  # PASS, PASS_WITH_WARNINGS, BLOCKED
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "blockers": self.blockers,
            "warnings": self.warnings,
        }


def run_review(workspace: str, *, oracles: dict[str, bool] | None = None) -> ReviewPacket:
    """Static review lenses — oracles + diff heuristics."""
    blockers: list[str] = []
    warnings: list[str] = []
    oracles = oracles or {}

    if not oracles.get("import_ok", True):
        blockers.append("import check failed: from app.server.main import app")
    if not oracles.get("pytest_ok", True):
        blockers.append("pytest failed")
    if not oracles.get("tsc_ok", True):
        blockers.append("dashboard tsc failed")

    try:
        proc = subprocess.run(
            ["git", "-C", workspace, "diff", "--stat", "HEAD"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        diff_stat = (proc.stdout or "").strip()
        if not diff_stat:
            warnings.append("empty diff — nothing to review")
    except (subprocess.SubprocessError, OSError):
        warnings.append("could not read diff stat")

    # Credential pattern scan on changed files
    for path in _changed_py_files(workspace):
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        for needle in ("sk-ant-", "lin_api_", "postgres://", "Bearer "):
            if needle in text:
                blockers.append(f"credential pattern {needle!r} in {path}")

    if blockers:
        return ReviewPacket(verdict="BLOCKED", blockers=blockers, warnings=warnings)
    if warnings:
        return ReviewPacket(verdict="PASS_WITH_WARNINGS", warnings=warnings)
    return ReviewPacket(verdict="PASS")


def _changed_py_files(workspace: str) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", workspace, "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        return [
            str(Path(workspace) / ln.strip())
            for ln in (proc.stdout or "").splitlines()
            if ln.strip().endswith((".py", ".ts", ".tsx"))
        ]
    except (subprocess.SubprocessError, OSError):
        return []
