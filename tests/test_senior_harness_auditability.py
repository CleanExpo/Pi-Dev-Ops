"""Executable size limits for the security-critical Senior Harness slice."""
from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPO_ROOT / "skills" / "senior-harness" / "scripts"
TEST_ROOT = REPO_ROOT / "tests"
MAX_FILE_LINES = 299
MAX_FUNCTION_LINES = 39


def _governed_files() -> list[Path]:
    files = [
        REPO_ROOT / "app" / "server" / "task_routing.py",
        REPO_ROOT / "app" / "server" / "routing_schema.py",
    ]
    files.extend(SCRIPT_ROOT.glob("*.py"))
    files.extend(TEST_ROOT.glob("test_senior_harness_*.py"))
    files.extend(TEST_ROOT.glob("test_grill_session_*.py"))
    for support_name in ("_senior_harness_setup_support.py", "_harness_entry_support.py"):
        support = TEST_ROOT / support_name
        if support.is_file():
            files.append(support)
    return sorted(set(files))


def test_governed_files_remain_under_300_lines() -> None:
    oversized = {
        path.relative_to(REPO_ROOT).as_posix(): len(path.read_text(encoding="utf-8").splitlines())
        for path in _governed_files()
        if len(path.read_text(encoding="utf-8").splitlines()) > MAX_FILE_LINES
    }
    assert not oversized, f"Senior Harness files exceed {MAX_FILE_LINES} lines: {oversized}"


def test_governed_functions_remain_under_40_lines() -> None:
    oversized: dict[str, int] = {}
    for path in _governed_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                size = (node.end_lineno or node.lineno) - node.lineno + 1
                if size > MAX_FUNCTION_LINES:
                    key = f"{path.relative_to(REPO_ROOT).as_posix()}:{node.lineno}:{node.name}"
                    oversized[key] = size
    assert not oversized, f"Senior Harness functions exceed {MAX_FUNCTION_LINES} lines: {oversized}"
