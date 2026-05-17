"""tests/_sprinkle_helpers.py — shared fixture for the 4 sprinkle tests.

The sprinkle pattern: a deterministic cron pipeline that lazily imports
`app.server.provider_router` inside a private `_run_provider_call_blocking`
helper and routes the LLM call through `run_via_provider`. To test these
in isolation, we install a fake `provider_router` module on
`sys.modules` before the call site executes.

RA-3017 — shared by:
  * test_sprinkle_triage.py
  * test_sprinkle_feedback_loop.py
  * test_sprinkle_cron_fire_agents.py
  * test_sprinkle_lesson_clusters.py
"""
from __future__ import annotations

import sys
import types
from dataclasses import dataclass


@dataclass
class _ProviderModelStub:
    """Minimal stand-in for app.server.provider_router.ProviderModel."""
    provider: str = "ollama"
    model_id: str = "gemma4:26b"
    tier: str = "cheap"


class FakeProviderRouter:
    """Drop-in replacement for `app.server.provider_router` whose
    `run_via_provider` records each call and returns a scripted result.

    Usage:
        fake = FakeProviderRouter(response='{"verdict":"real"}')
        install_fake_router(monkeypatch, fake)
        result = sprinkle_under_test(...)
        assert len(fake.calls) == 1
        assert fake.calls[0]["role"] == "sprinkle.triage"
    """

    def __init__(
        self,
        response: str = "ok",
        rc: int = 0,
        error: str | None = None,
        raise_exc: Exception | None = None,
        provider_model: _ProviderModelStub | None = None,
    ):
        self.response = response
        self.rc = rc
        self.error = error
        self.raise_exc = raise_exc
        self.provider_model = provider_model or _ProviderModelStub()
        self.calls: list[dict] = []
        self.select_calls: list[str] = []

    async def run_via_provider(
        self,
        prompt: str,
        *,
        role: str,
        task_class: str = "default",
        timeout_s: int = 120,
        workspace: str | None = None,
        session_id: str = "",
        thinking: str = "adaptive",
    ):
        self.calls.append({
            "prompt": prompt, "role": role, "task_class": task_class,
            "timeout_s": timeout_s, "session_id": session_id,
            "thinking": thinking,
        })
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.rc, self.response, 0.0, self.error

    def run_via_provider_blocking(
        self,
        prompt: str,
        role: str,
        timeout_s: int = 120,
        *,
        log=None,
    ):
        self.calls.append({
            "prompt": prompt, "role": role, "task_class": "default",
            "timeout_s": timeout_s, "session_id": "",
            "thinking": "adaptive",
        })
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.rc, self.response, 0.0, self.error, self.provider_model

    def select_provider_model(self, role: str):
        self.select_calls.append(role)
        return self.provider_model


def install_fake_router(monkeypatch, fake: FakeProviderRouter) -> None:
    """Install `fake` as a stand-in for `app.server.provider_router`.

    Sprinkle helpers import `run_via_provider` and `select_provider_model`
    from that module inside the function body (PLC0415-noqa'd), so the
    fake must expose both attributes.
    """
    mod = types.ModuleType("app.server.provider_router")
    mod.run_via_provider = fake.run_via_provider
    mod.run_via_provider_blocking = fake.run_via_provider_blocking
    mod.select_provider_model = fake.select_provider_model
    # Some callers may want to introspect ProviderModel — expose a stub.
    mod.ProviderModel = _ProviderModelStub
    monkeypatch.setitem(sys.modules, "app.server.provider_router", mod)
