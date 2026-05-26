"""Senior Project Manager (SPM) — pure logic, no DB / network.

Two responsibilities per swarm/intake/SPEC.md:

  1. Read a project + recent messages and produce a `SPMBrief` for the
     board (layout / framework / suitability / SWOT / open questions /
     readiness signal).

  2. After the board responds, aggregate the deliberation into a
     partner-facing reply (in Margot's founder voice — actual voice
     formatting happens in the Margot router; this module returns
     structured text).

Plus three authority-gating helpers per SPEC §G2 (workspace access vs.
approval authority — separate concerns) and one anti-spoofing helper
per SPEC §G3 (partner_id must come from trusted channels).

All DB I/O lives in the caller (margot_router / cli). All LLM I/O is
behind an `LLMClient` Protocol so unit tests stub it with a fake.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable, Literal, Protocol


# ============================================================
# Data shapes (frozen dataclasses — no DB / ORM coupling)
# ============================================================

@dataclass(frozen=True)
class ProjectContext:
    """Subset of intake_projects + intake_client_bots needed by SPM."""
    project_id: str
    workspace_slug: str  # SPEC §G4 — no client_slug
    name: str
    slug: str
    owner_partner_id: str  # SPEC §G2/G3 — trust-rooted creator
    approval_policy: Literal[
        "creator_only", "all_partners", "majority", "custom"
    ] = "creator_only"
    description: str | None = None
    status: str = "discovery"
    github_repo: str | None = None


@dataclass(frozen=True)
class ThreadMessage:
    """One inbound or outbound message on an intake thread."""
    direction: Literal["inbound", "outbound"]
    author: Literal["client", "margot", "spm", "board-summary", "system", "partner"]
    body: str
    submitted_by_partner_id: str | None  # SPEC §G3 — must be from a trusted channel
    created_at: str  # ISO 8601


@dataclass(frozen=True)
class SWOT:
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    threats: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SPMBrief:
    """Structured assessment the SPM produces for board fan-out."""
    layout: str
    framework: str
    suitability: str
    swot: SWOT
    open_questions: list[str]
    ready_for_production: bool
    rationale: str


@dataclass(frozen=True)
class BoardAggregation:
    """Distillation of board minutes into a partner-facing reply."""
    summary_for_partner: str  # markdown, suitable for Margot's relay
    open_questions: list[str]
    next_action: Literal["awaiting_partner", "ready_for_production", "paused_human_review"]
    metadata: dict  # raw board scores / minute path / personas referenced


@dataclass(frozen=True)
class AuthorityCheck:
    """Result of an authority gate (SPEC §G2)."""
    allowed: bool
    reason: str | None = None


# ============================================================
# LLM Protocol — tests stub this
# ============================================================

class LLMClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1500,
        temperature: float = 0.3,
    ) -> str:
        """Return the LLM's completion text. Implementations live elsewhere
        (e.g., a wrapper around openrouter / Anthropic). Tests stub this.
        """
        ...


# ============================================================
# Anti-spoofing — SPEC §G3
# ============================================================

def trusted_partner_id_for_inbound(
    *,
    bot_partner_id: str,
    telegram_chat_id: str,
    authorized_chat_ids: Iterable[str],
    telegram_from_user_id: int | None = None,
    partner_telegram_user_id: int | None = None,
) -> tuple[str | None, str | None]:
    """Derive `submitted_by_partner_id` from trusted identity sources only.

    Trust chain per SPEC §G3:
      (1) Bot identity — the receiving bot's `intake_client_bots.partner_id`
      (2) Authorized chat — the Telegram chat_id MUST be in `authorized_chat_ids`
      (3) Optional Telegram user id cross-check — defense in depth

    Returns:
      (partner_id, None) on accept, (None, reason) on reject.

    NEVER trust partner_id from message body or any user-supplied field.
    """
    authorized = set(str(c) for c in authorized_chat_ids)
    if authorized and str(telegram_chat_id) not in authorized:
        return None, (
            f"chat_id {telegram_chat_id} is not in this bot's authorized_chat_ids; "
            "rejecting to prevent impersonation (SPEC §G3.2)"
        )
    if (
        partner_telegram_user_id is not None
        and telegram_from_user_id is not None
        and telegram_from_user_id != partner_telegram_user_id
    ):
        return None, (
            f"telegram_from.id={telegram_from_user_id} does not match the expected "
            f"partner_telegram_user_id={partner_telegram_user_id}; rejecting "
            "(SPEC §G3.3)"
        )
    return bot_partner_id, None


# ============================================================
# Authority gates — SPEC §G2
# ============================================================

def can_approve_production(
    project: ProjectContext,
    requesting_partner_id: str,
) -> AuthorityCheck:
    """SPEC §G2 — only the creator approves production handoff under
    `creator_only` policy.

    Other policies (`all_partners`, `majority`, `custom`) are reserved
    for future implementation and default to DENY here so an unset
    policy can never accidentally ship.
    """
    if project.approval_policy == "creator_only":
        if requesting_partner_id == project.owner_partner_id:
            return AuthorityCheck(allowed=True)
        return AuthorityCheck(
            allowed=False,
            reason=(
                f"Only the project creator ({project.owner_partner_id}) can "
                f"approve production handoff under '{project.approval_policy}' "
                "policy (SPEC §G2)."
            ),
        )
    return AuthorityCheck(
        allowed=False,
        reason=(
            f"Approval policy '{project.approval_policy}' is reserved for a "
            "future PR; defaulting to DENY (SPEC §G2)."
        ),
    )


def can_change_ownership(
    project: ProjectContext,
    requesting_partner_id: str,
) -> AuthorityCheck:
    """SPEC §G2 — ownership transfer is creator-only (or future admin)."""
    if requesting_partner_id == project.owner_partner_id:
        return AuthorityCheck(allowed=True)
    return AuthorityCheck(
        allowed=False,
        reason=(
            f"Only the project creator ({project.owner_partner_id}) can change "
            "ownership (SPEC §G2). Workspace read/write access does NOT confer "
            "ownership-override authority."
        ),
    )


def can_delete_project(
    project: ProjectContext,
    requesting_partner_id: str,
) -> AuthorityCheck:
    """SPEC §G2 — project deletion is creator-only (or future admin)."""
    if requesting_partner_id == project.owner_partner_id:
        return AuthorityCheck(allowed=True)
    return AuthorityCheck(
        allowed=False,
        reason=(
            f"Only the project creator ({project.owner_partner_id}) can delete "
            "this project (SPEC §G2)."
        ),
    )


# ============================================================
# Brief generation
# ============================================================

SPM_SYSTEM_PROMPT = """You are the Senior Project Manager (SPM) for the
Unite-Group workspace. Three business partners (Phill, Duncan, Toby)
share visibility of every project. You receive a project + a recent
intake conversation thread, and you produce a STRUCTURED ASSESSMENT
that the executive board will deliberate on.

