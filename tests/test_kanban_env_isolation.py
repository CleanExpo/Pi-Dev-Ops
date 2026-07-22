"""Regression coverage for pytest isolation from the live Hermes Kanban board."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFTEST = REPO_ROOT / "conftest.py"
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


def test_debate_fixture_cannot_create_or_change_inherited_board(tmp_path):
    """Replay the exact producer with a frozen decoy DB outside pytest scratch."""
    inherited_db = tmp_path / "inherited-live-board-copy.db"
    sentinel = b"frozen-live-board-copy\n"
    inherited_db.write_bytes(sentinel)
    fake_hermes = tmp_path / "hermes-fixture"
    fake_hermes.write_text(
        "#!/bin/sh\n"
        "printf 'fixture-mutation\\n' >> \"$HERMES_KANBAN_DB\"\n"
        "printf '{\"task_id\": \"k-fixture\"}'\n",
        encoding="utf-8",
    )
    fake_hermes.chmod(0o755)
    before = hashlib.sha256(inherited_db.read_bytes()).hexdigest()
    env = _poisoned_env(*KANBAN_ENV_KEYS)
    env["HERMES_KANBAN_DB"] = str(inherited_db)
    env["HERMES_BIN"] = str(fake_hermes)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_debate_runner.py::test_happy_path_both_sides_succeed",
            "-q",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    after = hashlib.sha256(inherited_db.read_bytes()).hexdigest()
    assert after == before
    assert inherited_db.read_bytes() == sentinel