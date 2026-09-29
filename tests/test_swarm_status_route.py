"""RA-7849: /api/swarm/status carries the flags the dashboard needs to name the swarm's state."""
import asyncio

import pytest

from app.server.routes import swarm as swarm_routes


@pytest.mark.parametrize("shadow_env,want", [(None, True), ("1", True), ("0", False)])
def test_swarm_status_reports_shadow_with_the_runtime_default(monkeypatch, shadow_env, want):
    if shadow_env is None:
        monkeypatch.delenv("TAO_SWARM_SHADOW", raising=False)
    else:
        monkeypatch.setenv("TAO_SWARM_SHADOW", shadow_env)
    monkeypatch.delenv("TAO_SWARM_ENABLED", raising=False)
    out = asyncio.run(swarm_routes.swarm_status())
    assert out["swarm_shadow_env"] is want
    assert out["swarm_enabled_env"] is False
