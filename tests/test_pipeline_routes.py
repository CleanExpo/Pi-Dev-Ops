"""
test_pipeline_routes.py — FastAPI TestClient integration tests for the Ship Chain
pipeline routes (RA-6503).

Routes under test (app/server/routes/pipeline.py):
  POST /api/spec     — Phase 1: idea → spec.md (async background)
  POST /api/plan     — Phase 2: spec.md → plan.md (async background)
  POST /api/test     — Phase 4: run smoke tests + record results (async background)
  POST /api/ship     — Phase 6: hard gate + ship (synchronous)
  GET  /api/pipeline/{id}  — Fetch full PipelineState
  GET  /api/pipelines      — List all pipeline summaries

Externals mocked:
  - app.server.pipeline.run_spec_phase    (Claude SDK / subprocess)
  - app.server.pipeline.run_plan_phase    (Claude SDK / subprocess)
  - app.server.pipeline.run_test_phase    (subprocess smoke runner)
  - app.server.pipeline.run_ship_phase    (git / Linear API)
  - app.server.pipeline.load_pipeline_state  (filesystem)
  - app.server.pipeline.list_pipelines       (filesystem)

Auth is satisfied by injecting a valid Bearer token created with the real
create_session_token() helper — same approach as conftest.py env setup.

Off-limits per brief: sessions.py, session_linear.py, session_phases.py.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app() -> "FastAPI":  # noqa: F821
    """Import and return the assembled FastAPI app without starting background tasks."""
    from app.server.main import app  # noqa: PLC0415
    return app


def _valid_token() -> str:
    """Return a freshly signed session token accepted by require_auth."""
    from app.server.auth import create_session_token  # noqa: PLC0415
    return create_session_token()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_valid_token()}"}


def _make_pipeline_state(pipeline_id: str = "test-pipe-01", phase: str = "spec") -> "PipelineState":  # noqa: F821
    """Return a minimal PipelineState dataclass instance."""
    from app.server.pipeline import PipelineState  # noqa: PLC0415
    return PipelineState(
        pipeline_id=pipeline_id,
        idea="Build a REST API for inventory management",
        repo_url="https://github.com/example/inventory-api",
        current_phase=phase,
        phases_completed=[],
        spec="## Spec\n\nInventory API spec content.",
        plan=None,
        session_id=None,
        test_results=None,
        review_score=None,
        ship_log=None,
    )


# ---------------------------------------------------------------------------
# /api/spec — Phase 1
# ---------------------------------------------------------------------------

class TestSpecRoute:
    """POST /api/spec tests."""

    def test_spec_happy_path(self):
        """Returns 200 + pipeline_id when auth + body are valid."""
        app = _make_app()
        with patch("app.server.pipeline.run_spec_phase") as mock_spec:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/spec",
                    json={
                        "idea": "Build a REST API for inventory management",
                        "repo_url": "https://github.com/example/inventory-api",
                    },
                    headers=_auth_headers(),
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "pipeline_id" in data
        assert len(data["pipeline_id"]) > 0

    def test_spec_uses_provided_pipeline_id(self):
        """When pipeline_id is supplied it is echoed back unchanged."""
        app = _make_app()
        with patch("app.server.pipeline.run_spec_phase"):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/spec",
                    json={
                        "idea": "Rewrite legacy billing",
                        "repo_url": "https://github.com/example/billing",
                        "pipeline_id": "RA-9999",
                    },
                    headers=_auth_headers(),
                )
        assert resp.status_code == 200
        assert resp.json()["pipeline_id"] == "RA-9999"

    def test_spec_auth_rejected_no_token(self):
        """POST /api/spec without auth returns 401."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/spec",
                json={
                    "idea": "test",
                    "repo_url": "https://github.com/example/repo",
                },
            )
        assert resp.status_code == 401

    def test_spec_auth_rejected_bad_token(self):
        """POST /api/spec with a tampered Bearer token returns 401."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/spec",
                json={"idea": "test", "repo_url": "https://github.com/example/repo"},
                headers={"Authorization": "Bearer not-a-real-token"},
            )
        assert resp.status_code == 401

    def test_spec_background_failure_does_not_bubble_to_caller(self):
        """Even if run_spec_phase raises, the route returns 200 (background task)."""
        app = _make_app()
        with patch("app.server.pipeline.run_spec_phase", side_effect=RuntimeError("SDK unavailable")):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/spec",
                    json={
                        "idea": "Billing rewrite",
                        "repo_url": "https://github.com/example/billing",
                    },
                    headers=_auth_headers(),
                )
        # The error is caught inside _run(); the HTTP layer must still return 200
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# /api/plan — Phase 2
# ---------------------------------------------------------------------------

class TestPlanRoute:
    """POST /api/plan tests."""

    def test_plan_happy_path(self):
        """Returns 200 + pipeline_id for a valid authenticated request."""
        app = _make_app()
        with patch("app.server.pipeline.run_plan_phase"):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/plan",
                    json={"pipeline_id": "pipe-abc123"},
                    headers=_auth_headers(),
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["pipeline_id"] == "pipe-abc123"

    def test_plan_auth_rejected(self):
        """POST /api/plan without auth returns 401."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/plan", json={"pipeline_id": "pipe-abc123"})
        assert resp.status_code == 401

    def test_plan_failure_propagation(self):
        """run_plan_phase failure is swallowed — caller still sees 200."""
        app = _make_app()
        with patch("app.server.pipeline.run_plan_phase", side_effect=ValueError("spec not found")):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/plan",
                    json={"pipeline_id": "pipe-missing"},
                    headers=_auth_headers(),
                )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# /api/test — Phase 4
