"""Tests for swarm.inbox.intake_dispatch — wiring layer for CIP-PR5."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable

import pytest

from swarm.inbox.intake_dispatch import (
    DispatchOutcome,
    IntakeBot,
    dispatch_telegram_update,
)
from swarm.intake.margot_router import ProjectSummary, ThreadState


# ============================================================
# Stub Protocols
# ============================================================

class StubLLM:
    def __init__(self, response: dict | None = None):
        self.calls: list[tuple[str, str]] = []
        self._payload = json.dumps(response or {
            "has_project_name": False, "project_name": None,
            "has_idea": False, "idea": None,
            "is_rename_signal": False, "proposed_new_name": None,
        })

    def complete(self, *, system: str, user: str,
                 max_tokens: int = 800, temperature: float = 0.2) -> str:
        self.calls.append((system, user))
        return self._payload


class StubThreadStore:
    def __init__(self, initial: ThreadState | None = None):
        self.initial = initial
        self.upserts: list[ThreadState] = []
        self._next_thread_id = "t-1"

    def get_thread_for_chat(self, *, bot_id, chat_id):
        return self.initial

    def upsert_thread(self, *, bot_id, chat_id, thread):
        # Simulate DB-side id assignment
        if thread.thread_id is None:
            thread = replace(thread, thread_id=self._next_thread_id)
        self.upserts.append(thread)
        return thread


class StubProjectStore:
    def __init__(self, existing: list[ProjectSummary] | None = None):
        self.existing = list(existing or [])
        self.created: list[dict] = []
        self.renamed: list[dict] = []
        self._next_id = 99

    def list_open_projects(self, *, workspace_slug):
        return list(self.existing)

    def create_project(self, *, workspace_slug, name, slug,
                       owner_partner_id, first_idea):
        self._next_id += 1
        proj_id = f"p-{self._next_id}"
        rec = {
            "project_id": proj_id,
            "workspace_slug": workspace_slug,
            "name": name,
            "slug": slug,
            "owner_partner_id": owner_partner_id,
            "first_idea": first_idea,
        }
        self.created.append(rec)
        return ProjectSummary(
            project_id=proj_id, name=name, slug=slug,
            owner_partner_id=owner_partner_id, status="open",
        )

    def rename_project(self, *, project_id, new_name, new_slug):
        self.renamed.append({
            "project_id": project_id,
            "new_name": new_name,
            "new_slug": new_slug,
        })


class StubPersister:
    def __init__(self):
        self.inbounds: list[dict] = []
        self.outbounds: list[dict] = []

    def record_inbound(self, **kwargs):
        self.inbounds.append(kwargs)

    def record_outbound(self, **kwargs):
        self.outbounds.append(kwargs)


class StubReply:
    def __init__(self):
        self.sent: list[dict] = []

    def send_reply(self, *, bot_id, chat_id, text):
        self.sent.append({"bot_id": bot_id, "chat_id": chat_id, "text": text})


class StubForwarder:
    def __init__(self):
        self.forwards: list[dict] = []

    def forward(self, *, thread_id, project_id, bot_id, body):
        self.forwards.append({
            "thread_id": thread_id, "project_id": project_id,
            "bot_id": bot_id, "body": body,
        })


# ============================================================
# Fixtures
# ============================================================

def _bot(authorized=("100",), partner_id="phill") -> IntakeBot:
    return IntakeBot(
        bot_id="b-1",
        kind="client_intake",
        partner_id=partner_id,
        workspace_slug="unite-group",
        authorized_chat_ids=tuple(authorized),
        bot_username="@PhillIntakeBot",
    )


def _update(*, chat_id="100", text="Synthex Brand Refresh",
            update_id=1, message_id=42, from_id=12345) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "chat": {"id": chat_id},
            "from": {"id": from_id},
            "text": text,
        },
    }


def _deps(*,
          initial_thread: ThreadState | None = None,
          existing_projects: list[ProjectSummary] | None = None,
          llm_response: dict | None = None):
    return dict(
        llm=StubLLM(llm_response),
        threads=StubThreadStore(initial_thread),
        projects=StubProjectStore(existing_projects),
        persister=StubPersister(),
        reply=StubReply(),
        spm_forwarder=StubForwarder(),
    )


# ============================================================
# G3 anti-spoofing → rejection
# ============================================================

class TestG3Rejection:
    def test_unauthorized_chat_is_rejected(self):
        deps = _deps()
        update = _update(chat_id="999")  # not in authorized list
        outcome = dispatch_telegram_update(update, _bot(), **deps)
        assert outcome.handled is False
        assert "authoriz" in (outcome.rejected_reason or "").lower()
        # No side effects
        assert deps["persister"].inbounds == []
        assert deps["reply"].sent == []
        assert deps["spm_forwarder"].forwards == []
        assert deps["threads"].upserts == []

    def test_partner_telegram_user_id_mismatch_is_rejected(self):
        deps = _deps()
        update = _update(from_id=99999)  # not the partner's user id
        outcome = dispatch_telegram_update(
            update, _bot(), partner_telegram_user_id=12345, **deps,
        )
        assert outcome.handled is False
        assert deps["persister"].inbounds == []


# ============================================================
# Malformed update
# ============================================================

class TestMalformed:
    def test_no_message_returns_unhandled(self):
        deps = _deps()
        outcome = dispatch_telegram_update({"update_id": 1}, _bot(), **deps)
        assert outcome.handled is False
        assert outcome.rejected_reason == "malformed_update"


# ============================================================
# First-message happy path
# ============================================================

class TestFirstMessage:
    def test_creates_thread_and_advances_to_awaiting_idea(self):
        deps = _deps()
        outcome = dispatch_telegram_update(_update(), _bot(), **deps)
        assert outcome.handled is True
        assert outcome.partner_id == "phill"
        assert outcome.decision.action == "advance_to_idea"
        # Inbound recorded
        assert len(deps["persister"].inbounds) == 1
        inbound = deps["persister"].inbounds[0]
        assert inbound["submitted_by_partner_id"] == "phill"
        assert inbound["body"] == "Synthex Brand Refresh"
        # Reply sent + recorded
        assert len(deps["reply"].sent) == 1
        assert deps["reply"].sent[0]["chat_id"] == "100"
        assert len(deps["persister"].outbounds) == 1
        # Thread upserted with candidate name
        assert len(deps["threads"].upserts) == 1
        thread = deps["threads"].upserts[0]
        assert thread.margot_state == "awaiting_idea"
        assert thread.candidate_name == "Synthex Brand Refresh"
        # No project created yet, no forward yet
        assert deps["projects"].created == []
        assert deps["spm_forwarder"].forwards == []

    def test_both_name_and_idea_creates_project_and_forwards(self):
        deps = _deps(llm_response={
            "has_project_name": True,
            "project_name": "Synthex Brand Refresh",
            "has_idea": True,
            "idea": "Refresh the brand for spring",
            "is_rename_signal": False,
            "proposed_new_name": None,
        })
        outcome = dispatch_telegram_update(
            _update(text="Let's do Synthex Brand Refresh — refresh the brand for spring"),
            _bot(), **deps,
        )
        assert outcome.handled is True
        assert outcome.decision.action == "create_project"
        # Project created with the trusted partner as owner
        assert len(deps["projects"].created) == 1
        created = deps["projects"].created[0]
        assert created["name"] == "Synthex Brand Refresh"
        assert created["owner_partner_id"] == "phill"
        assert created["first_idea"] == "Refresh the brand for spring"
        # Thread is in_loop with the new project id
        thread = deps["threads"].upserts[0]
        assert thread.margot_state == "in_loop"
        assert thread.project_id is not None
        # Forward fired with the project id
        assert len(deps["spm_forwarder"].forwards) == 1
        fwd = deps["spm_forwarder"].forwards[0]
        assert fwd["project_id"] == created["project_id"]


# ============================================================
# Awaiting-idea second message
# ============================================================

class TestAwaitingIdea:
    def test_second_message_supplies_idea_creates_project(self):
        prior = ThreadState(
            thread_id="t-1", project_id=None,
            margot_state="awaiting_idea",
            candidate_name="Synthex Brand Refresh",
            candidate_slug="synthex-brand-refresh",
        )
        deps = _deps(initial_thread=prior)
        outcome = dispatch_telegram_update(
            _update(text="It's a full brand refresh for spring."),
            _bot(), **deps,
        )
        assert outcome.handled is True
        assert outcome.decision.action == "create_project"
        assert len(deps["projects"].created) == 1
        # Forward used the SECOND message body as the first idea
        assert deps["spm_forwarder"].forwards[0]["body"].startswith("It's")


# ============================================================
# in_loop forward
# ============================================================

class TestInLoopForward:
    def test_in_loop_message_forwards_to_spm(self):
        prior = ThreadState(
            thread_id="t-1", project_id="p-100",
            margot_state="in_loop",
            project_name="Synthex Brand Refresh",
            project_owner_partner_id="phill",
        )
        deps = _deps(initial_thread=prior)
        outcome = dispatch_telegram_update(
            _update(text="One more thought on colour."),
            _bot(), **deps,
        )
        assert outcome.handled is True
        assert outcome.decision.action == "forward_to_spm"
        # Silent — no reply sent
        assert deps["reply"].sent == []
        # Forward fired
        assert len(deps["spm_forwarder"].forwards) == 1
        assert deps["spm_forwarder"].forwards[0]["thread_id"] == "t-1"
        assert deps["spm_forwarder"].forwards[0]["project_id"] == "p-100"


# ============================================================
# Rename slash command
# ============================================================

class TestRename:
    def test_slash_rename_calls_project_store(self):
        prior = ThreadState(
            thread_id="t-1", project_id="p-100",
            margot_state="in_loop",
            project_name="Old Name",
            project_owner_partner_id="phill",
        )
        deps = _deps(initial_thread=prior)
        outcome = dispatch_telegram_update(
            _update(text="/rename Synthex v2"), _bot(), **deps,
        )
        assert outcome.handled is True
        assert outcome.decision.action == "rename_project"
        assert deps["projects"].renamed == [{
            "project_id": "p-100",
            "new_name": "Synthex v2",
            "new_slug": "synthex-v2",
        }]
        # Confirmation reply sent
        assert any("Synthex v2" in s["text"] for s in deps["reply"].sent)


# ============================================================
# Duplicate surfacing
# ============================================================

class TestDuplicate:
    def test_duplicate_project_surfaces_match_no_creation(self):
        existing = [
            ProjectSummary(
                project_id="p-1", name="Synthex Brand Refresh",
                slug="synthex-brand-refresh",
                owner_partner_id="phill", status="open",
            ),
        ]
        deps = _deps(existing_projects=existing)
        outcome = dispatch_telegram_update(_update(), _bot(), **deps)
        assert outcome.decision.action == "surface_duplicate"
        # No new project
        assert deps["projects"].created == []
        # Reply mentions the existing project
        assert any(
            "Synthex Brand Refresh" in s["text"] for s in deps["reply"].sent
        )


# ============================================================
# Vague-name rejection
# ============================================================

class TestVague:
    def test_vague_first_message_rejects_no_thread_advancement(self):
        deps = _deps()
        outcome = dispatch_telegram_update(
            _update(text="the thing"), _bot(), **deps,
        )
        assert outcome.decision.action == "reject"
        # Thread stays in awaiting_project_name
        assert deps["threads"].upserts[0].margot_state == "awaiting_project_name"
        # No project, no forward
        assert deps["projects"].created == []
        assert deps["spm_forwarder"].forwards == []
        # But the rejection reply WAS sent
        assert len(deps["reply"].sent) == 1


# ============================================================
# Bot kind check is the caller's responsibility (intake_router.tick),
# but we still want to confirm the dispatcher works fine for both kinds
# of bots — its behavior doesn't branch on `kind`.
# ============================================================

def test_dispatcher_does_not_depend_on_bot_kind():
    bot_context = IntakeBot(
        bot_id="b-2", kind="context", partner_id="phill",
        workspace_slug="unite-group",
        authorized_chat_ids=("100",),
        bot_username="@PhillContextBot",
    )
    deps = _deps()
    outcome = dispatch_telegram_update(_update(), bot_context, **deps)
    # Still handled — the routing decision in intake_router.tick is what
    # gates this; the dispatcher itself is kind-agnostic.
    assert outcome.handled is True
