"""Repository-wide pytest safety boundaries."""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest


_KANBAN_TEST_ROOT = Path(
    tempfile.mkdtemp(prefix="pi-dev-ops-pytest-kanban-")
).resolve()
_KANBAN_TEST_DATABASE = (_KANBAN_TEST_ROOT / "kanban.db").resolve()
_FORBIDDEN_KANBAN_CONTEXT = (
    "HERMES_KANBAN_BOARD",
    "HERMES_KANBAN_TASK",
    "HERMES_KANBAN_RUN_ID",
)


def _remove_kanban_test_root() -> None:
    shutil.rmtree(_KANBAN_TEST_ROOT, ignore_errors=True)


# Pytest imports this file before test collection and fixture creation. Rebind
# the only permitted Board locator to a run-local scratch DB, and remove
# ambient board/task identity so nested Hermes subprocesses cannot target the
# live dispatcher state inherited from a Kanban worker shell.
os.environ["HERMES_KANBAN_DB"] = str(_KANBAN_TEST_DATABASE)
for _key in _FORBIDDEN_KANBAN_CONTEXT:
    os.environ.pop(_key, None)
atexit.register(_remove_kanban_test_root)


def assert_kanban_environment_isolated() -> None:
    """Fail closed when pytest's Board target or parent identity escapes."""
    database_raw = os.environ.get("HERMES_KANBAN_DB")
    if not database_raw:
        raise AssertionError("HERMES_KANBAN_DB test pin is missing")
    database = Path(database_raw).resolve()
    if not database.is_relative_to(_KANBAN_TEST_ROOT):
        raise AssertionError(f"Kanban test DB escaped private root: {database}")
    if database != _KANBAN_TEST_DATABASE:
        raise AssertionError(f"HERMES_KANBAN_DB test pin changed: {database}")
    for key in _FORBIDDEN_KANBAN_CONTEXT:
        if key in os.environ:
            raise AssertionError(f"Parent Kanban context leaked into tests: {key}")


@pytest.fixture(autouse=True)
def _guard_kanban_environment():
    """Check the isolation boundary before and after every test."""
    assert_kanban_environment_isolated()
    yield
    assert_kanban_environment_isolated()
