"""
conftest.py — shared pytest fixtures for Pi-CEO unit tests.
"""
import os
import tempfile
from pathlib import Path

import pytest


KANBAN_TEST_BOARD = "pi-dev-ops-pytest"
KANBAN_TEST_TENANT = "pi-dev-ops-pytest"
_KANBAN_TEST_ROOT = Path(tempfile.mkdtemp(prefix="pi-dev-ops-pytest-kanban-")).resolve()


def _pin_kanban_environment() -> None:
    """Replace any worker-provided Kanban context before test collection."""
    os.environ["PI_DEV_TEST_KANBAN_ROOT"] = str(_KANBAN_TEST_ROOT)
    os.environ["HERMES_KANBAN_DB"] = str(_KANBAN_TEST_ROOT / "kanban.db")
    os.environ["HERMES_KANBAN_BOARD"] = KANBAN_TEST_BOARD
    os.environ["HERMES_KANBAN_HOME"] = str(_KANBAN_TEST_ROOT)
    os.environ["HERMES_KANBAN_WORKSPACES_ROOT"] = str(
        _KANBAN_TEST_ROOT / "workspaces"
    )
    os.environ["HERMES_TENANT"] = KANBAN_TEST_TENANT
    os.environ.pop("HERMES_KANBAN_TASK", None)
    os.environ.pop("HERMES_KANBAN_RUN_ID", None)


def assert_kanban_environment_isolated() -> None:
    """Fail closed if a test redirects Kanban outside its private root."""
    root = _KANBAN_TEST_ROOT
    if Path(os.environ["PI_DEV_TEST_KANBAN_ROOT"]).resolve() != root:
        raise AssertionError("Kanban test root pin was changed")
    database = Path(os.environ["HERMES_KANBAN_DB"]).resolve()
    if not database.is_relative_to(root):
        raise AssertionError(f"Kanban test DB escaped private root: {database}")
    support_paths = {
        "HERMES_KANBAN_HOME": (root, "Kanban test home pin was changed"),
        "HERMES_KANBAN_WORKSPACES_ROOT": (
            root / "workspaces",
            "Kanban test workspaces pin was changed",
        ),
    }
    for key, (expected, message) in support_paths.items():
        value = os.environ.get(key)
        if value is None or Path(value).resolve() != expected:
            raise AssertionError(message)
    if os.environ.get("HERMES_KANBAN_BOARD") != KANBAN_TEST_BOARD:
        raise AssertionError("Kanban test board pin was changed")
    if os.environ.get("HERMES_TENANT") != KANBAN_TEST_TENANT:
        raise AssertionError("Kanban test tenant pin was changed")
    for key in ("HERMES_KANBAN_TASK", "HERMES_KANBAN_RUN_ID"):
        if key in os.environ:
            raise AssertionError(f"Live worker context leaked into tests: {key}")


_pin_kanban_environment()

# Set required env vars before any app imports
os.environ.setdefault("TAO_PASSWORD", "test-password-ci")
os.environ.setdefault("TAO_SESSION_SECRET", "test-session-secret-32-chars-xxxx")
os.environ.setdefault("TAO_EVALUATOR_ENABLED", "false")


@pytest.fixture(autouse=True)
def _guard_kanban_environment():
    """Check every test boundary so a leaked Board target cannot go unnoticed."""
    assert_kanban_environment_isolated()
    yield
    assert_kanban_environment_isolated()


@pytest.fixture(scope="session")
def kanban_test_root() -> Path:
    return _KANBAN_TEST_ROOT
