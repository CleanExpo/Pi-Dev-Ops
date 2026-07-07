"""Tests for the Terminal Orchestrator read API (RA-7012 pane-UI backend)."""
from __future__ import annotations

from app.server.routes import terminal


def test_routes_registered_and_auth_gated():
    paths = {r.path: r for r in terminal.router.routes}
    assert "/api/terminal/sessions" in paths
    assert "/api/terminal/tail" in paths
    # both endpoints carry the require_auth dependency
    for r in terminal.router.routes:
        assert r.dependencies, f"{r.path} must be auth-gated"


async def test_sessions_never_500s_on_observer_failure(monkeypatch):
    """The dashboard fetch must degrade gracefully, not 500, if libtmux/observer errors."""
    import swarm.tmux_observer as obs

    monkeypatch.setattr(obs, "list_sessions", lambda **k: (_ for _ in ()).throw(RuntimeError("no tmux")))
    out = await terminal.sessions()
    assert out["sessions"] == []
    assert "no tmux" in out["error"]


async def test_tail_returns_observer_shape(monkeypatch):
    import swarm.tmux_observer as obs

    monkeypatch.setattr(obs, "tail", lambda s, lines=100, **k: {"session": s, "lines": ["a", "b"]})
    out = await terminal.tail(session="w1", lines=2)
    assert out == {"session": "w1", "lines": ["a", "b"]}


def test_app_imports_with_terminal_router():
    from app.server.main import app

    assert any(getattr(r, "path", "").startswith("/api/terminal") for r in app.routes)
