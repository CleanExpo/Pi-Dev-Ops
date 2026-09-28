"""
conftest.py — shared pytest fixtures for Pi-CEO unit tests.
"""
import os

# Set required env vars before any app imports
os.environ.setdefault("TAO_PASSWORD", "test-password-ci")
os.environ.setdefault("TAO_SESSION_SECRET", "test-session-secret-32-chars-xxxx")
os.environ.setdefault("TAO_EVALUATOR_ENABLED", "false")
# RA-7802: a real runner starts its agent once to prove it can work. Unit tests
# fake the agent, so the gate is off here; test_mesh_node_health turns it back on.
os.environ.setdefault("MESH_PREFLIGHT", "0")
