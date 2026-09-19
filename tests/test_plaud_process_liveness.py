"""Windows process probes must preserve locks without sending console events."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import plaud_ingest  # noqa: E402


def test_windows_pid_probe_never_sends_console_signals(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows console signal regression")

    def forbidden_signal(*args):
        raise AssertionError("A Windows liveness probe must not call os.kill")

    monkeypatch.setattr(os, "kill", forbidden_signal)
    assert plaud_ingest._pid_alive(os.getpid()) is True
    assert plaud_ingest._pid_alive(999999) is False
    assert plaud_ingest._pid_alive(0) is False
    assert plaud_ingest._pid_alive(-1) is False


@pytest.mark.skipif(os.name != "nt", reason="Windows process handle API")
@pytest.mark.parametrize(
    "handle,wait_result,error,expected",
    [(None, 0, 5, True), (None, 0, 87, False),
     (123, 0, 0, False), (123, 258, 0, True),
     (123, 0xFFFFFFFF, 5, None)],
)
def test_windows_pid_probe_preserves_locks_and_closes_handles(
    monkeypatch, handle, wait_result, error, expected,
):
    import ctypes

    api = MagicMock()
    api.OpenProcess.return_value = handle
    api.WaitForSingleObject.return_value = wait_result
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: api)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: error)
    if expected is None:
        with pytest.raises(OSError):
            plaud_ingest._pid_alive(12345)
    else:
        assert plaud_ingest._pid_alive(12345) is expected
    if handle:
        api.WaitForSingleObject.assert_called_once_with(handle, 0)
        api.CloseHandle.assert_called_once_with(handle)
    else:
        api.WaitForSingleObject.assert_not_called()
        api.CloseHandle.assert_not_called()


def test_ingest_pid_wrapper_works_when_loaded_by_path(monkeypatch):
    spec = importlib.util.spec_from_file_location("plaud_by_path", ROOT / "scripts" / "plaud_ingest.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert module._pid_alive(0) is False


def test_direct_cli_help_works_from_another_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "plaud_ingest.py"), "--help"],
        cwd=tmp_path, capture_output=True, text=True, timeout=15,
        creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                       | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)),
    )
    assert result.returncode == 0, result.stderr
    assert "--dry-run" in result.stdout


