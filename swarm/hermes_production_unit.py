"""Margot-led production packets for child Hermes agents.

RA-5042 turns a broad founder directive into a concrete handoff artifact:
two child agents get clear Linear scope, claim rules, evidence contracts,
and escalation paths while Margot remains the named production lead.

The module is intentionally pure. It does not call Linear, Hermes, GitHub, or
production services; callers feed it issue dictionaries and decide where to
publish the resulting packet.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Iterable, Literal


Lane = Literal["delivery", "verification"]


@dataclass(frozen=True)
class ProductionIssue:
    identifier: str
    title: str
    priority: int
    project: str
    url: str = ""
    state: str = "Todo"
    description: str = ""

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "ProductionIssue":
        priority = raw.get("priority", 3)
        if isinstance(priority, dict):
            priority = priority.get("value", 3)
        return cls(
            identifier=str(raw.get("identifier") or raw.get("id") or ""),
            title=str(raw.get("title") or ""),
            priority=int(priority or 3),
            project=str(raw.get("project") or raw.get("project_name") or ""),
            url=str(raw.get("url") or ""),
            state=str(raw.get("state") or raw.get("status") or "Todo"),
            description=str(raw.get("description") or ""),
        )


@dataclass(frozen=True)
class ChildAgentPacket:
    agent_id: str
    lane: Lane
    mission: str
    assigned_issues: list[ProductionIssue]
    allowed_actions: list[str]
    evidence_required: list[str]
    stop_conditions: list[str]
    escalation_path: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["assigned_issues"] = [asdict(issue) for issue in self.assigned_issues]
        return data


@dataclass(frozen=True)
class ProductionUnitPacket:
    unit_id: str
    generated_at: str
    lead: str
    objective: str
    shared_context: list[str]
    claim_contract: list[str]
    merge_contract: list[str]
    children: list[ChildAgentPacket] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["children"] = [child.to_dict() for child in self.children]
        return data


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "production-unit"


def _issue_sort_key(issue: ProductionIssue) -> tuple[int, str, str]:
    return (issue.priority, issue.project.lower(), issue.identifier)


def split_issues(issues: Iterable[ProductionIssue]) -> tuple[list[ProductionIssue], list[ProductionIssue]]:
    """Split work into delivery and verification lanes.

    Delivery gets implementation/build/fix tickets. Verification gets audit,
    test, smoke, cleanup, status, and evidence tickets. Ambiguous work goes to
    verification so the loop scopes it before anyone builds.
    """
    delivery: list[ProductionIssue] = []
    verification: list[ProductionIssue] = []
    delivery_words = re.compile(r"\b(build|implement|fix|wire|route|create|add|ship)\b", re.I)
    verification_words = re.compile(
        r"\b(audit|verify|test|smoke|status|report|cleanup|clean up|evidence|security|billing|secret)\b",
        re.I,
    )

    for issue in sorted(issues, key=_issue_sort_key):
        text = f"{issue.title}\n{issue.description}"
        if verification_words.search(text) and not delivery_words.search(text):
            verification.append(issue)
        elif delivery_words.search(text):
            delivery.append(issue)
        else:
            verification.append(issue)

    return delivery, verification


def build_packet(
    raw_issues: Iterable[dict[str, Any] | ProductionIssue],
    *,
    unit_id: str = "margot-hermes-linear-production-unit",
    now: datetime | None = None,
) -> ProductionUnitPacket:
    """Build a Margot-led two-agent packet from candidate Linear issues."""
    generated_at = (now or datetime.now(timezone.utc)).isoformat()
    issues = [
        item if isinstance(item, ProductionIssue) else ProductionIssue.from_mapping(item)
        for item in raw_issues
    ]
    issues = [issue for issue in issues if issue.identifier and issue.title]
    delivery, verification = split_issues(issues)

    shared_context = [
        "Margot is production lead; child agents do not invent strategy or change priorities.",
        "Linear is the shared queue; Hermes Kanban mirrors visibility but is not the authority.",
        "Every issue must move by evidence: branch, PR, test output, smoke result, or explicit blocker.",
        "Human approval remains required for production deploys, billing, secrets, destructive data actions, and merges to main.",
    ]
    claim_contract = [
        "Claim exactly one issue before work starts by moving it to In Progress or adding a visible claim comment.",
        "Skip issues already claimed by another agent or human.",
        "Work in an isolated branch/worktree; never push directly to main.",
        "If the same blocker repeats three times, stop that issue, comment the blocker, and pick the next safe issue.",
    ]
    merge_contract = [
        "Open a PR with verification evidence attached.",
        "Do not mark Linear Done until the PR is merged and main CI/smoke is green.",
        "If verification fails, update Linear with the concrete failing command and leave the issue In Progress or Blocked.",
    ]

    children = [
        ChildAgentPacket(
            agent_id="hermes-child-delivery-1",
            lane="delivery",
            mission="Build or repair the next narrow, agent-ready Linear item and open a PR with evidence.",
            assigned_issues=delivery[:5],
            allowed_actions=[
                "read repository files",
                "create feature branch/worktree",
                "edit safe-scope source/tests/docs",
                "run focused tests and project gates",
                "push branch and open PR",
                "comment progress/evidence in Linear",
            ],
            evidence_required=[
                "changed files summary",
                "commands run with pass/fail result",
                "PR URL",
                "main SHA after merge when complete",
            ],
            stop_conditions=[
                "protected file required",
                "secret/account/billing action required",
                "destructive migration or production data action required",
                "same failure repeats three times",
            ],
            escalation_path=["Margot", "Senior PM", "Phill"],
        ),
        ChildAgentPacket(
            agent_id="hermes-child-verification-1",
            lane="verification",
            mission="Truth-check active Linear work, close stale tickets with evidence, and create exact follow-up blockers.",
            assigned_issues=verification[:5],
            allowed_actions=[
                "inspect code and CI state",
                "run read-only audits and focused tests",
                "update Linear descriptions/comments/status with evidence",
                "open blocker tickets for concrete gaps",
                "prepare PRs only for test/docs/safe-scope fixes",
            ],
            evidence_required=[
                "file paths or live run URLs checked",
                "pass/fail/unknown classification",
                "status transition rationale",
                "next concrete gap per unresolved issue",
            ],
            stop_conditions=[
                "issue requires human credential rotation",
                "evidence is inconclusive after two independent checks",
                "state change would hide a real unresolved production risk",
            ],
            escalation_path=["Margot", "Board", "Phill"],
        ),
    ]

    return ProductionUnitPacket(
        unit_id=_slug(unit_id),
        generated_at=generated_at,
        lead="Margot",
        objective=(
            "Keep Pi-Dev-Ops Linear work moving continuously through a two-child "
            "Hermes production unit while preserving evidence gates and human approval."
        ),
        shared_context=shared_context,
        claim_contract=claim_contract,
        merge_contract=merge_contract,
        children=children,
    )


def render_markdown(packet: ProductionUnitPacket) -> str:
    """Render a packet as a human/Hermes-readable Markdown handoff."""
    lines = [
        f"# {packet.lead}-Led Hermes Linear Production Unit",
        "",
        f"Unit: `{packet.unit_id}`",
        f"Generated: `{packet.generated_at}`",
        "",
        "## Objective",
        packet.objective,
        "",
        "## Shared Context",
    ]
    lines.extend(f"- {item}" for item in packet.shared_context)
    lines.extend(["", "## Claim Contract"])
    lines.extend(f"- {item}" for item in packet.claim_contract)
    lines.extend(["", "## Merge Contract"])
    lines.extend(f"- {item}" for item in packet.merge_contract)

    for child in packet.children:
        lines.extend([
            "",
            f"## {child.agent_id}",
            f"Lane: `{child.lane}`",
            "",
            child.mission,
            "",
            "### Assigned Linear Issues",
        ])
        if child.assigned_issues:
            for issue in child.assigned_issues:
                link = f" [{issue.url}]" if issue.url else ""
                lines.append(
                    f"- `{issue.identifier}` P{issue.priority} {issue.project}: {issue.title}{link}"
                )
        else:
            lines.append("- No current issue assigned; ask Margot/Senior PM for the next candidate.")
        lines.extend(["", "### Allowed Actions"])
        lines.extend(f"- {item}" for item in child.allowed_actions)
        lines.extend(["", "### Evidence Required"])
        lines.extend(f"- {item}" for item in child.evidence_required)
        lines.extend(["", "### Stop Conditions"])
        lines.extend(f"- {item}" for item in child.stop_conditions)
        lines.extend(["", "### Escalation Path"])
        lines.append(" -> ".join(child.escalation_path))

    lines.extend([
        "",
        "## Machine JSON",
        "```json",
        json.dumps(packet.to_dict(), indent=2, sort_keys=True),
        "```",
        "",
    ])
    return "\n".join(lines)


def write_packet(packet: ProductionUnitPacket, output_dir: Path) -> tuple[Path, Path]:
    """Write Markdown and JSON packet artifacts. Returns (md_path, json_path)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{packet.unit_id}.md"
    json_path = output_dir / f"{packet.unit_id}.json"
    md_path.write_text(render_markdown(packet), encoding="utf-8")
    json_path.write_text(json.dumps(packet.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return md_path, json_path


__all__ = [
    "ChildAgentPacket",
    "ProductionIssue",
    "ProductionUnitPacket",
    "build_packet",
    "render_markdown",
    "split_issues",
    "write_packet",
]
