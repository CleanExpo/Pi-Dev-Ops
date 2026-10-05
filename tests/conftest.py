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
