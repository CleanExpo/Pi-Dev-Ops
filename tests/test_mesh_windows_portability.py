"""tests/test_mesh_windows_portability.py — the runner works on a Windows node (RA-7801).

#800 opened each run's log with `os.O_NOFOLLOW` and `os.fchmod`. Neither exists
on Windows, so on the PC every build claim raised `AttributeError` before the
agent started and was reported `failed` (`runner_exception`). CI runs only on
Linux, where both exist, so nothing caught it. These tests take them away the way
Windows does and pin that the run record still opens, and that the worktree goes
under the platform temp dir rather than a hard-coded `/tmp`.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from mesh_helpers import load_module as _load  # noqa: E402

rr = _load("mesh_run_record_windows", "mesh/run_record.py")

RUN_ID = "0123abcd"  # the runner generates 8 hex characters (run_record._RUN_ID)


def test_run_record_opens_without_posix_only_os_calls(tmp_path, monkeypatch):
    """No O_NOFOLLOW and no fchmod, as on Windows: the log still opens."""
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    monkeypatch.delattr(os, "fchmod", raising=False)
    rec = rr.RunRecord(RUN_ID, tmp_path)
    try:
        assert rec.path == tmp_path / "mesh-runs" / f"{RUN_ID}.log"
        assert rec.path.exists()
    finally:
        rec.close()


def test_run_record_still_refuses_an_existing_file_without_o_nofollow(tmp_path, monkeypatch):
    """Dropping O_NOFOLLOW must not drop O_EXCL: a planted file is never reopened."""
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    planted = tmp_path / "mesh-runs" / f"{RUN_ID}.log"
    planted.parent.mkdir(parents=True)
    planted.write_bytes(b"earlier run")
    rec = rr.RunRecord(RUN_ID, tmp_path)
    assert rec.path is None
    assert planted.read_bytes() == b"earlier run"


def test_worktree_goes_under_the_platform_temp_dir(tmp_path, monkeypatch):
    """`/tmp` does not exist on Windows; the worktree follows tempfile.gettempdir()."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    runner = _load("mesh_runner_windows", "mesh/runner.py")
    assert runner.worktree_path("RA-1", "abcd") == tmp_path / "mesh-RA-1-abcd"
