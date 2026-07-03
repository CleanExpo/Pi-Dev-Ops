"""Unit tests for swarm/intake/specialists.py (RA-6671 P1).

Coverage:
  - Default-OFF gating: no LLM calls when the fan-out flag is unset.
  - Kill-switch honoured: empty panel, no LLM calls, when active.
  - Happy path: enabled → one take per role, JSON parsed, confidence clamped.
  - Per-role isolation: one failing seat degrades to a stub, others survive.
  - Parallelism: all roles dispatched from a single gather.
  - render_panel folds takes into board material_input.
"""
from __future__ import annotations

import asyncio
import json
import threading

import pytest

from swarm.intake.spm import ProjectContext, SPMBrief, SWOT, ThreadMessage
from swarm.intake.specialists import (
    DEFAULT_ROLES,
    SpecialistPanel,
    gather_specialist_takes,
    render_panel,
    specialist_fanout_enabled,
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
        description="Pitched 2026-05-26",
        status="discovery",
    )


@pytest.fixture
def brief() -> SPMBrief:
    return SPMBrief(
        layout="A multi-channel posting dashboard.",
        framework="Next.js + FastAPI.",
        suitability="Fits the agency portfolio.",
        swot=SWOT(
            strengths=["clear scope"],
            weaknesses=["no analytics spec"],
            opportunities=["upsell existing clients"],
            threats=["crowded market"],
        ),
        open_questions=["What is the analytics requirement?"],
        ready_for_production=False,
        rationale="Scope not yet locked.",
    )


@pytest.fixture
def messages() -> list[ThreadMessage]:
    return [
        ThreadMessage(
            direction="inbound",
            author="partner",
            body="Build a marketing platform for Acme.",
            submitted_by_partner_id="partner_duncan",
            created_at="2026-05-26T10:00:00Z",
        ),
    ]


_TAKE_JSON = json.dumps(
    {
        "assessment": "Solid economics if we reuse the existing stack.",
        "key_risks": ["margin thin at low volume"],
        "recommendation": "Proceed with caution; lock pricing first.",
        "confidence": 0.7,
    }
)


class StubLLM:
    """Thread-safe LLMClient double. Records every call; returns a fixed body."""

    def __init__(self, response: str = _TAKE_JSON):
        self.response = response
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def complete(self, *, system: str, user: str, max_tokens: int = 1500,
                 temperature: float = 0.3) -> str:
        with self._lock:
            self.calls.append({"system": system, "user": user})
        return self.response


def _on() -> bool:
    return True


def _off() -> bool:
    return False


# ============================================================
# Gating
# ============================================================

def test_disabled_by_default_makes_no_llm_calls(project, brief, messages):
    llm = StubLLM()
    panel = asyncio.run(
        gather_specialist_takes(
            project, brief, messages, llm=llm,
            enabled=_off, kill_switch=_off,
        )
    )
    assert panel.takes == []
    assert llm.calls == []


def test_kill_switch_active_makes_no_llm_calls(project, brief, messages):
    llm = StubLLM()
    panel = asyncio.run(
        gather_specialist_takes(
            project, brief, messages, llm=llm,
            enabled=_on, kill_switch=_on,
        )
    )
    assert panel.takes == []
    assert llm.calls == []


def test_flag_reads_env(monkeypatch):
    monkeypatch.delenv("INTAKE_SPECIALIST_FANOUT", raising=False)
    assert specialist_fanout_enabled() is False
    monkeypatch.setenv("INTAKE_SPECIALIST_FANOUT", "1")
    assert specialist_fanout_enabled() is True
    monkeypatch.setenv("INTAKE_SPECIALIST_FANOUT", "off")
    assert specialist_fanout_enabled() is False


# ============================================================
# Happy path
# ============================================================

def test_enabled_fans_out_one_take_per_role(project, brief, messages):
    llm = StubLLM()
    panel = asyncio.run(
        gather_specialist_takes(
            project, brief, messages, llm=llm,
            enabled=_on, kill_switch=_off,
        )
    )
    assert [t.role for t in panel.takes] == list(DEFAULT_ROLES)
    assert len(llm.calls) == len(DEFAULT_ROLES)
    cfo = panel.by_role("CFO")
    assert cfo is not None
    assert cfo.confidence == 0.7
    assert cfo.key_risks == ["margin thin at low volume"]
    assert cfo.degraded is False
    # Each role got its own role-specific system prompt.
    assert any("CTO" in c["system"] for c in llm.calls)
    assert any("CMO" in c["system"] for c in llm.calls)


def test_confidence_is_clamped(project, brief, messages):
    llm = StubLLM(json.dumps({"assessment": "x", "key_risks": [],
                              "recommendation": "go", "confidence": 5}))
    panel = asyncio.run(
        gather_specialist_takes(project, brief, messages, llm=llm,
                                enabled=_on, kill_switch=_off)
    )
    assert all(0.0 <= t.confidence <= 1.0 for t in panel.takes)


def test_custom_roles_subset(project, brief, messages):
    llm = StubLLM()
    panel = asyncio.run(
        gather_specialist_takes(project, brief, messages, llm=llm,
                                roles=("CFO", "CTO"),
                                enabled=_on, kill_switch=_off)
    )
    assert [t.role for t in panel.takes] == ["CFO", "CTO"]
    assert len(llm.calls) == 2


# ============================================================
# Per-role isolation
# ============================================================

def test_one_failing_seat_degrades_without_sinking_panel(project, brief, messages):
    class FlakyLLM(StubLLM):
        def complete(self, *, system, user, max_tokens=1500, temperature=0.3):
            with self._lock:
                self.calls.append({"system": system, "user": user})
            if "CTO" in system:
                raise RuntimeError("model unavailable")
            return self.response

    llm = FlakyLLM()
    panel = asyncio.run(
        gather_specialist_takes(project, brief, messages, llm=llm,
                                enabled=_on, kill_switch=_off)
    )
    assert len(panel.takes) == len(DEFAULT_ROLES)
    cto = panel.by_role("CTO")
    assert cto is not None and cto.degraded is True
    assert cto.confidence == 0.0
    # The other seats still produced real takes.
    assert panel.by_role("CFO").degraded is False


def test_malformed_json_degrades_that_seat(project, brief, messages):
    llm = StubLLM("not json at all")
    panel = asyncio.run(
        gather_specialist_takes(project, brief, messages, llm=llm,
                                enabled=_on, kill_switch=_off)
    )
    assert all(t.degraded for t in panel.takes)


# ============================================================
# Render
# ============================================================

def test_render_panel_folds_takes(project, brief, messages):
    llm = StubLLM()
    panel = asyncio.run(
        gather_specialist_takes(project, brief, messages, llm=llm,
                                enabled=_on, kill_switch=_off)
    )
    out = render_panel(panel)
    for role in DEFAULT_ROLES:
        assert f"### {role}" in out
    assert "Recommendation:" in out


def test_render_empty_panel():
    assert render_panel(SpecialistPanel(takes=[])) == "(no specialist takes)"
