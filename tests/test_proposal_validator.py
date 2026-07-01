"""Tests for spec pipeline proposal pre-flight validation."""
from __future__ import annotations

import pytest

from app.server.models import MachineSpecProposalBody
from app.server.spec_pipeline.proposal_validator import (
    ProposalValidationError,
    enrich_proposal_for_judge,
    format_structured_for_judge,
    try_parse_structured_proposal,
    validate_proposal_text,
)

VALID_PROPOSAL = (
    "Add a pre-flight proposal validator to reject template tokens before the judge runs. "
    "Scope: spec_pipeline only."
)


def test_rejects_bare_str_token():
    with pytest.raises(ProposalValidationError, match="bare type token"):
        validate_proposal_text("str")


def test_rejects_angle_bracket_placeholder():
    with pytest.raises(ProposalValidationError, match="placeholder"):
        validate_proposal_text("Build feature <full updated proposal text> now please")


def test_rejects_template_fragment():
    with pytest.raises(ProposalValidationError, match="placeholder|template fragment"):
        validate_proposal_text("Use <bool> for proceed flag in liaison JSON output")


def test_accepts_real_proposal():
    assert validate_proposal_text(VALID_PROPOSAL) == VALID_PROPOSAL


def test_structured_proposal_parses_sections():
    text = (
        "## Problem\nUsers see silent failures when liaison emits template tokens.\n\n"
        "## Evidence\nSee spec-445f2cb2e8c3 judge artifact.\n\n"
        "## Design\nAdd validate_proposal_text before judge.\n\n"
        "## Data flows\nproposal → validator → judge.\n\n"
        "## UX\nBlocked pipeline shows validation reason in handoff.\n\n"
        "## Acceptance\nReject bare str token with ValueError.\n\n"
        "## Scope\n~100 lines across validator + tests.\n"
    )
    body = try_parse_structured_proposal(text)
    assert body is not None
    assert "silent failures" in body.problem_statement


def test_enrich_adds_structured_block():
    text = (
        "## Problem\nUsers see silent failures when liaison emits template tokens.\n\n"
        "## Evidence\nSee spec-445f2cb2e8c3 judge artifact.\n\n"
        "## Design\nAdd validate_proposal_text before judge.\n\n"
        "## Data flows\nproposal → validator → judge.\n\n"
        "## UX\nBlocked pipeline shows validation reason in handoff.\n\n"
        "## Acceptance\nReject bare str token with ValueError.\n\n"
        "## Scope\n~100 lines across validator + tests.\n"
    )
    enriched = enrich_proposal_for_judge(text)
    assert "Structured sections" in enriched
    assert "Problem:" in enriched


def test_machine_spec_proposal_body_requires_nonempty_fields():
    with pytest.raises(ValueError):
        MachineSpecProposalBody(
            problem_statement="short",
            evidence_refs="refs",
            design_decisions="design",
            data_flows="flows",
            ux_behaviour="ux",
            acceptance_criteria="ac",
            implementation_scope="scope",
        )


def test_format_structured_for_judge():
    body = MachineSpecProposalBody(
        problem_statement="A long enough problem statement for validation.",
        evidence_refs="artifact spec-445",
        design_decisions="validator module",
        data_flows="proposal in → validator → judge out",
        ux_behaviour="show blocked reason",
        acceptance_criteria="reject str",
        implementation_scope="validator + tests",
    )
    rendered = format_structured_for_judge(body)
    assert "validator module" in rendered
