"""Tests for swarm.intake.margot_router — G6 non-happy-path coverage."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from swarm.intake.margot_router import (
    ABANDONED_THREAD_DAYS,
    ClassifiedMessage,
    InboundMessage,
    LLMClient,
    ProjectSummary,
    RouterDecision,
    ThreadState,
    _slugify,
    find_duplicate_project,
    is_thread_abandoned,
    is_vague_name,
    parse_slash_command,
    route_inbound,
)


# ============================================================
# Stub LLM — caller controls the JSON it returns
# ============================================================

class StubLLM:
    """Records calls and returns whatever JSON the test sets."""

    def __init__(self, response: dict | str | None = None):
        self.calls: list[tuple[str, str]] = []
        if isinstance(response, dict):
            self._response_text = json.dumps(response)
        elif isinstance(response, str):
            self._response_text = response
        else:
            self._response_text = json.dumps({
                "has_project_name": False,
                "project_name": None,
                "has_idea": False,
                "idea": None,
                "is_rename_signal": False,
                "proposed_new_name": None,
            })

    def complete(self, *, system: str, user: str,
                 max_tokens: int = 800, temperature: float = 0.2) -> str:
        self.calls.append((system, user))
        return self._response_text


def _empty_classification() -> dict:
    return {
        "has_project_name": False, "project_name": None,
        "has_idea": False, "idea": None,
        "is_rename_signal": False, "proposed_new_name": None,
    }


# ============================================================
# is_vague_name
# ============================================================

class TestIsVagueName:
    def test_empty_is_vague(self):
        vague, reason = is_vague_name("")
        assert vague is True
        assert reason  # non-empty partner-facing prompt

    def test_too_short(self):
        vague, _ = is_vague_name("ab")
        assert vague is True

    def test_vague_token_thing(self):
        vague, _ = is_vague_name("the thing")
        assert vague is True

    def test_vague_token_stuff(self):
        vague, _ = is_vague_name("stuff")
        assert vague is True

    def test_too_long(self):
        vague, _ = is_vague_name("x" * 200)
        assert vague is True

    def test_good_name_passes(self):
        vague, reason = is_vague_name("Synthex Brand Refresh")
        assert vague is False
        assert reason is None

    def test_punctuated_vague_phrase_still_caught(self):
        vague, _ = is_vague_name("it!!!")
        assert vague is True


# ============================================================
# find_duplicate_project (G6 fuzzy-match)
# ============================================================

class TestFindDuplicateProject:
    def _existing(self):
        return [
            ProjectSummary("p1", "Synthex Brand Refresh", "synthex-brand-refresh", "phill", "open"),
            ProjectSummary("p2", "Acme Onboarding", "acme-onboarding", "duncan", "open"),
            ProjectSummary("p3", "Old Closed One", "old-closed-one", "toby", "shipped"),
        ]

    def test_exact_slug_match(self):
        dup = find_duplicate_project("Synthex Brand Refresh", self._existing())
        assert dup is not None and dup.project_id == "p1"

    def test_case_insensitive(self):
        dup = find_duplicate_project("synthex brand refresh", self._existing())
        assert dup is not None and dup.project_id == "p1"

    def test_fuzzy_token_overlap(self):
        dup = find_duplicate_project("Synthex Brand", self._existing())
        assert dup is not None and dup.project_id == "p1"

    def test_no_duplicate(self):
        dup = find_duplicate_project("Totally New Initiative", self._existing())
        assert dup is None

    def test_shipped_projects_ignored(self):
        # "Old Closed One" should NOT match because its status is shipped
        dup = find_duplicate_project("Old Closed One", self._existing())
        assert dup is None


# ============================================================
# is_thread_abandoned (G6)
# ============================================================

class TestIsThreadAbandoned:
    def test_recent_thread_not_abandoned(self):
        now = datetime.now(timezone.utc)
        thread = ThreadState(
            thread_id="t1", project_id="p1", margot_state="in_loop",
            project_status="open",
            last_inbound_at=(now - timedelta(days=2)).isoformat(),
        )
        assert is_thread_abandoned(thread, now=now) is False

    def test_old_thread_abandoned(self):
        now = datetime.now(timezone.utc)
        thread = ThreadState(
            thread_id="t1", project_id="p1", margot_state="in_loop",
            project_status="open",
            last_inbound_at=(now - timedelta(days=ABANDONED_THREAD_DAYS + 1)).isoformat(),
        )
        assert is_thread_abandoned(thread, now=now) is True

    def test_shipped_thread_never_abandoned(self):
        now = datetime.now(timezone.utc)
        thread = ThreadState(
            thread_id="t1", project_id="p1", margot_state="in_loop",
            project_status="shipped",
            last_inbound_at=(now - timedelta(days=100)).isoformat(),
        )
        assert is_thread_abandoned(thread, now=now) is False


# ============================================================
# parse_slash_command
# ============================================================

class TestParseSlashCommand:
    def test_no_slash(self):
        assert parse_slash_command("hello") == (None, None)

    def test_start(self):
        assert parse_slash_command("/start") == ("start", None)

    def test_rename_with_arg(self):
        assert parse_slash_command("/rename Synthex v2") == ("rename", "Synthex v2")

    def test_case_insensitive(self):
        assert parse_slash_command("/Rename Foo") == ("rename", "Foo")


# ============================================================
# State machine — happy paths
# ============================================================

class TestStateMachineHappyPath:
    def test_first_message_just_name_advances_to_idea(self):
        llm = StubLLM(_empty_classification())
        thread = ThreadState(
            thread_id=None, project_id=None,
            margot_state="awaiting_project_name",
        )
        msg = InboundMessage(
            chat_id="42", body="Synthex Brand Refresh",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "advance_to_idea"
        assert decision.next_state == "awaiting_idea"
        assert decision.captured_project_name == "Synthex Brand Refresh"
        assert decision.captured_project_slug == "synthex-brand-refresh"

    def test_awaiting_idea_creates_project(self):
        llm = StubLLM(_empty_classification())
        thread = ThreadState(
            thread_id="t1", project_id=None,
            margot_state="awaiting_idea",
            candidate_name="Synthex Brand Refresh",
            candidate_slug="synthex-brand-refresh",
        )
        msg = InboundMessage(
            chat_id="42",
            body="We need to refresh the brand for the spring launch.",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "create_project"
        assert decision.next_state == "in_loop"
        assert decision.metadata["first_idea"].startswith("We need")

    def test_in_loop_forwards_to_spm(self):
        llm = StubLLM(_empty_classification())
        thread = ThreadState(
            thread_id="t1", project_id="p1",
            margot_state="in_loop",
            project_name="Synthex Brand Refresh",
            project_owner_partner_id="phill",
        )
        msg = InboundMessage(
            chat_id="42", body="Here's a thought on the colour palette.",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "forward_to_spm"
        assert decision.next_state == "in_loop"


# ============================================================
# G6 — both name AND idea in one message
# ============================================================

class TestG6BothInOneMessage:
    def test_first_message_with_name_and_idea_skips_to_classified(self):
        llm = StubLLM({
            "has_project_name": True,
            "project_name": "Synthex Brand Refresh",
            "has_idea": True,
            "idea": "Refresh the brand for spring",
            "is_rename_signal": False,
            "proposed_new_name": None,
        })
        thread = ThreadState(
            thread_id=None, project_id=None,
            margot_state="awaiting_project_name",
        )
        msg = InboundMessage(
            chat_id="42",
            body="Let's do Synthex Brand Refresh — refresh the brand for spring.",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "create_project"
        assert decision.next_state == "in_loop"
        assert decision.captured_project_name == "Synthex Brand Refresh"
        assert decision.metadata["first_idea"] == "Refresh the brand for spring"


# ============================================================
# G6 — vague name rejection
# ============================================================

class TestG6VagueName:
    def test_vague_name_rejected_in_awaiting_project_name(self):
        llm = StubLLM(_empty_classification())
        thread = ThreadState(
            thread_id=None, project_id=None,
            margot_state="awaiting_project_name",
        )
        msg = InboundMessage(
            chat_id="42", body="the thing",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "reject"
        assert decision.next_state == "awaiting_project_name"
        assert "name" in decision.reply_text.lower()


# ============================================================
# G6 — duplicate project surfaced
# ============================================================

class TestG6Duplicate:
    def test_duplicate_surfaced_on_first_message(self):
        llm = StubLLM(_empty_classification())
        existing = [
            ProjectSummary("p1", "Synthex Brand Refresh",
                           "synthex-brand-refresh", "phill", "open"),
        ]
        thread = ThreadState(
            thread_id=None, project_id=None,
            margot_state="awaiting_project_name",
        )
        msg = InboundMessage(
            chat_id="42", body="Synthex Brand Refresh",
            submitted_by_partner_id="duncan",
        )
        decision = route_inbound(msg, thread, existing, llm=llm)
        assert decision.action == "surface_duplicate"
        assert decision.duplicate_match is not None
        assert decision.duplicate_match.project_id == "p1"


# ============================================================
# G6 — abandoned thread → pause_for_review
# ============================================================

class TestG6AbandonedThread:
    def test_old_thread_paused_for_review(self):
        llm = StubLLM(_empty_classification())
        now = datetime(2026, 5, 26, tzinfo=timezone.utc)
        thread = ThreadState(
            thread_id="t1", project_id="p1",
            margot_state="in_loop",
            project_name="Old Project",
            project_owner_partner_id="phill",
            project_status="open",
            last_inbound_at="2026-04-01T00:00:00+00:00",  # >30 days
        )
        msg = InboundMessage(
            chat_id="42", body="hey, are we still doing this?",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm, now=now)
        assert decision.action == "pause_for_review"
        assert decision.next_state == "paused_human_review"

    def test_paused_thread_replies_to_resume(self):
        llm = StubLLM(_empty_classification())
        thread = ThreadState(
            thread_id="t1", project_id="p1",
            margot_state="paused_human_review",
            project_owner_partner_id="phill",
        )
        msg = InboundMessage(
            chat_id="42", body="anything new?",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "reply"
        assert "resume" in decision.reply_text.lower()


# ============================================================
# G6 — /rename slash command + natural-language rename
# ============================================================

class TestG6Rename:
    def test_slash_rename_updates_project(self):
        llm = StubLLM(_empty_classification())
        thread = ThreadState(
            thread_id="t1", project_id="p1",
            margot_state="in_loop",
            project_name="Old Name",
            project_owner_partner_id="phill",
        )
        msg = InboundMessage(
            chat_id="42", body="/rename Synthex v2",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "rename_project"
        assert decision.rename_to == "Synthex v2"
        assert decision.captured_project_slug == "synthex-v2"

    def test_slash_rename_without_arg_prompts(self):
        llm = StubLLM(_empty_classification())
        thread = ThreadState(
            thread_id="t1", project_id="p1",
            margot_state="in_loop",
            project_owner_partner_id="phill",
        )
        msg = InboundMessage(
            chat_id="42", body="/rename",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "reply"
        assert "/rename" in decision.reply_text

    def test_slash_rename_vague_rejected(self):
        llm = StubLLM(_empty_classification())
        thread = ThreadState(
            thread_id="t1", project_id="p1",
            margot_state="in_loop",
            project_owner_partner_id="phill",
        )
        msg = InboundMessage(
            chat_id="42", body="/rename the thing",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "reject"

    def test_slash_rename_duplicate_surfaced(self):
        llm = StubLLM(_empty_classification())
        existing = [
            ProjectSummary("p2", "Acme Onboarding", "acme-onboarding", "duncan", "open"),
        ]
        thread = ThreadState(
            thread_id="t1", project_id="p1",
            margot_state="in_loop",
            project_owner_partner_id="phill",
        )
        msg = InboundMessage(
            chat_id="42", body="/rename Acme Onboarding",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, existing, llm=llm)
        assert decision.action == "surface_duplicate"

    def test_natural_language_rename_in_loop(self):
        llm = StubLLM({
            "has_project_name": False, "project_name": None,
            "has_idea": False, "idea": None,
            "is_rename_signal": True, "proposed_new_name": "Synthex v2",
        })
        thread = ThreadState(
            thread_id="t1", project_id="p1",
            margot_state="in_loop",
            project_name="Old Name",
            project_owner_partner_id="phill",
        )
        msg = InboundMessage(
            chat_id="42", body="actually let's call it Synthex v2",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "rename_project"
        assert decision.rename_to == "Synthex v2"


# ============================================================
# G6 — /start mid-flow asks for continuation confirmation
# ============================================================

class TestG6StartMidFlow:
    def test_start_when_fresh_starts_normally(self):
        llm = StubLLM()
        thread = ThreadState(
            thread_id=None, project_id=None,
            margot_state="awaiting_project_name",
        )
        msg = InboundMessage(
            chat_id="42", body="/start",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "reply"
        assert decision.next_state == "awaiting_project_name"

    def test_start_mid_flow_confirms_continuation(self):
        llm = StubLLM()
        thread = ThreadState(
            thread_id="t1", project_id="p1",
            margot_state="in_loop",
            project_name="Synthex Brand Refresh",
            project_owner_partner_id="phill",
        )
        msg = InboundMessage(
            chat_id="42", body="/start",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "confirm_resume"
        assert "Synthex Brand Refresh" in decision.reply_text


# ============================================================
# G6 — cross-partner takeover is allowed (G2 workspace access)
# ============================================================

class TestG6CrossPartnerTakeover:
    def test_other_partner_can_post_to_thread(self):
        """G2: workspace-scoped RLS means any partner can post.
        Authority (approve / delete / etc.) is checked in spm.py, not here."""
        llm = StubLLM(_empty_classification())
        thread = ThreadState(
            thread_id="t1", project_id="p1",
            margot_state="in_loop",
            project_name="Duncan's Project",
            project_owner_partner_id="duncan",  # owned by Duncan
        )
        msg = InboundMessage(
            chat_id="42",
            body="Quick thought on the architecture",
            submitted_by_partner_id="toby",  # but Toby is replying
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        # Forwarded to SPM normally — attribution is preserved via
        # the message's submitted_by_partner_id, not blocked here.
        assert decision.action == "forward_to_spm"
        assert decision.next_state == "in_loop"


# ============================================================
# Edge cases
# ============================================================

class TestEdgeCases:
    def test_empty_body_in_awaiting_project_name_prompts(self):
        llm = StubLLM()
        thread = ThreadState(
            thread_id=None, project_id=None,
            margot_state="awaiting_project_name",
        )
        msg = InboundMessage(
            chat_id="42", body="",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "reply"
        assert decision.next_state == "awaiting_project_name"

    def test_bad_llm_json_falls_back_to_empty_extraction(self):
        """LLM returns garbage → classifier treats it as 'no extraction',
        and the raw body is validated as a name."""
        llm = StubLLM("totally not json")
        thread = ThreadState(
            thread_id=None, project_id=None,
            margot_state="awaiting_project_name",
        )
        msg = InboundMessage(
            chat_id="42", body="Synthex Brand Refresh",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        # Falls through to "treat body as name", advances to awaiting_idea
        assert decision.action == "advance_to_idea"

    def test_resume_when_not_paused_is_noop_reply(self):
        llm = StubLLM()
        thread = ThreadState(
            thread_id="t1", project_id="p1",
            margot_state="in_loop",
        )
        msg = InboundMessage(
            chat_id="42", body="/resume",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "reply"
        assert "isn't paused" in decision.reply_text

    def test_resume_when_paused_unpauses(self):
        llm = StubLLM()
        thread = ThreadState(
            thread_id="t1", project_id="p1",
            margot_state="paused_human_review",
        )
        msg = InboundMessage(
            chat_id="42", body="/resume",
            submitted_by_partner_id="phill",
        )
        decision = route_inbound(msg, thread, [], llm=llm)
        assert decision.action == "reply"
        assert decision.next_state == "in_loop"


def test_slugify():
    assert _slugify("Synthex Brand Refresh") == "synthex-brand-refresh"
    assert _slugify("  Foo!! Bar??  ") == "foo-bar"
    assert _slugify("---") == ""


def test_llmclient_protocol_accepts_stub():
    llm: LLMClient = StubLLM()
    assert isinstance(llm.complete(system="x", user="y"), str)
