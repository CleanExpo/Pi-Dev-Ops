"""Pre-flight proposal validation for the machine spec pipeline."""
from __future__ import annotations

import re

from app.server.models import MachineSpecProposalBody

log_name = __name__

# Bare Python type tokens emitted when LLM JSON templates are not substituted.
BARE_TYPE_TOKENS = frozenset({
    "str", "int", "bool", "float", "dict", "list", "tuple", "set",
    "none", "any", "object",
})

# Known template fragments from liaison/judge prompts.
TEMPLATE_FRAGMENTS = (
    "<full updated proposal text>",
    "<bool>",
    "<description>",
    "<int>",
    "<str>",
)

_PLACEHOLDER_RE = re.compile(r"<[A-Za-z][\w\s\-]*>")
_SECTION_HEADINGS = (
    ("problem", "problem_statement"),
    ("evidence", "evidence_refs"),
    ("design", "design_decisions"),
    ("data flow", "data_flows"),
    ("ux", "ux_behaviour"),
    ("acceptance", "acceptance_criteria"),
    ("scope", "implementation_scope"),
    ("implementation", "implementation_scope"),
)


class ProposalValidationError(ValueError):
    """Raised when proposal text is a template token or otherwise unusable."""


def validate_proposal_text(text: str) -> str:
    """
    Reject template garbage before the prebuild judge runs.

    Returns stripped proposal text on success.
    """
    proposal = (text or "").strip()
    lowered = proposal.lower()

    if lowered in BARE_TYPE_TOKENS:
        raise ProposalValidationError(f"proposal is bare type token: {proposal!r}")

    if _PLACEHOLDER_RE.search(proposal):
        raise ProposalValidationError("proposal contains angle-bracket placeholder")

    for frag in TEMPLATE_FRAGMENTS:
        if frag.lower() in lowered:
            raise ProposalValidationError(f"proposal contains template fragment: {frag!r}")

    if len(proposal) < 10:
        raise ProposalValidationError("proposal too short (minimum 10 characters)")

    return proposal


def _extract_section(text: str, keywords: tuple[str, ...]) -> str:
    """Pull content after a markdown heading that matches any keyword."""
    lines = text.splitlines()
    capture: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip().lower()
            in_section = any(kw in heading for kw in keywords)
            if in_section:
                capture = []
            continue
        if in_section:
            if stripped.startswith("#") and capture:
                break
            capture.append(line)
    return "\n".join(capture).strip()


def try_parse_structured_proposal(text: str) -> MachineSpecProposalBody | None:
    """Parse markdown-section proposal into the seven-field schema if possible."""
    proposal = validate_proposal_text(text)
    fields: dict[str, str] = {}
    for keywords, field_name in _SECTION_HEADINGS:
        if field_name in fields and fields[field_name]:
            continue
        chunk = _extract_section(proposal, (keywords,))
        if chunk:
            fields[field_name] = chunk

    if len(fields) < 4:
        return None

    try:
        return MachineSpecProposalBody(**fields)
    except ValueError:
        return None


def format_structured_for_judge(body: MachineSpecProposalBody) -> str:
    """Render structured fields for judge prompt enrichment."""
    parts = [
        f"Problem: {body.problem_statement}",
        f"Evidence refs: {body.evidence_refs}",
        f"Design decisions: {body.design_decisions}",
        f"Data flows: {body.data_flows}",
        f"UX behaviour: {body.ux_behaviour}",
        f"Acceptance criteria: {body.acceptance_criteria}",
        f"Implementation scope: {body.implementation_scope}",
    ]
    return "\n\n".join(parts)


def enrich_proposal_for_judge(text: str) -> str:
    """Validate free-form or structured proposal; return text for judge scoring."""
    proposal = validate_proposal_text(text)
    structured = try_parse_structured_proposal(proposal)
    if structured is None:
        return proposal
    return (
        f"{proposal}\n\n--- Structured sections (for scoring) ---\n"
        f"{format_structured_for_judge(structured)}"
    )
