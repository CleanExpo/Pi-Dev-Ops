"""Production handoff — pure-logic orchestration with injected clients.

Once an intake project is `ready_for_production` AND the creator has
explicitly approved the ship (G2), `execute_handoff` runs five steps
in order, recording sub-status to the caller after each one:

    1. branch_repo        → create `feat/<project-slug>` on project repo
    2. open_pr            → open PR INTO project repo (`main`)
    3. create_linear      → write a Linear issue in the workspace project
    4. notify_partners    → broadcast "shipped" to all 3 partner bots
    5. mark_shipped       → set intake_projects.status='shipped'

Idempotency: each step is wrapped so re-running a handoff that
already advanced past step N skips steps ≤ N. The caller passes in
the current `HandoffState` (typically loaded from
`intake_production_handoffs`); we return an updated `HandoffState`.

Authority enforcement (SPEC §G2): `execute_handoff` REFUSES to run
unless the calling partner is the project creator (per
`approval_policy='creator_only'`). The check happens before any
side effects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Iterable, Literal, Protocol

from swarm.github_tools import GhRepo, GitHubClient, PullRequestResult

HandoffStatus = Literal[
    "pending",
    "repo_branched",
    "pr_opened",
    "linear_created",
    "notified",
    "complete",
    "failed",
]


# ============================================================
# Data shapes
# ============================================================

@dataclass(frozen=True)
class ProjectForHandoff:
    """Subset of intake_projects needed to ship."""
    project_id: str
    workspace_slug: str
    name: str
    slug: str
    owner_partner_id: str  # G2 — creator-only authority
    approval_policy: Literal["creator_only", "majority", "custom"]
    github_repo: str  # 'owner/name' — set at project creation
    status: str = "ready_for_production"
    description: str | None = None


@dataclass(frozen=True)
class SpmAssessmentForHandoff:
    """Final SPM brief that justified the ship."""
    summary: str
    open_questions: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(frozen=True)
class PartnerBot:
    """One row from intake_client_bots — the broadcast targets."""
    partner_id: str
    chat_id: str  # Telegram chat id to notify
    display_name: str


@dataclass(frozen=True)
class HandoffState:
    """Persistent state per intake_production_handoffs row."""
    handoff_id: str | None = None
    status: HandoffStatus = "pending"
    branch_name: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    linear_issue_id: str | None = None
    linear_issue_url: str | None = None
    notified_partner_ids: tuple[str, ...] = ()
    error_message: str | None = None


@dataclass(frozen=True)
class HandoffRequest:
    """The "ship it" command, already authority-checked at the caller."""
    project: ProjectForHandoff
    requesting_partner_id: str
    spm_assessment: SpmAssessmentForHandoff


@dataclass(frozen=True)
class AuthorityCheck:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class LinearIssuePayload:
    """What goes to the Linear API. The PR5 wiring layer turns this
    into a save_issue GraphQL call via swarm/linear_tools.py."""
    team_id: str
    project_id: str | None
    title: str
    description: str
    label_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CreatedLinearIssue:
    id: str
    url: str


@dataclass(frozen=True)
class NotificationPayload:
    chat_id: str
    text: str


# ============================================================
# Protocols
# ============================================================

class LinearClient(Protocol):
    def save_issue(self, payload: LinearIssuePayload) -> CreatedLinearIssue: ...


class TelegramBroadcaster(Protocol):
    """Sends a Telegram message via the partner's bot.

    Implementations in PR5 look up the bot token by
    `intake_client_bots.bot_token_env_name` keyed on partner_id.
    """
    def send(self, *, partner_id: str, payload: NotificationPayload) -> None: ...


# ============================================================
# Pure helpers
# ============================================================

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    s = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return re.sub(r"-+", "-", s)


def branch_name_for(project: ProjectForHandoff) -> str:
    return f"feat/{slugify(project.slug or project.name)}"


def pr_title_for(project: ProjectForHandoff) -> str:
    return f"feat: ship intake project — {project.name}"


def pr_body_for(
    project: ProjectForHandoff,
    spm: SpmAssessmentForHandoff,
    *,
    requesting_partner_id: str,
) -> str:
    """Markdown PR body. Conforms to skill conventions:
    metadata block at the bottom for autonomous-agent traceability."""
    parts: list[str] = [
        "## Summary",
        "",
        f"Project '{project.name}' has been approved for production by its creator "
        f"({project.owner_partner_id}). Opening this PR to seed the implementation work.",
        "",
        "## SPM final read",
        "",
        spm.summary or "_no summary recorded_",
        "",
    ]
    if spm.open_questions:
        parts.extend([
            "### Open questions carried into implementation",
            "",
        ])
        parts.extend(f"- {q}" for q in spm.open_questions)
        parts.append("")
    if spm.rationale:
        parts.extend([
            "### Rationale",
            "",
            spm.rationale,
            "",
        ])
    parts.extend([
        "---",
        "",
        f"Agent ID: pi-ceo-intake-pipeline",
        f"Task ID: handoff/{project.project_id}",
        f"Verifier ID: swarm.intake.handoff.execute_handoff",
        f"Agentic Layer: swarm/intake (handoff)",
        f"Approved by: {requesting_partner_id} (project creator)",
        "",
        "🤖 Generated by the CIP handoff layer",
    ])
    return "\n".join(parts)


def linear_payload_for(
    project: ProjectForHandoff,
    spm: SpmAssessmentForHandoff,
    *,
    team_id: str,
    project_linear_id: str | None,
    label_ids: tuple[str, ...] = (),
) -> LinearIssuePayload:
    description_parts: list[str] = [
        f"Production handoff for intake project '{project.name}'.",
        "",
    ]
    if project.description:
        description_parts.extend([project.description, ""])
    if spm.summary:
        description_parts.extend(["## SPM summary", "", spm.summary, ""])
    if spm.open_questions:
        description_parts.append("## Open questions")
        description_parts.append("")
        description_parts.extend(f"- {q}" for q in spm.open_questions)
        description_parts.append("")
    return LinearIssuePayload(
        team_id=team_id,
        project_id=project_linear_id,
        title=f"Ship intake project — {project.name}",
        description="\n".join(description_parts),
        label_ids=label_ids,
    )


def broadcast_payloads(
    project: ProjectForHandoff,
    bots: Iterable[PartnerBot],
    *,
    pr_url: str,
    linear_url: str,
) -> list[tuple[str, NotificationPayload]]:
    """Return (partner_id, payload) tuples to send via the broadcaster."""
    out: list[tuple[str, NotificationPayload]] = []
    for bot in bots:
        text = (
            f"Project '{project.name}' is shipped.\n"
            f"PR: {pr_url}\n"
            f"Linear: {linear_url}"
        )
        out.append((bot.partner_id, NotificationPayload(chat_id=bot.chat_id, text=text)))
    return out


# ============================================================
# G2 — Authority gate
# ============================================================

def check_handoff_authority(
    project: ProjectForHandoff,
    requesting_partner_id: str,
) -> AuthorityCheck:
    """G2: project creator only, regardless of shared workspace RLS.

    `majority` and `custom` policies are NOT implemented yet — they
    explicitly deny. NEVER silently fall back to creator-only.
    """
    if project.approval_policy == "creator_only":
        if requesting_partner_id == project.owner_partner_id:
            return AuthorityCheck(True, "creator approved")
        return AuthorityCheck(
            False,
            f"creator-only — only {project.owner_partner_id} can ship this project",
        )
    if project.approval_policy in ("majority", "custom"):
        return AuthorityCheck(
            False,
            f"approval_policy={project.approval_policy} not implemented yet; "
            "denying ship to avoid silent fallback",
        )
    return AuthorityCheck(False, f"unknown approval_policy: {project.approval_policy}")


# ============================================================
# Step orchestration
# ============================================================

@dataclass(frozen=True)
class HandoffPlan:
    """What execute_handoff is about to do — used by tests and dry-run."""
    branch_name: str
    pr_title: str
    pr_body: str
    linear_payload: LinearIssuePayload
    broadcasts: tuple[tuple[str, NotificationPayload], ...]


def plan_handoff(
    request: HandoffRequest,
    bots: Iterable[PartnerBot],
    *,
    linear_team_id: str,
    linear_project_id: str | None,
    label_ids: tuple[str, ...] = (),
    placeholder_links: bool = True,
) -> HandoffPlan:
    """Compute everything we WILL send without doing any I/O.

    If `placeholder_links=True`, the broadcast payloads contain
    `(pending)` for the PR / Linear URL because we haven't created
    them yet. `execute_handoff` re-runs `broadcast_payloads` after
    the real URLs land. Pure planning is useful for tests + dry-run.
    """
    branch = branch_name_for(request.project)
    title = pr_title_for(request.project)
    body = pr_body_for(
        request.project,
        request.spm_assessment,
        requesting_partner_id=request.requesting_partner_id,
    )
    linear = linear_payload_for(
        request.project, request.spm_assessment,
        team_id=linear_team_id,
        project_linear_id=linear_project_id,
        label_ids=label_ids,
    )
    pr_url = "(pending)" if placeholder_links else ""
    linear_url = "(pending)" if placeholder_links else ""
    broadcasts = tuple(
        broadcast_payloads(request.project, bots, pr_url=pr_url, linear_url=linear_url)
    )
    return HandoffPlan(
        branch_name=branch,
        pr_title=title,
        pr_body=body,
        linear_payload=linear,
        broadcasts=broadcasts,
    )


def execute_handoff(
    request: HandoffRequest,
    state: HandoffState,
    bots: Iterable[PartnerBot],
    *,
    gh: GitHubClient,
    linear: LinearClient,
    broadcaster: TelegramBroadcaster,
    linear_team_id: str,
    linear_project_id: str | None,
    label_ids: tuple[str, ...] = (),
    base_branch: str = "main",
) -> HandoffState:
    """Run the 5-step handoff, idempotently resuming from `state.status`.

    Returns an updated `HandoffState`. Any exception is caught,
    recorded into `state.error_message`, and surfaced via
    `status='failed'` so the caller can persist + retry.
    """
    # G2 authority check FIRST — refuse even to plan if not creator
    auth = check_handoff_authority(request.project, request.requesting_partner_id)
    if not auth.allowed:
        return replace(
            state,
            status="failed",
            error_message=f"authority check failed: {auth.reason}",
        )

    bots_tuple = tuple(bots)
    repo = GhRepo.parse(request.project.github_repo)
    branch = state.branch_name or branch_name_for(request.project)
    title = pr_title_for(request.project)
    body = pr_body_for(
        request.project,
        request.spm_assessment,
        requesting_partner_id=request.requesting_partner_id,
    )
    payload = linear_payload_for(
        request.project, request.spm_assessment,
        team_id=linear_team_id,
        project_linear_id=linear_project_id,
        label_ids=label_ids,
    )

    try:
        # ── Step 1: branch ─────────────────────────────────────────
        if state.status == "pending":
            gh.create_branch(repo=repo, base=base_branch, new_branch=branch)
            state = replace(state, status="repo_branched", branch_name=branch)

        # ── Step 2: open PR ────────────────────────────────────────
        if state.status == "repo_branched":
            pr = gh.open_pr(
                repo=repo, head=branch, base=base_branch,
                title=title, body=body,
            )
            state = replace(state, status="pr_opened",
                            pr_url=pr.url, pr_number=pr.number)

        # ── Step 3: Linear issue ───────────────────────────────────
        if state.status == "pr_opened":
            issue = linear.save_issue(payload)
            state = replace(state, status="linear_created",
                            linear_issue_id=issue.id, linear_issue_url=issue.url)

        # ── Step 4: notify partners ────────────────────────────────
        if state.status == "linear_created":
            assert state.pr_url and state.linear_issue_url, "step ordering bug"
            already = set(state.notified_partner_ids)
            broadcasts = broadcast_payloads(
                request.project, bots_tuple,
                pr_url=state.pr_url, linear_url=state.linear_issue_url,
            )
            sent: list[str] = list(state.notified_partner_ids)
            for partner_id, npayload in broadcasts:
                if partner_id in already:
                    continue
                broadcaster.send(partner_id=partner_id, payload=npayload)
                sent.append(partner_id)
            state = replace(state, status="notified",
                            notified_partner_ids=tuple(sent))

        # ── Step 5: complete ───────────────────────────────────────
        if state.status == "notified":
            state = replace(state, status="complete")

    except Exception as exc:  # noqa: BLE001 — record everything for the caller
        state = replace(state, status="failed", error_message=str(exc))

    return state