Your job is to be honest about layout, framework choice, suitability,
SWOT, and the open questions that still block production. You do NOT
ship anything; the board reviews your assessment, and only the project
creator can approve production handoff.

Return STRICT JSON with these keys ONLY (no markdown, no commentary
outside the JSON):

{
  "layout": "<one paragraph: the proposed shape of the deliverable>",
  "framework": "<one paragraph: the technical/business framework you'd pick>",
  "suitability": "<one paragraph: how this fits the partners' existing portfolio>",
  "swot": {
    "strengths": ["...", "..."],
    "weaknesses": ["...", "..."],
    "opportunities": ["...", "..."],
    "threats": ["...", "..."]
  },
  "open_questions": ["...", "..."],
  "ready_for_production": <true|false>,
  "rationale": "<one paragraph: why ready or not>"
}

Set "ready_for_production": true ONLY when:
  - Scope is locked (no open dependencies on partner clarification)
  - Framework is chosen (not 'we could use X or Y')
  - SWOT is concrete (no platitudes)
  - Success metrics are defined (in either layout or rationale)
"""


def _render_thread(messages: Iterable[ThreadMessage], max_messages: int = 30) -> str:
    """Format the last `max_messages` messages as plain text for the LLM."""
    msgs = list(messages)[-max_messages:]
    lines: list[str] = []
    for m in msgs:
        who = m.author
        if m.author == "partner" and m.submitted_by_partner_id:
            who = f"partner:{m.submitted_by_partner_id}"
        lines.append(f"[{m.created_at}] [{m.direction}] [{who}] {m.body}")
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of LLM output, tolerating chatter."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match is None:
        raise ValueError("LLM did not return a JSON object")
    return json.loads(match.group(0))


def build_spm_brief(
    project: ProjectContext,
    recent_messages: Iterable[ThreadMessage],
    *,
    llm: LLMClient,
    max_messages: int = 30,
) -> SPMBrief:
    """Produce an SPM brief from project context + recent thread messages.

    Pure orchestration around the LLM call. No DB. Tests stub `llm` with
    a fake `LLMClient` that returns canned JSON.
    """
    user_prompt = (
        f"Project: {project.name}\n"
        f"Slug: {project.slug}\n"
        f"Workspace: {project.workspace_slug}\n"
        f"Owner (creator) partner: {project.owner_partner_id}\n"
        f"Status: {project.status}\n"
        f"Description: {project.description or '(not yet provided)'}\n"
        f"\n--- Recent intake conversation ---\n"
        f"{_render_thread(recent_messages, max_messages)}\n"
        f"\nProduce the structured assessment now."
    )

    raw = llm.complete(
        system=SPM_SYSTEM_PROMPT,
        user=user_prompt,
        max_tokens=2000,
        temperature=0.3,
    )
    parsed = _extract_json(raw)

    swot_raw = parsed.get("swot") or {}
    swot = SWOT(
        strengths=[str(s) for s in swot_raw.get("strengths") or []],
        weaknesses=[str(s) for s in swot_raw.get("weaknesses") or []],
        opportunities=[str(s) for s in swot_raw.get("opportunities") or []],
        threats=[str(s) for s in swot_raw.get("threats") or []],
    )

    return SPMBrief(
        layout=str(parsed.get("layout") or "").strip(),
        framework=str(parsed.get("framework") or "").strip(),
        suitability=str(parsed.get("suitability") or "").strip(),
        swot=swot,
        open_questions=[str(q) for q in parsed.get("open_questions") or []],
        ready_for_production=bool(parsed.get("ready_for_production", False)),
        rationale=str(parsed.get("rationale") or "").strip(),
    )


# ============================================================
# Board response aggregation
# ============================================================

AGGREGATION_SYSTEM_PROMPT = """You are the Senior Project Manager (SPM)
distilling the executive board's deliberation into a single reply for
the project's partner team. The reply will be relayed by Margot in her
founder voice — write it as concise, partner-facing prose, not as
minutes.