# ---------------------------------------------------------------------------

class TestTestRoute:
    """POST /api/test tests."""

    def test_test_happy_path(self):
        """Returns 200 + pipeline_id for valid auth + body."""
        app = _make_app()
        with patch("app.server.pipeline.run_test_phase"):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/test",
                    json={"pipeline_id": "pipe-xyz", "session_id": "sess-001"},
                    headers=_auth_headers(),
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["pipeline_id"] == "pipe-xyz"

    def test_test_auth_rejected(self):
        """POST /api/test without auth returns 401."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/test",
                json={"pipeline_id": "pipe-xyz", "session_id": "sess-001"},
            )
        assert resp.status_code == 401

    def test_test_failure_swallowed(self):
        """run_test_phase failure is caught internally — caller sees 200."""
        app = _make_app()
        with patch("app.server.pipeline.run_test_phase", side_effect=OSError("smoke runner not found")):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/test",
                    json={"pipeline_id": "pipe-xyz", "session_id": "sess-fail"},
                    headers=_auth_headers(),
                )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /api/ship — Phase 6 (synchronous)
# ---------------------------------------------------------------------------

class TestShipRoute:
    """POST /api/ship tests — synchronous; errors surface immediately."""

    def test_ship_happy_path(self):
        """Returns 200 with ok=True when pipeline shipped successfully."""
        app = _make_app()
        state = _make_pipeline_state(phase="ship")
        state.ship_log = {"shipped": True, "pr_url": "https://github.com/example/inventory-api/pull/42"}

        with patch("app.server.pipeline.run_ship_phase", return_value=state):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/ship",
                    json={"pipeline_id": "test-pipe-01"},
                    headers=_auth_headers(),
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["pipeline_id"] == "test-pipe-01"
        assert "ship_log" in data

    def test_ship_not_shipped_returns_ok_false(self):
        """When ship_log.shipped is False, ok=False is returned (gate failed)."""
        app = _make_app()
        state = _make_pipeline_state(phase="ship")
        state.ship_log = {"shipped": False, "reason": "review score too low"}

        with patch("app.server.pipeline.run_ship_phase", return_value=state):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/ship",
                    json={"pipeline_id": "test-pipe-01"},
                    headers=_auth_headers(),
                )

        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    def test_ship_auth_rejected(self):
        """POST /api/ship without auth returns 401."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/ship", json={"pipeline_id": "test-pipe-01"})
        assert resp.status_code == 401

    def test_ship_value_error_returns_400(self):
        """run_ship_phase raising ValueError surfaces as HTTP 400 (not 500)."""
        app = _make_app()
        with patch("app.server.pipeline.run_ship_phase", side_effect=ValueError("pipeline not in shippable state")):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/ship",
                    json={"pipeline_id": "bad-pipe"},
                    headers=_auth_headers(),
                )
        assert resp.status_code == 400
        # Must NOT leak internal details (RA-1023)
        detail = resp.json().get("detail", "")
        assert "not in shippable" not in detail
        assert "pipeline" in detail.lower() or "invalid" in detail.lower() or "ship" in detail.lower()

    def test_ship_no_ship_log_returns_ok_false(self):
        """When ship_log is None, ok defaults to False (gate not recorded)."""
        app = _make_app()
        state = _make_pipeline_state(phase="ship")
        state.ship_log = None  # no log recorded

        with patch("app.server.pipeline.run_ship_phase", return_value=state):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/ship",
                    json={"pipeline_id": "test-pipe-01"},
                    headers=_auth_headers(),
                )

        assert resp.status_code == 200
        assert resp.json()["ok"] is False


