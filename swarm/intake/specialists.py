"""Per-project specialist fan-out (RA-6671 P1) — pure logic, no DB / network.

The founder complaint behind RA-6671: "different bots with different skills —
when a project lands, each performs its specialised skill and brings back to the
board for discussion." The existing specialist bots (`swarm/bots/{cfo,cto,cmo,cs}`)
only run a daily 06:00 portfolio-wide clock; there is no per-project, on-demand
take. This module is that missing primitive.

Given a landed project (`ProjectContext` + the SPM's `SPMBrief` + recent thread
messages), fan out to the four senior specialists (CFO / CTO / CMO / CS) for an
on-demand skilled take, in parallel (`asyncio.gather`). Each take is a structured
assessment the board can deliberate on alongside the SPM brief.

Design mirrors `swarm/intake/spm.py`: all LLM I/O is behind the `LLMClient`
Protocol (tests stub it), all data shapes are frozen dataclasses, and there is no
DB or network here. It is gated default-OFF (`INTAKE_SPECIALIST_FANOUT`) and honours
the TAO kill-switch, so first activation is deliberate and spend is bounded — until
then `gather_specialist_takes` short-circuits to an empty panel with zero LLM calls.

This is P1: the primitive + tests. Wiring it between the forwarder and the board
(P2) and the live provider layer (P3) are separate, gated increments.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Callable, Iterable

from swarm.intake.spm import (
    LLMClient,
    ProjectContext,
    SPMBrief,
    ThreadMessage,
    _extract_json,
    _render_thread,
)

log = logging.getLogger(__name__)


# ============================================================
# Data shapes (frozen — no DB / ORM coupling)
# ============================================================

@dataclass(frozen=True)
class SpecialistTake:
    """One senior specialist's on-demand assessment of a landed project."""
    role: str  # "CFO" | "CTO" | "CMO" | "CS"
    assessment: str  # one paragraph, the specialist's read
    key_risks: list[str]
    recommendation: str  # prose: go / proceed-with-caution / hold, with why
    confidence: float  # 0.0..1.0
    degraded: bool = False  # True when the LLM call failed and this is a stub


@dataclass(frozen=True)
class SpecialistPanel:
    """The collected takes from a per-project fan-out."""
    takes: list[SpecialistTake]

    def by_role(self, role: str) -> SpecialistTake | None:
        for t in self.takes:
            if t.role == role:
                return t
        return None


# ============================================================
# Roles + role-specific system prompts
# ============================================================

DEFAULT_ROLES: tuple[str, ...] = ("CFO", "CTO", "CMO", "CS")

_ROLE_LENS: dict[str, str] = {
    "CFO": (
        "unit economics, pricing, margin, burn/runway impact, and whether the "
        "revenue case justifies the build cost"
    ),
    "CTO": (
        "technical framework fit, delivery risk, maintenance burden, security/"
        "compliance exposure, and build-vs-reuse"
    ),
    "CMO": (
        "market positioning, differentiation, demand signal, go-to-market path, "
        "and brand fit with the existing portfolio"
    ),
    "CS": (
        "client-success load, onboarding/support burden, churn/expansion risk, "
        "and whether we can service this well post-ship"
    ),
}


def _system_prompt(role: str) -> str:
    lens = _ROLE_LENS.get(role, "your domain of executive responsibility")
    return (
        f"You are the {role} of the Unite-Group workspace, giving an on-demand "
        f"take on a project that has just landed. Assess it strictly through the "
        f"lens of {lens}.\n\n"
        "You receive the project, the Senior Project Manager's structured brief, "
        "and the recent intake conversation. Give an honest, specific take from "
        f"your seat — not a summary of the SPM brief. You do NOT approve or ship; "
        "the board deliberates on every specialist take together.\n\n"
        "Return STRICT JSON with these keys ONLY (no markdown, no commentary "
        "outside the JSON):\n\n"
        "{\n"
        '  "assessment": "<one paragraph: your read from this seat>",\n'
        '  "key_risks": ["...", "..."],\n'
        '  "recommendation": "<one paragraph: go / proceed-with-caution / hold, and why>",\n'
        '  "confidence": <number 0.0-1.0>\n'
        "}\n"
    )


def _user_prompt(
    project: ProjectContext,
    brief: SPMBrief,
    recent_messages: Iterable[ThreadMessage],
    max_messages: int,
) -> str:
    return (
        f"Project: {project.name}\n"
        f"Slug: {project.slug}\n"
        f"Workspace: {project.workspace_slug}\n"
        f"Status: {project.status}\n"
        f"Description: {project.description or '(not yet provided)'}\n"
        f"\n--- SPM brief ---\n"
        f"Layout: {brief.layout}\n"
        f"Framework: {brief.framework}\n"
        f"Suitability: {brief.suitability}\n"
        f"Strengths: {', '.join(brief.swot.strengths) or '—'}\n"
        f"Weaknesses: {', '.join(brief.swot.weaknesses) or '—'}\n"
        f"Opportunities: {', '.join(brief.swot.opportunities) or '—'}\n"
        f"Threats: {', '.join(brief.swot.threats) or '—'}\n"
        f"Open questions: {', '.join(brief.open_questions) or '—'}\n"
        f"Rationale: {brief.rationale}\n"
        f"\n--- Recent intake conversation ---\n"
        f"{_render_thread(recent_messages, max_messages)}\n"
        f"\nGive your specialist take now."
    )


