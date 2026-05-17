"""Tests for the BUBUS_ENABLED env-flag gateway (DORMANT by default)."""
import os
from unittest.mock import patch

import pytest


@pytest.mark.parametrize("falsy", ["", "0", "false", "FALSE", None])
def test_bubus_disabled_by_default(falsy):
    """BUBUS_ENABLED unset / falsy → legacy path."""
    env = {"BUBUS_ENABLED": falsy} if falsy is not None else {}
    with patch.dict(os.environ, env, clear=True):
        from swarm.board.dispatch import bubus_enabled
        assert bubus_enabled() is False


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes"])
def test_bubus_enabled_on_explicit_flag(truthy):
    """BUBUS_ENABLED in {1, true, yes} → bubus path."""
    with patch.dict(os.environ, {"BUBUS_ENABLED": truthy}):
        from swarm.board.dispatch import bubus_enabled
        assert bubus_enabled() is True


def test_dispatch_callable_with_legacy_path():
    """The dispatch entrypoint is importable and callable (legacy path)."""
    from swarm.board import dispatch
    assert callable(dispatch.dispatch)
    assert dispatch.bubus_enabled() is False
