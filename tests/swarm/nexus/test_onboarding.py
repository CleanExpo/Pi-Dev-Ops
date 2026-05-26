"""Tests for swarm.nexus.onboarding — pure-logic state machine.

35+ tests covering: every transition (happy + denied + error), LLM parse
edge cases, slug validation, approval-gate forcing, irreversibility,
terminal-state guards, transition table consistency.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

import pytest

from swarm.nexus.onboarding import (
    APPROVAL_SLA_HOURS,
    QUALIFY_BUDGET_APPROVAL_THRESHOLD_AUD,
    approve_qualification,
    build_qualification_approval,
    can_transition_to,
    create_workspace,
    enable_loops,
    is_terminal,
    off_board_client,
    pause_workspace,
    qualify_client,
    resume_workspace,
    wire_channels,
)
from swarm.nexus.types import Channel, Client, Loop, Workspace


# ============================================================
# Stub Protocols
# ============================================================

class StubLLM:
    def __init__(self, response: dict | str | None = None):
        self.calls: list[tuple[str, str]] = []
        if isinstance(response, dict):
            self._payload = json.dumps(response)
        elif isinstance(response, str):
            self._payload = response
        else:
            self._payload = json.dumps(_DEFAULT_QUAL)

    def complete(self, *, system, user, max_tokens=1024, temperature=0.3):
        self.calls.append((system, user))
        return self._payload


_DEFAULT_QUAL = {
    "industry": "restoration",
    "scope_summary": "IICRC water damage workflow",
    "estimated_budget_aud": 2000,
    "compliance_flags": [],
    "qualified": True,
    "rationale": "scope is clear and budget within auto-threshold",
    "requires_approval": False,
    "approval_reason": None,
}


class StubWorkspaceStore:
    def __init__(self, *, taken: set[str] | None = None):
        self._taken = set(taken or ())
        self.saved: list[Workspace] = []

    def get(self, workspace_id):
        for w in self.saved:
            if w.id == workspace_id:
                return w
        return None

    def get_by_slug(self, slug):
        for w in self.saved:
            if w.slug == slug:
                return w
        return None

    def save(self, workspace):
        self.saved.append(workspace)
        self._taken.add(workspace.slug)
        return workspace

    def slug_taken(self, slug):
        return slug in self._taken


class StubChannelStore:
    def __init__(self, channels: Iterable[Channel] = ()):
        self._channels = list(channels)

    def list_for_workspace(self, workspace_id):
        return [c for c in self._channels if c.workspace_id == workspace_id]


class StubLoopStore:
    def __init__(self):
        self.saved: list[Loop] = []

    def upsert(self, loop):
        self.saved.append(loop)
        return loop

    def list_for_workspace(self, workspace_id):
        return [l for l in self.saved if l.workspace_id == workspace_id]


# ============================================================
# Fixtures
# ============================================================

def _client(status="intake", client_id="c-1", founder="phill") -> Client:
    return Client(
        id=client_id,
        founder_id=founder,
        legal_name="Acme Restoration Pty Ltd",
        display_name="Acme",
        status=status,
        created_at="2026-05-26T00:00:00Z",
        updated_at="2026-05-26T00:00:00Z",
    )


def _workspace(client_id="c-1", slug="acme-restoration") -> Workspace:
    return Workspace(
        id=f"ws-{client_id}",
        client_id=client_id,
        slug=slug,
        display_name="Acme Restoration",
        linear_team_id="team-abc",
        status="active",
    )


# ============================================================
# qualify_client
# ============================================================

class TestQualifyClient:
    def test_happy_path_qualified_no_approval(self):
        client = _client("intake")
        llm = StubLLM()
        result = qualify_client(client, "Acme wants restoration tooling", llm=llm)
        assert result.result == "ok"
        assert result.new_status == "qualified"
        assert "qualification" in result.audit_payload

    def test_wrong_initial_status_denied(self):
        client = _client("workspace_created")
        result = qualify_client(client, "anything", llm=StubLLM())
        assert result.result == "denied"
        assert "intake" in result.reason

    def test_llm_returns_no_json_raises_error_result(self):
        llm = StubLLM(response="totally not json")
        result = qualify_client(_client(), "foo", llm=llm)
        assert result.result == "error"
        assert "no JSON" in result.reason

    def test_llm_returns_malformed_json(self):
        llm = StubLLM(response="{ this is { not valid }")
        result = qualify_client(_client(), "foo", llm=llm)
        assert result.result == "error"
        assert "parse failed" in result.reason

    def test_llm_chatter_around_json_tolerated(self):
        payload = "Here's the qualification:\n" + json.dumps(_DEFAULT_QUAL) + "\nThanks!"
        llm = StubLLM(response=payload)
        result = qualify_client(_client(), "foo", llm=llm)
        assert result.result == "ok"

    def test_budget_above_threshold_forces_approval(self):
        qual_data = {**_DEFAULT_QUAL, "estimated_budget_aud": 10_000, "requires_approval": False}
        llm = StubLLM(response=qual_data)
        result = qualify_client(_client(), "foo", llm=llm)
        assert result.result == "ok"
        qual = result.audit_payload["qualification"]
        assert qual["requires_approval"] is True
        assert "budget" in qual["approval_reason"].lower()

    def test_compliance_flags_force_approval(self):
        qual_data = {**_DEFAULT_QUAL, "compliance_flags": ["IICRC", "NDIA"], "requires_approval": False}
        llm = StubLLM(response=qual_data)
        result = qualify_client(_client(), "foo", llm=llm)
        qual = result.audit_payload["qualification"]
        assert qual["requires_approval"] is True
        assert "IICRC" in qual["approval_reason"]

    def test_already_required_approval_not_overwritten(self):
        qual_data = {
            **_DEFAULT_QUAL,
            "compliance_flags": ["IICRC"],
            "requires_approval": True,
            "approval_reason": "operator-specified contractual review",
        }
        llm = StubLLM(response=qual_data)
        result = qualify_client(_client(), "foo", llm=llm)
        qual = result.audit_payload["qualification"]
        # original reason preserved (not overwritten by compliance-forcing logic)
        assert qual["approval_reason"] == "operator-specified contractual review"

    def test_llm_called_with_system_and_user_prompts(self):
        llm = StubLLM()
        qualify_client(_client(), "call summary: water damage job", llm=llm)
        assert len(llm.calls) == 1
        system, user = llm.calls[0]
        assert "qualification" in system.lower()
        assert "water damage" in user


# ============================================================
# approve_qualification
# ============================================================

class TestApproveQualification:
    def test_approved_keeps_qualified_status(self):
        client = _client("qualified")
        result = approve_qualification(client, "approved", decided_by="phill")
        assert result.result == "ok"
        assert result.new_status == "qualified"

    def test_denied_parks_back_to_intake(self):
        client = _client("qualified")
        result = approve_qualification(client, "denied", decided_by="phill", note="budget unclear")
        assert result.result == "ok"
        assert result.new_status == "intake"
        assert "budget unclear" in result.reason

    def test_invalid_decision_denied(self):
        client = _client("qualified")
        result = approve_qualification(client, "maybe", decided_by="phill")
        assert result.result == "denied"
        assert "approved" in result.reason

    def test_wrong_initial_status_denied(self):
        client = _client("in_loop")
        result = approve_qualification(client, "approved", decided_by="phill")
        assert result.result == "denied"


# ============================================================
# create_workspace
# ============================================================

class TestCreateWorkspace:
    def test_happy_path(self):
        client = _client("qualified")
        store = StubWorkspaceStore()
        result = create_workspace(
            client, slug="acme-restoration", display_name="Acme",
            linear_team_id="team-1", workspaces=store,
        )
        assert result.result == "ok"
        assert result.new_status == "workspace_created"
        assert len(store.saved) == 1
        assert store.saved[0].slug == "acme-restoration"

    def test_slug_taken_denied(self):
        client = _client("qualified")
        store = StubWorkspaceStore(taken={"acme-restoration"})
        result = create_workspace(
            client, slug="acme-restoration", display_name="Acme",
            linear_team_id="team-1", workspaces=store,
        )
        assert result.result == "denied"
        assert "taken" in result.reason

    @pytest.mark.parametrize("bad_slug,reason_substr", [
        ("", "empty"),
        ("ab", "too short"),
        ("x" * 50, "too long"),
        ("AcmeRestoration", "lowercase"),
        ("acme restoration", "lowercase"),
        ("-acme", "hyphen"),
        ("acme-", "hyphen"),
        ("acme_restoration", "lowercase"),  # underscore not allowed
    ])
    def test_slug_validation_denials(self, bad_slug, reason_substr):
        result = create_workspace(
            _client("qualified"), slug=bad_slug, display_name="X",
            linear_team_id="team-1", workspaces=StubWorkspaceStore(),
        )
        assert result.result == "denied"
        assert reason_substr in result.reason.lower()

    def test_wrong_initial_status_denied(self):
        result = create_workspace(
            _client("intake"), slug="acme", display_name="X",
            linear_team_id="team-1", workspaces=StubWorkspaceStore(),
        )
        assert result.result == "denied"


# ============================================================
# wire_channels
# ============================================================

class TestWireChannels:
    def test_happy_path_with_one_channel(self):
        client = _client("workspace_created")
        ws = _workspace()
        ch = Channel(
            id="ch-1", workspace_id=ws.id, workspace_slug=ws.slug,
            kind="telegram_chat", external_id="12345",
            display_name="Acme team", inbound_route="margot",
        )
        result = wire_channels(client, ws, channels=StubChannelStore([ch]))
        assert result.result == "ok"
        assert result.new_status == "wired"

    def test_no_channels_denied(self):
        result = wire_channels(
            _client("workspace_created"), _workspace(),
            channels=StubChannelStore([]),
        )
        assert result.result == "denied"
        assert "no channels" in result.reason

    def test_wrong_initial_status_denied(self):
        result = wire_channels(
            _client("intake"), _workspace(),
            channels=StubChannelStore([]),
        )
        assert result.result == "denied"


# ============================================================
# enable_loops
# ============================================================

class TestEnableLoops:
    def test_happy_path_multiple_loops(self):
        client = _client("wired")
        ws = _workspace()
        store = StubLoopStore()
        result = enable_loops(
            client, ws,
            loop_specs=[
                ("discovery", "0 */6 * * *", {"persona": "restoreassist"}),
                ("content", "0 9 * * *", {}),
                ("kpi", "0 8 * * 1", {}),
            ],
            loops=store,
        )
        assert result.result == "ok"
        assert result.new_status == "in_loop"
        assert len(store.saved) == 3
        assert {l.loop_kind for l in store.saved} == {"discovery", "content", "kpi"}

    def test_empty_loop_specs_denied(self):
        result = enable_loops(
            _client("wired"), _workspace(),
            loop_specs=[], loops=StubLoopStore(),
        )
        assert result.result == "denied"
        assert "empty" in result.reason

    def test_wrong_initial_status_denied(self):
        result = enable_loops(
            _client("intake"), _workspace(),
            loop_specs=[("discovery", "0 */6 * * *", {})],
            loops=StubLoopStore(),
        )
        assert result.result == "denied"


# ============================================================
# pause / resume
# ============================================================

class TestPauseResume:
    def test_pause_from_in_loop(self):
        result = pause_workspace(_client("in_loop"), _workspace(), reason="ops check")
        assert result.result == "ok"
        assert result.new_status == "paused"

    def test_pause_from_wrong_status_denied(self):
        result = pause_workspace(_client("intake"), _workspace(), reason="x")
        assert result.result == "denied"

    def test_resume_from_paused(self):
        result = resume_workspace(_client("paused"), _workspace())
        assert result.result == "ok"
        assert result.new_status == "in_loop"

    def test_resume_from_wrong_status_denied(self):
        result = resume_workspace(_client("in_loop"), _workspace())
        assert result.result == "denied"


# ============================================================
# off_board_client (irreversible)
# ============================================================

class TestOffBoardClient:
    def test_requires_explicit_ack(self):
        result = off_board_client(
            _client("in_loop"), decided_by="phill", explicit_ack=False,
        )
        assert result.result == "denied"
        assert "explicit_ack" in result.reason

    def test_happy_path_with_ack(self):
        result = off_board_client(
            _client("in_loop"), decided_by="phill", explicit_ack=True,
        )
        assert result.result == "ok"
        assert result.new_status == "off_boarded"
        assert result.audit_payload["irreversible"] is True

    def test_already_off_boarded_denied(self):
        result = off_board_client(
            _client("off_boarded"), decided_by="phill", explicit_ack=True,
        )
        assert result.result == "denied"
        assert "already" in result.reason


# ============================================================
# build_qualification_approval
# ============================================================

class TestBuildQualificationApproval:
    def test_basic_construction(self):
        client = _client()
        qual = type("Q", (), {
            "industry": "restoration",
            "scope_summary": "test",
            "estimated_budget_aud": 2000,
            "compliance_flags": ("IICRC",),
            "qualified": True,
            "rationale": "ok",
            "requires_approval": True,
            "approval_reason": "compliance flags present",
            "__dict__": {
                "industry": "restoration",
                "compliance_flags": ("IICRC",),
                "requires_approval": True,
            },
        })()
        req = build_qualification_approval(client, qual, requested_by="hermes-strategy")
        assert req.action == "qualification:approve"
        assert req.requested_by == "hermes-strategy"
        assert req.status == "pending"

    def test_sla_is_72_hours(self):
        from swarm.nexus.types import Qualification
        client = _client()
        qual = Qualification(
            industry="restoration", scope_summary="x",
            estimated_budget_aud=2000, compliance_flags=(),
            qualified=True, rationale="ok", requires_approval=True,
            approval_reason="test",
        )
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        req = build_qualification_approval(client, qual, requested_by="x", now=now)
        sla = datetime.fromisoformat(req.sla_expires_at)
        delta = sla - now
        assert delta == timedelta(hours=APPROVAL_SLA_HOURS)


# ============================================================
# Transition table consistency
# ============================================================

class TestTransitionTable:
    def test_off_boarded_is_terminal(self):
        assert is_terminal("off_boarded") is True

    def test_in_loop_is_not_terminal(self):
        assert is_terminal("in_loop") is False

    def test_intake_to_qualified_allowed(self):
        assert can_transition_to("intake", "qualified") is True

    def test_intake_cannot_skip_to_in_loop(self):
        assert can_transition_to("intake", "in_loop") is False

    def test_off_boarded_cannot_transition(self):
        for target in ("intake", "qualified", "in_loop", "paused"):
            assert can_transition_to("off_boarded", target) is False

    def test_qualified_can_go_back_to_intake_on_denial(self):
        assert can_transition_to("qualified", "intake") is True

    def test_paused_to_in_loop_allowed(self):
        assert can_transition_to("paused", "in_loop") is True

    def test_in_loop_to_off_boarded_allowed(self):
        assert can_transition_to("in_loop", "off_boarded") is True


# ============================================================
# Constants
# ============================================================

class TestConstants:
    def test_budget_threshold_is_5000(self):
        assert QUALIFY_BUDGET_APPROVAL_THRESHOLD_AUD == 5_000

    def test_sla_is_72_hours(self):
        assert APPROVAL_SLA_HOURS == 72
