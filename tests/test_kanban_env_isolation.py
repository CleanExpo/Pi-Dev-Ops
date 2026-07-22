"""Regression coverage for pytest isolation from the live Hermes Kanban board."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFTEST = REPO_ROOT / "conftest.py"
FAKE_HERMES = REPO_ROOT / "tests" / "fixtures" / "fake_hermes_kanban.py"
KANBAN_ENV_KEYS = (
    "HERMES_KANBAN_DB",
    "HERMES_KANBAN_BOARD",
    "HERMES_KANBAN_TASK",
    "HERMES_KANBAN_RUN_ID",
)


def _poisoned_env(*keys: str) -> dict[str, str]:
    env = os.environ.copy()
    for key in KANBAN_ENV_KEYS:
        env.pop(key, None)
    for key in keys:
        env[key] = f"inherited-{key.lower()}"
    return env


@pytest.mark.parametrize(
    "poisoned_keys",
    [(key,) for key in KANBAN_ENV_KEYS] + [KANBAN_ENV_KEYS],
    ids=["db", "board", "task", "run-id", "all"],
)
def test_conftest_isolates_all_kanban_env_before_fixture_creation(poisoned_keys):
    """Import-time bootstrap replaces inherited Board state before collection."""
    script = f"""
import json, os, runpy, tempfile
runpy.run_path({str(CONFTEST)!r})
db = os.environ.get("HERMES_KANBAN_DB")
db_abs = os.path.realpath(db) if db else None
temp_root = os.path.realpath(tempfile.gettempdir())
print(json.dumps({{
    "db": db,
    "db_parent_exists": bool(db and os.path.isdir(os.path.dirname(db))),
    "db_inside_scratch": bool(db_abs and os.path.commonpath([db_abs, temp_root]) == temp_root),
    "board": os.environ.get("HERMES_KANBAN_BOARD"),
    "task": os.environ.get("HERMES_KANBAN_TASK"),
    "run_id": os.environ.get("HERMES_KANBAN_RUN_ID"),
}}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=_poisoned_env(*poisoned_keys),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    db = Path(observed["db"])
    assert db.name == "kanban.db"
    assert db.parent.name.startswith("pi-dev-ops-pytest-kanban-")
    assert observed["db_parent_exists"] is True
    assert observed["db_inside_scratch"] is True
    assert observed["board"] is None
    assert observed["task"] is None
    assert observed["run_id"] is None


PRODUCERS = {
    "restoreassist": (
        "test_happy_path_both_sides_succeed",
        ["[CFO@restoreassist] debate — ship today's CFO brief"],
    ),
    "parallel": (
        "test_run_debates_parallel_runs_many",
        [f"[CFO@b{index}] debate — t{index}" for index in range(4)],
    ),
}
FORBIDDEN_CHILD_KEYS = {
    "HERMES_KANBAN_BOARD",
    "HERMES_KANBAN_TASK",
    "HERMES_KANBAN_RUN_ID",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "STRIPE_API_KEY",
    "PYTHONPATH",
    "VIRTUAL_ENV",
}


def _query(database: Path, statement: str) -> list[tuple[Any, ...]]:
    with sqlite3.connect(str(database)) as connection:
        return connection.execute(statement).fetchall()


def _root_conftest(request):
    for _name, plugin in request.config.pluginmanager.list_name_plugin():
        if Path(getattr(plugin, "__file__", "")).resolve() == CONFTEST.resolve():
            return plugin
    raise AssertionError("repository-root conftest plugin was not loaded")


def _run_producer_case(tmp_path: Path, producer: str, mode: str) -> dict[str, Any]:
    if mode == "normal" and os.environ.get("PI_DEV_TEST_FORCE_MISSING_HERMES") == "1":
        mode = "missing"
    case_home = tmp_path / f"{producer}-{mode}"
    working_directory = case_home / "cwd"
    working_directory.mkdir(parents=True)
    (case_home / "mode.txt").write_text(mode, encoding="utf-8")
    if mode != "missing":
        shutil.copyfile(FAKE_HERMES, working_directory / "kanban")

    decoy = case_home / "inherited-live-board-copy.db"
    decoy.write_bytes(b"frozen-live-board-copy\n")
    before = hashlib.sha256(decoy.read_bytes()).hexdigest()
    env = _poisoned_env(*KANBAN_ENV_KEYS)
    env.update({
        "HOME": str(case_home),
        "HERMES_KANBAN_DB": str(decoy),
        "HERMES_BIN": (
            str(case_home / "definitely-missing-hermes")
            if mode == "missing" else sys.executable
        ),
        "PYTHONPATH": "POISONED_PYTHONPATH_MUST_NOT_REACH_CHILD",
        "VIRTUAL_ENV": "POISONED_VIRTUAL_ENV_MUST_NOT_REACH_CHILD",
        "STRIPE_API_KEY": "POISONED_PROVIDER_KEY_MUST_NOT_REACH_CHILD",
    })
    node, expected_titles = PRODUCERS[producer]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            f"{REPO_ROOT / 'tests' / 'test_debate_runner.py'}::{node}",
            "-q",
        ],
        cwd=working_directory,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    audit = case_home / "audit.sqlite"
    snapshot = case_home / "target_snapshot.sqlite"
    invocations = _query(
        audit,
        "SELECT env_names_json,db_path FROM invocations ORDER BY seq",
    ) if audit.exists() else []
    rows = _query(
        snapshot,
        "SELECT title,body,tenant,skills_json FROM tasks ORDER BY title,id",
    ) if snapshot.exists() else []
    return {
        "result": result,
        "decoy_unchanged": hashlib.sha256(decoy.read_bytes()).hexdigest() == before,
        "decoy_bytes": decoy.read_bytes(),
        "decoy": decoy,
        "invocations": invocations,
        "rows": rows,
        "expected_titles": expected_titles,
        "wrong_db_exists": (case_home / "wrong.sqlite").exists(),
    }


def _violations(case: dict[str, Any]) -> set[str]:
    violations: set[str] = set()
    result = case["result"]
    expected_titles = case["expected_titles"]
    invocations = case["invocations"]
    rows = case["rows"]
    if result.returncode != 0:
        violations.add("pytest")
    if len(invocations) != len(expected_titles):
        violations.add("invocations")
    if [row[0] for row in rows] != sorted(expected_titles):
        violations.add("rows")
    if not case["decoy_unchanged"] or case["decoy_bytes"] != b"frozen-live-board-copy\n":
        violations.add("decoy")
    if case["wrong_db_exists"]:
        violations.add("wrong-db")
    for env_names_json, database in invocations:
        names = set(json.loads(env_names_json))
        path = Path(database)
        if names & FORBIDDEN_CHILD_KEYS:
            violations.add("child-env")
        if (
            path.name != "kanban.db"
            or not path.parent.name.startswith("pi-dev-ops-pytest-kanban-")
            or path.resolve() == case["decoy"].resolve()
        ):
            violations.add("path")
    for _title, body, tenant, skills_json in rows:
        if (
            not body
            or "### Drafter (CFO) artifact" not in body
            or "### Red-team critique" not in body
            or tenant != "pi-ceo"
            or json.loads(skills_json) != ["debate-summary"]
        ):
            violations.add("contract")
    return violations


@pytest.mark.parametrize("producer", PRODUCERS)
def test_exact_debate_producers_write_only_to_isolated_scratch(tmp_path, producer):
    case = _run_producer_case(tmp_path, producer, "normal")
    assert _violations(case) == set(), case["result"].stdout + case["result"].stderr


@pytest.mark.parametrize(
    ("producer", "mode", "expected_violation"),
    [
        ("restoreassist", "missing", "invocations"),
        ("restoreassist", "noop", "rows"),
        ("restoreassist", "nonzero", "rows"),
        ("restoreassist", "wrong_db", "wrong-db"),
        ("parallel", "omit_one", "rows"),
        ("parallel", "duplicate", "rows"),
    ],
)
def test_positive_sink_proof_rejects_broken_fakes(
    tmp_path, producer, mode, expected_violation,
):
    case = _run_producer_case(tmp_path, producer, mode)
    assert expected_violation in _violations(case)


def test_run_wide_guard_rejects_resolved_database_escape(
    monkeypatch, tmp_path, request,
):
    escaped_database = tmp_path.parent / "escaped-kanban.db"
    monkeypatch.setenv("HERMES_KANBAN_DB", str(escaped_database))
    with pytest.raises(AssertionError, match="escaped private root"):
        _root_conftest(request).assert_kanban_environment_isolated()


@pytest.mark.parametrize(
    "key",
    ["HERMES_KANBAN_BOARD", "HERMES_KANBAN_TASK", "HERMES_KANBAN_RUN_ID"],
)
def test_run_wide_guard_rejects_parent_board_or_identity(monkeypatch, key, request):
    monkeypatch.setenv(key, "escaped-parent-context")
    with pytest.raises(AssertionError, match=key):
        _root_conftest(request).assert_kanban_environment_isolated()
