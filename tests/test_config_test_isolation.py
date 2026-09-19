"""Collection must not load workstation env files into application tests."""

from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def boundary(pytestconfig):
    target = Path(__file__).resolve().parents[1] / "conftest.py"
    return next(plugin for plugin in pytestconfig.pluginmanager.get_plugins()
                if getattr(plugin, "__file__", None)
                and Path(plugin.__file__).resolve() == target)


@pytest.mark.parametrize("relative", [".env", ".env.local", "app/.env.local"])
@pytest.mark.parametrize("mode", ["r", "rb"])
def test_live_env_reads_are_empty_without_opening_disk(monkeypatch, boundary, relative, mode):
    disk_open = Mock(side_effect=AssertionError("must not open workstation env files"))
    monkeypatch.setattr(boundary, "_PATH_OPEN", disk_open)
    path = Path(boundary.__file__).parent / relative
    with boundary._isolated_credential_open(path, mode) as stream:
        assert stream.read() == (b"" if "b" in mode else "")
    disk_open.assert_not_called()


def test_live_env_writes_are_rejected_without_opening_disk(monkeypatch, boundary):
    disk_open = Mock(side_effect=AssertionError("must not open workstation env files"))
    monkeypatch.setattr(boundary, "_PATH_OPEN", disk_open)
    with pytest.raises(PermissionError):
        boundary._isolated_credential_open(Path(boundary.__file__).parent / ".env", "w")
    disk_open.assert_not_called()
