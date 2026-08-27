"""Pydantic request models for the Pi CEO API (RA-937)."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    # RA-1021: hard cap at 10 via Field constraint; validator enforces the same
    # server-side so even clients that bypass OpenAPI validation are rejected.
    n_workers: int = Field(default=2, ge=1, le=10)

    @field_validator("n_workers")
    @classmethod
    def valid_workers(cls, v: int) -> int:
        # Clamp defensively in case the Field constraint is bypassed.
        return min(max(v, 1), 10)


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


class GoalProjectCreate(BaseModel):
    """Operator-created project brief used to ground Goal tickets."""

    title: str
    description: str
    audience: str
    problem: str = ""
    users: str = ""
    outcomes: str = ""
    constraints: str = ""
    out_of_scope: str = ""

    @field_validator("title", "description", "audience")
    @classmethod
    def strip_required_brief(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("field cannot be empty")
        return v


class GoalTicketRequest(BaseModel):
    """Goal → Linear: required fields only. No autonomy markers."""

    goal: str
    acceptance: str
    project_id: str

    @field_validator("goal", "acceptance", "project_id")
    @classmethod
    def strip_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("field cannot be empty")
        return v


class GoalDraft(BaseModel):
    """One proposed ticket. Filed only after explicit approval."""

    model_config = ConfigDict(extra="allow")

    title: str
    goal: str
    acceptance: str
    rationale: str = ""
    context: str = ""
    user_story: str = ""
    current_behaviour: str = ""
    expected_behaviour: str = ""
    technical_requirements: str = ""
    edge_cases: str = ""
    testing: str = ""
    dependencies: str = ""
    ticket_id: str = ""
    priority: str = ""
    summary: str = ""
    scope: str = ""
    user_flow: str = ""
    technical_flow: str = ""
    examples: str = ""
    implementation_notes: str = ""
    risks: str = ""
    review: str = ""
    ui_ux: str = ""
    data_state: str = ""
    affected_surfaces: str = ""
    tasks: str = ""
    sub_tasks: str = ""
    sub_tasks_json: str = ""
    scenarios: str = ""
    junior_notes: str = ""

    @field_validator("title", "goal", "acceptance")
    @classmethod
    def strip_draft(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("field cannot be empty")
        return v


class GoalTicketFileRequest(GoalTicketRequest):
    """Linear write. `approved` must be true; tickets are the reviewed drafts."""

    approved: bool
    tickets: list[GoalDraft]


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


class MachineSpecProposalBody(BaseModel):
    """Seven-field machine spec proposal schema (spec pipeline pre-flight)."""

    problem_statement: str = Field(..., min_length=20)
    evidence_refs: str = Field(..., min_length=10)
    design_decisions: str = Field(..., min_length=10)
    data_flows: str = Field(..., min_length=10)
    ux_behaviour: str = Field(..., min_length=10)
    acceptance_criteria: str = Field(..., min_length=10)
    implementation_scope: str = Field(..., min_length=10)

    @field_validator(
        "problem_statement",
        "evidence_refs",
        "design_decisions",
        "data_flows",
        "ux_behaviour",
        "acceptance_criteria",
        "implementation_scope",
    )
    @classmethod
    def strip_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("field cannot be empty")
        return v
