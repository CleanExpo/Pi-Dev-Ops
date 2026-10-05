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
import sys
import types
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


def secret_token() -> str:
    """An Anthropic-API-key-shaped string, assembled at runtime so no key-like literal sits in source."""
    return "sk-ant-" + "api03-" + "Ab3_" * 24


def server_only_secret() -> str:
    """A secret shape the runner's transcript bank does not recognise (UNI-2796 review round 4)."""
    return "token='" + "qwertyuiop" + "asdfghjklz'"


def hostile_exception(base):
    """An exception class whose NAME is the secret (UNI-2796 review round 5)."""
    return type("SECRET_QWERTY_12345", (base,), {})


class UnprintableError(Exception):
    """An exception whose `__str__` raises (UNI-2796 review round 13)."""

    def __str__(self):
        raise ValueError("cannot print")


class InterruptOnce:
    """A real Popen whose first call to `step` raises KeyboardInterrupt (UNI-2796 review round 14).

    For `terminate` the interrupt lands after the signal is sent, so the agent
    still exits promptly; for every other step it lands before the call.
    """

    def __init__(self, proc, step):
        self._proc, self._step = proc, step

    def __getattr__(self, name):
        attr = getattr(self._proc, name)
        if name != self._step or not callable(attr):
            return attr

        def once(*args, **kwargs):
            self._step = None
            if name == "terminate":
                attr(*args, **kwargs)
            raise KeyboardInterrupt

        return once
# RA-7780: stands in for `mesh/ship_run.py` in suites that fake `subprocess.run` and
# are not about shipping. Their fake returns None, which the real module cannot read,
# and a run must ship before it lands `done`. The module's own behaviour is proven
# against real git in tests/test_mesh_runner_ships_own_work.py.
SHIPPED = types.SimpleNamespace(start_point=lambda *a, **k: "0" * 40,
                                settle=lambda *a, **k: None)


def short_temp_alias(tmp_path: Path) -> tuple[Path, Path]:
    """(alias, real): a temp dir and another name for it (RA-7801).

    On Windows, creating a folder with a space makes a real 8.3 short name
    (`DISAST~1`), exactly what the PC's scheduled task was handed as TEMP.
    Elsewhere a symlink stands in for it. On Windows there is no fallback: a
    missing short name fails the test, so a green run always exercised one."""
    real = tmp_path / "Disaster Recovery 4"
    real.mkdir()
    if sys.platform == "win32":
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        got = ctypes.windll.kernel32.GetShortPathNameW(str(real), buf, len(buf))
        assert got and "~" in Path(buf.value).name, f"no 8.3 short name for {real}: {buf.value!r}"
        assert Path(buf.value).resolve() == real.resolve()
        return Path(buf.value), real.resolve()
    alias = tmp_path / "short-alias"
    alias.symlink_to(real, target_is_directory=True)
    return alias, real.resolve()


# RA-7910: claim/self re-reads each cached candidate by id before claiming it, so a
# fake Linear that serves the queue must also answer `query{issue(id:"X")…}` as Linear
# does: that one ticket, or null. A ticket the list query returned is in the mesh pool
# (that is the query's filter), so it reads back open and labelled unless it says otherwise.
IN_POOL = {"labels": {"nodes": [{"name": "mesh:auto"}]}, "state": {"name": "Todo", "type": "unstarted"}}


def is_issue_read(query: str) -> bool:
    """True for Linear's single-ticket read (`mesh_lanes.explicit`)."""
    return query.startswith("query{issue(")


def issue_by_id(query: str, nodes) -> dict:
    """Linear's answer to `query{issue(id:"X")…}` over the fake's queue."""
    ident = query.split('issue(id:"', 1)[1].split('"', 1)[0]
    node = next((n for n in nodes if n.get("identifier") == ident), None)
    return {"issue": None if node is None else {**IN_POOL, **node}}
