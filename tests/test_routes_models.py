"""
test_routes_models.py — Unit tests for Pydantic request models (RA-937).

All models live in app/server/models.py after the main.py decomposition.
Tests cover field validation, defaults, and validator rejection.
"""
import pytest
from pydantic import ValidationError

from app.server.models import (
    BuildRequest,
    ParallelBuildRequest,
    TriggerRequest,
    LessonRequest,
    ScanRequest,
    MonitorRequest,
    SpecRequest,
    PlanRequest,
    TestRequest as PipelineTestRequest,
    ShipRequest,
)


# ── BuildRequest ──────────────────────────────────────────────────────────────

def test_build_request_valid_https():
    r = BuildRequest(repo_url="https://github.com/org/repo")
    assert r.repo_url == "https://github.com/org/repo"
    assert r.model == "sonnet"


def test_build_request_valid_git_ssh():
    r = BuildRequest(repo_url="git@github.com:org/repo.git")
    assert r.repo_url == "git@github.com:org/repo.git"


def test_build_request_strips_whitespace():
    r = BuildRequest(repo_url="  https://github.com/org/repo  ")
    assert r.repo_url == "https://github.com/org/repo"


def test_build_request_invalid_url():
    with pytest.raises(ValidationError, match="repo_url must start with"):
        BuildRequest(repo_url="http://github.com/org/repo")


def test_build_request_invalid_model():
    with pytest.raises(ValidationError, match="model must be opus"):
        BuildRequest(repo_url="https://github.com/org/repo", model="gpt-4")


def test_build_request_valid_models():
    for m in ("opus", "sonnet", "haiku"):
        r = BuildRequest(repo_url="https://github.com/x/y", model=m)
        assert r.model == m


def test_build_request_defaults():
    r = BuildRequest(repo_url="https://github.com/x/y")
    assert r.brief == ""
    assert r.intent == ""
    assert r.evaluator_enabled is None
    assert r.budget_minutes is None
    assert r.scope is None
    assert r.plan_discovery is False
    assert r.complexity_tier == ""


# ── ParallelBuildRequest ──────────────────────────────────────────────────────

def test_parallel_build_default_workers():
    r = ParallelBuildRequest(repo_url="https://github.com/x/y")
    assert r.n_workers == 2


def test_parallel_build_valid_workers():
    r = ParallelBuildRequest(repo_url="https://github.com/x/y", n_workers=8)
    assert r.n_workers == 8


def test_parallel_build_zero_workers():
    # RA-1021: 0 is below the ge=1 Field constraint.
    with pytest.raises(ValidationError):
        ParallelBuildRequest(repo_url="https://github.com/x/y", n_workers=0)


def test_parallel_build_nine_workers():
    # RA-1021: cap raised from 8 to 10 — 9 is now valid.
    r = ParallelBuildRequest(repo_url="https://github.com/x/y", n_workers=9)
    assert r.n_workers == 9


def test_parallel_build_eleven_workers():
    # RA-1021: 11 exceeds the le=10 Field constraint.
    with pytest.raises(ValidationError):
        ParallelBuildRequest(repo_url="https://github.com/x/y", n_workers=11)


# ── TriggerRequest ────────────────────────────────────────────────────────────

def test_trigger_request_valid():
    r = TriggerRequest(repo_url="https://github.com/x/y", minute=30)
    assert r.minute == 30
    assert r.hour is None


def test_trigger_request_with_hour():
    r = TriggerRequest(repo_url="https://github.com/x/y", minute=0, hour=9)
    assert r.hour == 9


def test_trigger_request_invalid_minute():
    with pytest.raises(ValidationError, match="minute must be 0-59"):
        TriggerRequest(repo_url="https://github.com/x/y", minute=60)


def test_trigger_request_invalid_hour():
    with pytest.raises(ValidationError, match="hour must be 0-23"):
        TriggerRequest(repo_url="https://github.com/x/y", minute=0, hour=24)


def test_trigger_request_hour_zero_valid():
    r = TriggerRequest(repo_url="https://github.com/x/y", minute=0, hour=0)
    assert r.hour == 0


# ── LessonRequest ─────────────────────────────────────────────────────────────

def test_lesson_request_valid():
    r = LessonRequest(lesson="Always use atomic writes for JSON persistence.")
    assert r.source == "manual"
    assert r.category == "general"
    assert r.severity == "info"


def test_lesson_request_strips_whitespace():
    r = LessonRequest(lesson="  trim me  ")
    assert r.lesson == "trim me"


def test_lesson_request_empty_rejected():
    with pytest.raises(ValidationError, match="lesson cannot be empty"):
        LessonRequest(lesson="   ")


# ── ScanRequest ───────────────────────────────────────────────────────────────

def test_scan_request_defaults():
    r = ScanRequest()
    assert r.project_id is None
    assert r.scan_types is None
    assert r.dry_run is False
    assert r.auto_pr is False


def test_scan_request_valid_types():
    r = ScanRequest(scan_types=["security", "code_quality"])
    assert len(r.scan_types) == 2


def test_scan_request_invalid_type():
    with pytest.raises(ValidationError):
        ScanRequest(scan_types=["invalid_type"])


# ── MonitorRequest / SpecRequest / PlanRequest / TestRequest / ShipRequest ────

def test_monitor_request_defaults():
    r = MonitorRequest()
    assert r.project_id is None
    assert r.use_agent is False
    assert r.dry_run is False


def test_spec_request_valid():
    r = SpecRequest(idea="Build a rate limiter", repo_url="https://github.com/x/y")
    assert r.model == "sonnet"
    assert r.pipeline_id is None


def test_plan_request_valid():
    r = PlanRequest(pipeline_id="abc123")
    assert r.model == "sonnet"


def test_pipeline_test_request_valid():
    r = PipelineTestRequest(pipeline_id="abc123", session_id="sess-456")
    assert r.pipeline_id == "abc123"
    assert r.session_id == "sess-456"


def test_ship_request_valid():
    r = ShipRequest(pipeline_id="abc123")
    assert r.pipeline_id == "abc123"
