"""Test fixtures for the bubus typed-event surface (DORMANT)."""
import pytest


@pytest.fixture(autouse=True)
def _stub_provider_ollama(monkeypatch):
    """Stub ``provider_ollama.call`` so wiring imports without a live daemon."""
    async def _fake_call(**kwargs):
        return 0, "stub-opinion " * 20, 0.0, None

    monkeypatch.setattr(
        "app.server.provider_ollama.call", _fake_call, raising=False
    )
