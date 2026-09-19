"""Background health checks must stay hidden and reap timed-out children."""

import asyncio
import subprocess
from unittest.mock import AsyncMock, Mock

import pytest

from app.server.routes import health


@pytest.mark.parametrize("timeout", [False, True])
def test_cli_poll_is_hidden_and_reaps_timeout(monkeypatch, timeout):
    proc = Mock(returncode=0)
    proc.wait = AsyncMock(side_effect=[asyncio.TimeoutError(), None] if timeout else [None])
    spawn = AsyncMock(return_value=proc)
    monkeypatch.setattr(health.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(health.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError))
    monkeypatch.setattr(health, "_claude_ok", False)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(health._poll_claude_cli())
    assert spawn.call_args.kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert health._claude_ok is (not timeout)
    if timeout:
        proc.kill.assert_called_once()
        assert proc.wait.await_count == 2
