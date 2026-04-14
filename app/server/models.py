"""Pydantic request models for the Pi CEO API (RA-937)."""
from typing import Literal
from pydantic import BaseModel, field_validator


class BuildRequest(BaseModel):
    repo_url: str
    brief: str = ""
    model: str = "sonnet"
    evaluator_enabled: bool | None = None
    intent: str = ""
    budget_minutes: int | None = None   # RA-677: AUTONOMY_BUDGET single-knob override
    scope: dict | None = None           # RA-676: session scope contract
    plan_discovery: bool = False        # RA-679: run plan variation discovery before generate
    complexity_tier: str = ""           # RA-681: override tier (basic/detailed/advanced)

    @field_validator("repo_url")
    @classmethod
    def valid_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("https://", "git@")):
            raise ValueError("repo_url must start with https:// or git@")
        return v

    @field_validator("model")
    @classmethod
    def valid_model(cls, v: str) -> str:
        if v not in ("opus", "sonnet", "haiku"):
            raise ValueError("model must be opus | sonnet | haiku")
        return v


class ParallelBuildRequest(BuildRequest):
    n_workers: int = 2

    @field_validator("n_workers")
    @classmethod
    def valid_workers(cls, v: int) -> int:
        if not (1 <= v <= 8):
            raise ValueError("n_workers must be 1–8")
        return v


class TriggerRequest(BaseModel):
    repo_url: str
    brief: str = ""
    model: str = "sonnet"
    minute: int
    hour: int | None = None

    @field_validator("repo_url")
    @classmethod
    def valid_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("https://", "git@")):
            raise ValueError("repo_url must start with https:// or git@")
        return v

    @field_validator("model")
    @classmethod
    def valid_model(cls, v: str) -> str:
        if v not in ("opus", "sonnet", "haiku"):
            raise ValueError("model must be opus | sonnet | haiku")
        return v

    @field_validator("minute")
    @classmethod
    def valid_minute(cls, v: int) -> int:
        if not (0 <= v <= 59):
            raise ValueError("minute must be 0-59")
        return v

    @field_validator("hour")
    @classmethod
    def valid_hour(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 23):
            raise ValueError("hour must be 0-23")
        return v


class LessonRequest(BaseModel):
    source: str = "manual"
    category: str = "general"
    lesson: str
    severity: str = "info"

    @field_validator("lesson")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("lesson cannot be empty")
        return v.strip()


class ScanRequest(BaseModel):
    project_id: str | None = None
    scan_types: list[Literal["security", "code_quality", "dependencies", "deployment_health"]] | None = None
    dry_run: bool = False
    auto_pr: bool = False  # RA-537: open GitHub PRs for auto-fixable findings


class MonitorRequest(BaseModel):
    project_id: str | None = None
    use_agent: bool = False
    dry_run: bool = False


class SpecRequest(BaseModel):
    idea: str
    repo_url: str
    pipeline_id: str | None = None
    model: str = "sonnet"


class PlanRequest(BaseModel):
    pipeline_id: str
    model: str = "sonnet"


class TestRequest(BaseModel):
    pipeline_id: str
    session_id: str


class ShipRequest(BaseModel):
    pipeline_id: str
