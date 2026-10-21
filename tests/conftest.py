"""
conftest.py — shared pytest fixtures for Pi-CEO unit tests.
"""
import os
import sys

import pytest

# Set required env vars before any app imports
os.environ.setdefault("TAO_PASSWORD", "test-password-ci")
os.environ.setdefault("TAO_SESSION_SECRET", "test-session-secret-32-chars-xxxx")
os.environ.setdefault("TAO_EVALUATOR_ENABLED", "false")
# RA-7802: a real runner starts its agent once to prove it can work. Unit tests
# fake the agent, so the gate is off here; test_mesh_node_health turns it back on.
os.environ.setdefault("MESH_PREFLIGHT", "0")
os.environ.setdefault("MESH_SELF_UPDATE", "0")  # never fetch or check out code from a unit test
# RA-7798: runner tests leave agents unstoppable on purpose; never record them in the node's real file.
os.environ["MESH_LEFT_RUNNING"] = os.path.join(__import__("tempfile").mkdtemp(prefix="mesh-left-"), "left.json")


@pytest.fixture(autouse=True)
def _fresh_left_running_record(tmp_path, monkeypatch):
    """Each test gets its own record: one test's unstoppable agent must not block another's update."""
    path = tmp_path / "mesh-left-running.json"
    monkeypatch.setenv("MESH_LEFT_RUNNING", str(path))
    module = sys.modules.get("left_running")
    if module is not None:
        monkeypatch.setattr(module, "PATH", path)
        monkeypatch.setattr(module, "_UNRECORDED", [False])


@pytest.fixture(autouse=True)
def _fresh_mesh_queue_cache():
    """RA-7910: claim/self shares one Linear read per TTL; never let it leak between tests."""
    module = sys.modules.get("app.server.mesh_queue_cache")
    if module is not None:
        module.reset()
    yield
    module = sys.modules.get("app.server.mesh_queue_cache")
    if module is not None:
        module.reset()


@pytest.fixture
def legacy_loopback_ollama_transport(monkeypatch):
    """Ollama-removal STAGE 1 (founder ruling 21/10/2026) took the loopback-Ollama
    allowance out of provider_policy, so every Ollama dispatch now fails closed.
    The Ollama adapters themselves are deleted in STAGE 2. Until then, tests of
    those adapters' own mechanics (HTTP decoding, identity evidence, dispatch)
    opt in to this stub, which restores the old loopback-only rule for "ollama"
    and delegates every other provider to the real policy. The real policy's
    refusal is pinned by tests/test_provider_policy_margot_free.py.
    """
    from urllib.parse import urlsplit

    from app.server import provider_policy

    real = provider_policy.require_transport

    def require_transport(provider, **kw):
        if provider != "ollama":
            return real(provider, **kw)
        url = kw.get("endpoint_url")
        endpoint = urlsplit(url if url is not None else
                            (os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"))
        if endpoint.scheme not in {"http", "https"} or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise provider_policy.ProviderPolicyError("subscription_only: unverified remote Ollama transport")
        return {"billing_class": "local", "auth_verified": True, "source": "loopback_transport"}

    monkeypatch.setattr(provider_policy, "require_transport", require_transport)
