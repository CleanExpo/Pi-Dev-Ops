"""Repository-wide pytest safety boundaries."""

import atexit
import os
import shutil
import tempfile
from pathlib import Path


_KANBAN_TEST_ROOT = Path(
    tempfile.mkdtemp(prefix="pi-dev-ops-pytest-kanban-")
).resolve()


def _remove_kanban_test_root() -> None:
    shutil.rmtree(_KANBAN_TEST_ROOT, ignore_errors=True)


# Pytest imports this file before test collection and fixture creation. Rebind
# the only permitted Board locator to a run-local scratch DB, and remove
# ambient board/task identity so nested Hermes subprocesses cannot target the
# live dispatcher state inherited from a Kanban worker shell.
os.environ["HERMES_KANBAN_DB"] = str(_KANBAN_TEST_ROOT / "kanban.db")
for _key in (
    "HERMES_KANBAN_BOARD",
    "HERMES_KANBAN_TASK",
    "HERMES_KANBAN_RUN_ID",
):
    os.environ.pop(_key, None)
atexit.register(_remove_kanban_test_root)