# ---------------------------------------------------------------------------
# GET /api/pipeline/{pipeline_id}
# ---------------------------------------------------------------------------

class TestGetPipelineRoute:
    """GET /api/pipeline/{id} tests."""

    def test_get_pipeline_happy_path(self):
        """Returns 200 + full state dict for an existing pipeline."""
        app = _make_app()
        state = _make_pipeline_state("pipe-found", phase="plan")

        with patch("app.server.pipeline.load_pipeline_state", return_value=state):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/api/pipeline/pipe-found",
                    headers=_auth_headers(),
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["pipeline_id"] == "pipe-found"
        assert data["current_phase"] == "plan"
        assert "idea" in data

    def test_get_pipeline_not_found_returns_404(self):
        """Returns 404 when load_pipeline_state returns None."""
        app = _make_app()
        with patch("app.server.pipeline.load_pipeline_state", return_value=None):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/api/pipeline/no-such-pipe",
                    headers=_auth_headers(),
                )
        assert resp.status_code == 404

    def test_get_pipeline_auth_rejected(self):
        """GET /api/pipeline/{id} without auth returns 401."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/pipeline/pipe-found")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/pipelines
# ---------------------------------------------------------------------------

class TestListPipelinesRoute:
    """GET /api/pipelines tests."""

    def test_list_pipelines_empty(self):
        """Returns 200 + empty list when no pipelines exist."""
        app = _make_app()
        with patch("app.server.pipeline.list_pipelines", return_value=[]):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/pipelines", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_pipelines_returns_summaries(self):
        """Returns list of pipeline summary dicts."""
        app = _make_app()
        summaries = [
            {
                "pipeline_id": "pipe-001",
                "idea": "Build inventory API",
                "current_phase": "ship",
                "phases_completed": ["spec", "plan"],
                "updated_at": "2026-06-11T00:00:00+00:00",
            },
            {
                "pipeline_id": "pipe-002",
                "idea": "Rebuild auth service",
                "current_phase": "plan",
                "phases_completed": ["spec"],
                "updated_at": "2026-06-11T01:00:00+00:00",
            },
        ]
        with patch("app.server.pipeline.list_pipelines", return_value=summaries):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/pipelines", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["pipeline_id"] == "pipe-001"

    def test_list_pipelines_auth_rejected(self):
        """GET /api/pipelines without auth returns 401."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/pipelines")
        assert resp.status_code == 401