You receive:
  - The SPM brief that was sent into the board
  - The board's minutes (markdown)
  - Who sent the latest partner message (you can speak to them by name)

Return STRICT JSON:

{
  "summary_for_partner": "<2-4 short paragraphs in markdown, partner-facing>",
  "open_questions": ["...", "..."],
  "next_action": "<one of: awaiting_partner | ready_for_production | paused_human_review>",
  "metadata": {"board_personas_aligned": <int>, "board_personas_dissenting": <int>}
}

Rules:
  - If the board surfaces material open questions, next_action MUST be 'awaiting_partner'
  - If 7+ of 9 personas align AND no material open questions, next_action MAY be 'ready_for_production'
  - If the board flags a hard blocker (legal / safety / financial), next_action MUST be 'paused_human_review'
  - Never claim 'ready_for_production' on your own — only suggest it; the project creator approves separately
"""


def aggregate_board_response(
    project: ProjectContext,
    spm_brief: SPMBrief,
    board_minutes: str,
    requesting_partner_id: str,
    *,
    llm: LLMClient,
) -> BoardAggregation:
    """Distill board minutes into a partner-facing reply.

    `requesting_partner_id` is the partner whose latest message triggered
    this board round — it's the addressee of the reply.
    """
    user_prompt = (
        f"Project: {project.name} (owner: {project.owner_partner_id})\n"
        f"Latest partner message came from: {requesting_partner_id}\n"
        f"\n--- SPM brief ---\n"
        f"Layout: {spm_brief.layout}\n"
        f"Framework: {spm_brief.framework}\n"
        f"Suitability: {spm_brief.suitability}\n"
        f"SWOT: {json.dumps({'strengths': spm_brief.swot.strengths, 'weaknesses': spm_brief.swot.weaknesses, 'opportunities': spm_brief.swot.opportunities, 'threats': spm_brief.swot.threats})}\n"
        f"Open questions: {spm_brief.open_questions}\n"
        f"Rationale: {spm_brief.rationale}\n"
        f"\n--- Board minutes ---\n"
        f"{board_minutes}\n"
        f"\nProduce the partner-facing distillation now."
    )

    raw = llm.complete(
        system=AGGREGATION_SYSTEM_PROMPT,
        user=user_prompt,
        max_tokens=1500,
        temperature=0.3,
    )
    parsed = _extract_json(raw)

    next_action = parsed.get("next_action", "awaiting_partner")
    if next_action not in {"awaiting_partner", "ready_for_production", "paused_human_review"}:
        next_action = "awaiting_partner"

    return BoardAggregation(
        summary_for_partner=str(parsed.get("summary_for_partner") or "").strip(),
        open_questions=[str(q) for q in parsed.get("open_questions") or []],
        next_action=next_action,
        metadata=parsed.get("metadata") or {},
    )
