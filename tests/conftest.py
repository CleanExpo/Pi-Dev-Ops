"""
conftest.py — shared pytest fixtures for Pi-CEO unit tests.
"""
import os

# Set required env vars before any app imports
os.environ.setdefault("TAO_PASSWORD", "test-password-ci")
os.environ.setdefault("TAO_SESSION_SECRET", "test-session-secret-32-chars-xxxx")
os.environ.setdefault("TAO_EVALUATOR_ENABLED", "false")
# RA-7798: runner tests leave agents unstoppable on purpose; never record them in the node's real file.
os.environ["MESH_LEFT_RUNNING"] = os.path.join(__import__("tempfile").mkdtemp(prefix="mesh-left-"), "left.json")
