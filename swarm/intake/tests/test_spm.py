"""Unit tests for swarm/intake/spm.py.

Coverage targets:
  - All 4 authority gates (SPEC §G2)
  - Anti-spoofing in all 5 paths (SPEC §G3)
  - Brief + aggregation happy paths with a stubbed LLM
  - JSON-extraction tolerance (LLM chatter around JSON)
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from swarm.intake.spm import (
    AuthorityCheck,
    BoardAggregation,
    LLMClient,
    ProjectContext,
    SPMBrief,
    SWOT,
    ThreadMessage,
    aggregate_board_response,
    build_spm_brief,
    can_approve_production,
    can_change_ownership,
    can_delete_project,
    trusted_partner_id_for_inbound,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def project() -> ProjectContext:
    return ProjectContext(
        project_id="proj_abc",
        workspace_slug="unite-group",
        name="Acme Marketing Platform",
        slug="acme-marketing-platform",
        owner_partner_id="partner_duncan",
        approval_policy="creator_only",
        description="Pitched 2026-05-26",
        status="discovery",
        github_repo="CleanExpo/Acme-Marketing-Platform",
    )


@pytest.fixture
def messages() -> list[ThreadMessage]:
    return [
        ThreadMessage(
            direction="inbound",
            author="partner",
            body="I want to build a marketing platform for Acme.",
            submitted_by_partner_id="partner_duncan",
            created_at="2026-05-26T10:00:00Z",
        ),
        ThreadMessage(
            direction="outbound",
            author="margot",
            body="Got it. Tell me about Acme Marketing Platform.",
            submitted_by_partner_id=None,
            created_at="2026-05-26T10:00:05Z",
        ),
        ThreadMessage(
            direction="inbound",
            author="partner",
            body="Multi-channel posting, draft approvals, analytics.",
            submitted_by_partner_id="partner_duncan",
            created_at="2026-05-26T10:01:00Z",
        ),
    ]


class StubLLM:
    """Test double for LLMClient. Returns a configured response."""

    def __init__(self, response: str):
        self.response = response
        self.calls: list[dict] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 1500, temperature: float = 0.3) -> str:
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens, "temperature": temperature})
        return self.response


# ============================================================
# §G2 — Authority gates
# ============================================================

class TestAuthorityGates:
    def test_creator_can_approve_production_under_creator_only(self, project):
        result = can_approve_production(project, requesting_partner_id="partner_duncan")
        assert result == AuthorityCheck(allowed=True)

    def test_non_creator_cannot_approve_production(self, project):
        result = can_approve_production(project, requesting_partner_id="partner_toby")
        assert result.allowed is False
        assert "Only the project creator" in (result.reason or "")
        assert "partner_duncan" in (result.reason or "")

    def test_unsupported_approval_policy_denies(self, project):
        project = replace(project, approval_policy="all_partners")
        result = can_approve_production(project, requesting_partner_id="partner_duncan")
        assert result.allowed is False
        assert "future PR" in (result.reason or "")

    def test_majority_policy_currently_denies_until_implemented(self, project):
        project = replace(project, approval_policy="majority")
        result = can_approve_production(project, requesting_partner_id="partner_duncan")
        assert result.allowed is False

    def test_can_change_ownership_creator_only(self, project):
        assert can_change_ownership(project, "partner_duncan").allowed is True
        assert can_change_ownership(project, "partner_toby").allowed is False
        assert can_change_ownership(project, "partner_phill").allowed is False

    def test_can_delete_project_creator_only(self, project):
        assert can_delete_project(project, "partner_duncan").allowed is True
        denied = can_delete_project(project, "partner_phill")
        assert denied.allowed is False
        assert "Only the project creator" in (denied.reason or "")


# ============================================================
# §G3 — Anti-spoofing
# ============================================================

class TestTrustedPartnerIdForInbound:
    def test_authorized_chat_id_accepted(self):
        partner_id, reason = trusted_partner_id_for_inbound(
            bot_partner_id="partner_duncan",
            telegram_chat_id="12345",
            authorized_chat_ids=["12345", "67890"],
        )
        assert partner_id == "partner_duncan"
        assert reason is None

    def test_unauthorized_chat_id_rejected(self):
        partner_id, reason = trusted_partner_id_for_inbound(
            bot_partner_id="partner_duncan",
            telegram_chat_id="99999",
            authorized_chat_ids=["12345", "67890"],
        )
        assert partner_id is None
        assert "not in this bot's authorized_chat_ids" in (reason or "")
        assert "SPEC §G3.2" in (reason or "")

    def test_empty_authorized_list_falls_through_to_bot_identity(self):
        """An empty allowlist means 'no restriction' — bot identity is the only trust."""
        partner_id, reason = trusted_partner_id_for_inbound(
            bot_partner_id="partner_duncan",
            telegram_chat_id="anything",
            authorized_chat_ids=[],
        )
        assert partner_id == "partner_duncan"
        assert reason is None

    def test_telegram_user_id_match_accepted(self):
        partner_id, reason = trusted_partner_id_for_inbound(
            bot_partner_id="partner_duncan",
            telegram_chat_id="12345",
            authorized_chat_ids=["12345"],
            telegram_from_user_id=999,
            partner_telegram_user_id=999,
        )
        assert partner_id == "partner_duncan"
        assert reason is None

    def test_telegram_user_id_mismatch_rejected(self):
        partner_id, reason = trusted_partner_id_for_inbound(
            bot_partner_id="partner_duncan",
            telegram_chat_id="12345",
            authorized_chat_ids=["12345"],
            telegram_from_user_id=111,
            partner_telegram_user_id=999,
        )
        assert partner_id is None
        assert "does not match the expected" in (reason or "")
        assert "SPEC §G3.3" in (reason or "")

    def test_missing_optional_user_ids_does_not_block(self):
        """If either telegram_from_user_id or partner_telegram_user_id is None,
        the cross-check is skipped (defense-in-depth is optional)."""
        partner_id, reason = trusted_partner_id_for_inbound(
            bot_partner_id="partner_duncan",
            telegram_chat_id="12345",
            authorized_chat_ids=["12345"],
            telegram_from_user_id=999,
            partner_telegram_user_id=None,
        )
        assert partner_id == "partner_duncan"

    def test_chat_id_string_vs_int_normalized(self):
        """Telegram IDs sometimes arrive as int, list might be str. Should match."""
        partner_id, _ = trusted_partner_id_for_inbound(
            bot_partner_id="partner_duncan",
            telegram_chat_id="12345",
            authorized_chat_ids=[12345, 67890],  # ints
        )
        assert partner_id == "partner_duncan"


# ============================================================
# Brief generation
# ============================================================

class TestBuildSpmBrief:
    def test_happy_path(self, project, messages):
        llm = StubLLM(json.dumps({
            "layout": "A multi-tenant Next.js platform with brand-isolated workspaces.",
            "framework": "Synthex feature module + Supabase RLS per brand.",
            "suitability": "Fits the existing Unite-Group portfolio cleanly.",
            "swot": {
                "strengths": ["Existing infra", "Clear scope"],
                "weaknesses": ["Auth complexity"],
                "opportunities": ["Cross-sell to other clients"],
                "threats": ["Competitor X"],
            },
            "open_questions": ["What's the launch deadline?"],
            "ready_for_production": False,
            "rationale": "Scope is clear but deadline + success metric still missing.",
        }))

        brief = build_spm_brief(project, messages, llm=llm)

        assert isinstance(brief, SPMBrief)
        assert brief.layout.startswith("A multi-tenant")
        assert brief.framework.startswith("Synthex")
        assert brief.swot.strengths == ["Existing infra", "Clear scope"]
        assert brief.open_questions == ["What's the launch deadline?"]
        assert brief.ready_for_production is False
        assert "deadline" in brief.rationale

        # The LLM was called once with the right shape
        assert len(llm.calls) == 1
        call = llm.calls[0]
        assert "Senior Project Manager" in call["system"]
        assert project.name in call["user"]
        assert "partner_duncan" in call["user"]  # owner shown

    def test_handles_llm_chatter_around_json(self, project, messages):
        llm = StubLLM(
            "Sure! Here you go:\n\n"
            + json.dumps({
                "layout": "x",
                "framework": "y",
                "suitability": "z",
                "swot": {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []},
                "open_questions": [],
                "ready_for_production": True,
                "rationale": "ok",
            })
            + "\n\nLet me know if you'd like a deeper take."
        )
        brief = build_spm_brief(project, messages, llm=llm)
        assert brief.ready_for_production is True

    def test_missing_swot_keys_default_empty(self, project, messages):
        llm = StubLLM(json.dumps({
            "layout": "x", "framework": "y", "suitability": "z",
            "swot": {},  # all keys missing
            "open_questions": [], "ready_for_production": False, "rationale": "ok",
        }))
        brief = build_spm_brief(project, messages, llm=llm)
        assert brief.swot == SWOT()

    def test_bad_llm_output_raises(self, project, messages):
        llm = StubLLM("not json at all, no braces")
        with pytest.raises(ValueError, match="JSON"):
            build_spm_brief(project, messages, llm=llm)

    def test_thread_truncated_to_max_messages(self, project):
        """If we send a long thread, only the last `max_messages` reach the LLM."""
        many = [
            ThreadMessage(
                direction="inbound",
                author="partner",
                body=f"msg {i}",
                submitted_by_partner_id="partner_duncan",
                created_at=f"2026-05-26T{i:02d}:00:00Z",
            )
            for i in range(50)
        ]
        llm = StubLLM(json.dumps({
            "layout": "x", "framework": "y", "suitability": "z",
            "swot": {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []},
            "open_questions": [], "ready_for_production": False, "rationale": "ok",
        }))
        build_spm_brief(project, many, llm=llm, max_messages=5)
        user = llm.calls[0]["user"]
        # First 45 should NOT appear; last 5 should
        assert "msg 0]" not in user
        assert "msg 1]" not in user
        assert "msg 45" in user
        assert "msg 49" in user


# ============================================================
# Aggregation
# ============================================================

class TestAggregateBoardResponse:
    def test_happy_path_awaiting_partner(self, project):
        brief = SPMBrief(
            layout="x", framework="y", suitability="z",
            swot=SWOT(),
            open_questions=["What's the deadline?"],
            ready_for_production=False,
            rationale="ok",
        )
        llm = StubLLM(json.dumps({
            "summary_for_partner": "**Board take:** scope is solid. One open question:\n\n- What's the deadline?",
            "open_questions": ["What's the deadline?"],
            "next_action": "awaiting_partner",
            "metadata": {"board_personas_aligned": 7, "board_personas_dissenting": 2},
        }))

        agg = aggregate_board_response(
            project=project,
            spm_brief=brief,
            board_minutes="...",
            requesting_partner_id="partner_duncan",
            llm=llm,
        )

        assert isinstance(agg, BoardAggregation)
        assert agg.next_action == "awaiting_partner"
        assert "deadline" in agg.summary_for_partner.lower()
        assert agg.metadata["board_personas_aligned"] == 7

        # Requesting partner is in the prompt context
        assert "partner_duncan" in llm.calls[0]["user"]

    def test_next_action_must_be_valid_enum(self, project):
        brief = SPMBrief(
            layout="x", framework="y", suitability="z",
            swot=SWOT(), open_questions=[], ready_for_production=False, rationale="ok",
        )
        llm = StubLLM(json.dumps({
            "summary_for_partner": "ok",
            "open_questions": [],
            "next_action": "ship-it-yolo",  # invalid
            "metadata": {},
        }))
        agg = aggregate_board_response(project, brief, "...", "partner_duncan", llm=llm)
        # Invalid → falls back to awaiting_partner (safe default)
        assert agg.next_action == "awaiting_partner"

    def test_paused_human_review_passes_through(self, project):
        brief = SPMBrief(
            layout="x", framework="y", suitability="z",
            swot=SWOT(), open_questions=[], ready_for_production=False, rationale="ok",
        )
        llm = StubLLM(json.dumps({
            "summary_for_partner": "Legal flag — needs human review.",
            "open_questions": [],
            "next_action": "paused_human_review",
            "metadata": {},
        }))
        agg = aggregate_board_response(project, brief, "...", "partner_duncan", llm=llm)
        assert agg.next_action == "paused_human_review"


# ============================================================
# Protocol check — LLMClient surface
# ============================================================

def test_llmclient_protocol_accepts_stub():
    """Smoke test that StubLLM satisfies the LLMClient Protocol."""
    llm: LLMClient = StubLLM("ok")
    assert llm.complete(system="s", user="u") == "ok"