# ============================================================
# Gating (default-OFF, kill-switch honoured) — mirrors forwarders.py
# ============================================================

def specialist_fanout_enabled() -> bool:
    """Default-OFF gate. Flip with INTAKE_SPECIALIST_FANOUT=1."""
    return os.environ.get("INTAKE_SPECIALIST_FANOUT", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _default_kill_switch() -> bool:
    from swarm import kill_switch
    return kill_switch.is_active()


# ============================================================
# Fan-out
# ============================================================

def _parse_take(role: str, raw: str) -> SpecialistTake:
    parsed = _extract_json(raw)
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return SpecialistTake(
        role=role,
        assessment=str(parsed.get("assessment") or "").strip(),
        key_risks=[str(r) for r in parsed.get("key_risks") or []],
        recommendation=str(parsed.get("recommendation") or "").strip(),
        confidence=confidence,
    )


def _one_take(
    role: str,
    project: ProjectContext,
    brief: SPMBrief,
    recent_messages: list[ThreadMessage],
    llm: LLMClient,
    max_messages: int,
) -> SpecialistTake:
    """Synchronous single-role take. Wrapped in a thread by the async fan-out."""
    raw = llm.complete(
        system=_system_prompt(role),
        user=_user_prompt(project, brief, recent_messages, max_messages),
        max_tokens=1200,
        temperature=0.3,
    )
    return _parse_take(role, raw)


def _degraded_take(role: str) -> SpecialistTake:
    return SpecialistTake(
        role=role,
        assessment="",
        key_risks=[],
        recommendation="",
        confidence=0.0,
        degraded=True,
    )


async def gather_specialist_takes(
    project: ProjectContext,
    brief: SPMBrief,
    recent_messages: Iterable[ThreadMessage],
    *,
    llm: LLMClient,
    roles: Iterable[str] = DEFAULT_ROLES,
    max_messages: int = 30,
    enabled: Callable[[], bool] = specialist_fanout_enabled,
    kill_switch: Callable[[], bool] = _default_kill_switch,
) -> SpecialistPanel:
    """Fan a landed project out to the specialist roles in parallel.

    Pure orchestration around per-role LLM calls. No DB, no network beyond the
    injected `llm`. Returns an empty panel — with ZERO LLM calls — when the
    fan-out is disabled or the kill-switch is active, so this primitive is inert
    until deliberately activated (P2/P3). A single role whose LLM call fails
    degrades to a low-confidence stub take rather than sinking the whole panel,
    so the board still receives the other seats' input.
    """
    role_list = list(roles)
    if not enabled():
        return SpecialistPanel(takes=[])
    if kill_switch():
        log.warning(
            "specialist fan-out skipped: kill-switch active (project=%s)",
            project.project_id,
        )
        return SpecialistPanel(takes=[])

    messages = list(recent_messages)

    async def _run(role: str) -> SpecialistTake:
        try:
            return await asyncio.to_thread(
                _one_take, role, project, brief, messages, llm, max_messages,
            )
        except Exception:  # noqa: BLE001 — one seat failing must not sink the panel
            log.exception(
                "specialist take failed (role=%s project=%s)",
                role, project.project_id,
            )
            return _degraded_take(role)

    takes = await asyncio.gather(*(_run(role) for role in role_list))
    return SpecialistPanel(takes=list(takes))


# ============================================================
# Render (fold the panel into the board packet)
# ============================================================

def render_panel(panel: SpecialistPanel) -> str:
    """Render the specialist panel as board material_input.

    The board deliberates on the SPM brief AND the specialist takes together.
    """
    if not panel.takes:
        return "(no specialist takes)"
    blocks: list[str] = []
    for t in panel.takes:
        if t.degraded:
            blocks.append(f"### {t.role}\n(take unavailable — LLM call failed)")
            continue
        risks = "; ".join(t.key_risks) or "—"
        blocks.append(
            f"### {t.role} (confidence {t.confidence:.2f})\n"
            f"Assessment: {t.assessment}\n"
            f"Key risks: {risks}\n"
            f"Recommendation: {t.recommendation}"
        )
    return "\n\n".join(blocks)


__all__ = [
    "SpecialistTake",
    "SpecialistPanel",
    "DEFAULT_ROLES",
    "specialist_fanout_enabled",
    "gather_specialist_takes",
    "render_panel",
]
