"""tests/mesh_helpers.py — shared fixtures-support for the mesh runner suites.

`test_mesh_runner_idle_autoclaim.py` and `test_mesh_runner_claim_reporting.py`
both load `mesh/runner.py` by path, both need a sentinel to end `main()`'s
loop deliberately, and both need a fake agent process that exits cleanly. Those
three were duplicated, and `ImmediateProc`/`_DoneProc` had drifted apart
slightly, which is the usual way two copies of a fake stop agreeing about what
they are faking.

Extracted when the autoclaim suite needed one more line and had none to spare:
it sits exactly on its 539-line size-gate baseline, and the repo's rule is to
extract rather than shave prose to fit.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, rel: str):
    """Import a repo module by path, exactly as the runner's tests expect.

    `mesh/runner.py` reads several environment variables at module scope
    (`MESH_REPO_DIR`, `MESH_MAX_CLAIMS`, …), so callers that want to control
    those must set or clear them BEFORE calling this.
    """
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Break(Exception):
    """Raised from a patched sleep to end `main()`'s loop deliberately.

    The loop only reaches its poll sleep once the work queue has drained, so
    arriving here is itself the assertion that it drained rather than spinning.
    """


class ImmediateProc:
    """A fake agent process that has already exited cleanly on first poll.

    `returncode` is set as well as `poll()` because `_wait_for_agent` reads
    `getattr(proc, "returncode", status)` — without it the attribute lookup
    falls through to the poll status, which happens to agree here but would
    hide a real divergence in any test that set a non-zero exit.
    """

    returncode = 0

    def poll(self):
        """Clean exit, immediately — so `_wait_for_agent` lands `done`."""
        return 0

    def wait(self, timeout=None):
        """Already exited; nothing to wait for."""
        return 0

    def terminate(self):
        """No-op: there is no real process to signal."""

    def kill(self):
        """No-op: there is no real process to signal."""
