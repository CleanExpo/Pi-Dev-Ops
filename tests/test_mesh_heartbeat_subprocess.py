"""Heartbeat probes must not create visible consoles on Windows."""
import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def heartbeat(monkeypatch):
    # Prevent import-time fallback reads of workstation credentials.
    monkeypatch.setenv("PI_CEO_API_URL", "https://example.invalid")
    monkeypatch.setenv("PI_CEO_API_KEY", "test-only")
    source = Path(__file__).resolve().parents[1] / "mesh" / "heartbeat.py"
    spec = importlib.util.spec_from_file_location("heartbeat_under_test", source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("platform_name", ["win32", "linux", "darwin"])
def test_probe_hides_windows_console_and_preserves_output(heartbeat, platform_name):
    run = Mock(return_value=SimpleNamespace(stdout="  ready\n"))
    heartbeat.sys = SimpleNamespace(platform=platform_name)
    heartbeat.subprocess = SimpleNamespace(run=run)
    if platform_name == "win32":
        heartbeat.subprocess.CREATE_NO_WINDOW = 0x08000000

    assert heartbeat._run(["probe", "--status"], timeout=7) == "ready"
    run.assert_called_once_with(
        ["probe", "--status"], capture_output=True, text=True, timeout=7,
        creationflags=0x08000000 if platform_name == "win32" else 0,
    )


@pytest.mark.parametrize("platform_name", ["win32", "linux"])
@pytest.mark.parametrize("error", [subprocess.TimeoutExpired("probe", 2), OSError("missing")])
def test_failed_probe_remains_best_effort(heartbeat, platform_name, error):
    run = Mock(side_effect=error)
    heartbeat.sys = SimpleNamespace(platform=platform_name)
    heartbeat.subprocess = SimpleNamespace(run=run, CREATE_NO_WINDOW=0x08000000)

    assert heartbeat._run(["probe"], timeout=2) == ""
    assert run.call_args.kwargs["creationflags"] == (
        0x08000000 if platform_name == "win32" else 0
    )
