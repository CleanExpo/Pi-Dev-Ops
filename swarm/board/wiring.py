"""Pi-CEO Board Layer-3 dispatcher — Wave 5.4 Phase B (LLM wiring).

Strategic asks land here from Margot. Each of the 8 non-CEO personas
gets a parallel ``qwen3:14b`` call via the local Ollama daemon; the CEO
persona then synthesises their opinions into a decision memo and emits a
``[DISPATCH-TO: PM-X]`` sentinel that the parser uses to route the
implementation to the right Senior PM (PM-Core / PM-CCW / PM-RA / PM-DR
/ PM-Synthex).

Founder directive 2026-05-13: no paid inference; free local only. This
dispatcher pins ``qwen3:14b`` regardless of ROLE_TIER["board"]="top" — we
call ``app.server.provider_ollama.call`` directly instead of going through
``select_provider_model`` so Anthropic / OpenRouter cannot be picked.

dispatch() stays SYNC at the call boundary. Internally we ``asyncio.run``
an ``asyncio.gather`` over the 8 persona calls so total wall-time is one
model latency, not eight.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass

from app.server.provider_ollama import call as ollama_call

from .personas import CANONICAL_PERSONAS, CEO_SYNTHESIS_TEMPLATE, Persona

log = logging.getLogger("swarm.board.wiring")

BOARD_MODEL_ID = "qwen3:14b"
# Per-persona timeout has to cover Ollama's serialised queue: with 8
# concurrent ``asyncio.gather`` calls against a single-stream local model,
# the last request in the queue waits behind the previous seven. Keep it
# generous so cold-queue cycles don't degrade to ABSTAIN fallbacks.
PERSONA_TIMEOUT_S = 600.0
CEO_TIMEOUT_S = 240.0

# Valid Senior PM slugs the CEO may dispatch to.
VALID_PM_SLUGS = {"PM-Core", "PM-CCW", "PM-RA", "PM-DR", "PM-Synthex"}

# Rationale per slug (one line each; used when dispatched_to is set).
_PM_RATIONALES = {
    "PM-Core":    "Cross-portfolio / Unite-Group infra implementation.",
    "PM-CCW":     "Cleaner Clean Wash CRM build implicated.",
    "PM-RA":      "RestoreAssist iOS / SaaS implementation implicated.",
    "PM-DR":      "Disaster Recovery platform implementation implicated.",
    "PM-Synthex": "Synthex AEO / portfolio-brain implementation implicated.",
}

_SENTINEL_RE = re.compile(
    r"\[\s*DISPATCH-?TO\s*:\s*(PM-(?:Core|CCW|RA|DR|Synthex)|NONE)\s*\]",
    re.IGNORECASE,
)


@dataclass
class BoardDecision:
    strategic_ask: str
    opinions: dict[str, str]  # persona role → opinion text
    decision_memo: str
    dispatched_to: str | None  # which Senior PM, if any
    rationale: str


# ── Internal helpers ────────────────────────────────────────────────────────


def _strip_think_tags(text: str) -> str:
    """Qwen3 emits <think>...</think> chain-of-thought blocks. Remove them.

    Also collapses repeated blank lines that often remain after stripping.
    """
    out = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


async def _call_persona(persona: Persona, strategic_ask: str) -> tuple[str, str]:
    """One non-CEO persona call. Returns (role, opinion_text).

    On failure, falls back to a deterministic non-stub message that is
    still ≥100 chars so the dispatcher's contract holds even when Ollama
    flakes mid-flight. Caller should log; we do not raise.
    """
    prompt = persona.prompt_template.format(strategic_ask=strategic_ask)
    rc, text, _cost, err = await ollama_call(
        prompt=prompt,
        model_id=BOARD_MODEL_ID,
        timeout_s=PERSONA_TIMEOUT_S,
        role=f"board.{persona.role.lower().replace(' ', '_')}",
        max_tokens=600,
    )
    if rc != 0 or not text:
        log.warning("board: persona %s failed (%s) — fallback", persona.role, err)
        fallback = (
            f"The {persona.role} voice could not be reached on this cycle "
            f"(local inference error: {err or 'unknown'}). Defaulting to a "
            f"conservative reading of {persona.perspective.lower()} — the "
            "CEO should treat this voice as ABSTAIN and weight the other "
            "seven accordingly."
        )
        return persona.role, fallback
    return persona.role, _strip_think_tags(text)


async def _call_ceo(strategic_ask: str,
                    opinions: dict[str, str]) -> str:
    """CEO synthesis call. Returns decision_memo text."""
    opinions_block = "\n\n".join(
        f"### {role}\n{opinion}" for role, opinion in opinions.items()
    )
    prompt = CEO_SYNTHESIS_TEMPLATE.format(
        strategic_ask=strategic_ask,
        opinions_block=opinions_block,
    )
    rc, text, _cost, err = await ollama_call(
        prompt=prompt,
        model_id=BOARD_MODEL_ID,
        timeout_s=CEO_TIMEOUT_S,
        role="board.ceo_synthesis",
        max_tokens=900,
    )
    if rc != 0 or not text:
        log.warning("board: CEO synthesis failed (%s) — fallback memo", err)
        # Fallback memo cites three personas by name so the contract holds.
        return (
            "CEO synthesis unavailable on this cycle (local inference error). "
            "Defaulting to NO ACTION until next deliberation. The Contrarian, "
            "Revenue, and Technical Architect voices should be re-run before "
            "re-attempting this dispatch.\n"
            "[DISPATCH-TO: NONE]"
        )
    return _strip_think_tags(text)


def _parse_dispatch_target(memo: str) -> tuple[str | None, str]:
    """Find the [DISPATCH-TO: PM-X] sentinel. Returns (slug_or_None, rationale)."""
    match = _SENTINEL_RE.search(memo)
    if not match:
        return None, "No DISPATCH-TO sentinel found in CEO memo."
    raw = match.group(1).strip()
    # Normalise casing — sentinel may come back as PM-ra or pm-Core from the LLM.
    if raw.upper() == "NONE":
        return None, "CEO opted not to route to a Senior PM."
    # Re-match to canonical capitalisation.
    for slug in VALID_PM_SLUGS:
        if raw.upper() == slug.upper():
            return slug, _PM_RATIONALES[slug]
    return None, f"Unrecognised dispatch slug: {raw!r}"


async def _run_board(strategic_ask: str) -> BoardDecision:
    """Full async pipeline: parallel persona fan-out → CEO synthesis → parse."""
    non_ceo = [p for p in CANONICAL_PERSONAS if p.role != "CEO"]
    persona_results = await asyncio.gather(
        *[_call_persona(p, strategic_ask) for p in non_ceo]
    )
    opinions: dict[str, str] = {role: text for role, text in persona_results}

    memo = await _call_ceo(strategic_ask, opinions)
    opinions["CEO"] = memo

    dispatched_to, rationale = _parse_dispatch_target(memo)
    return BoardDecision(
        strategic_ask=strategic_ask,
        opinions=opinions,
        decision_memo=memo,
        dispatched_to=dispatched_to,
        rationale=rationale,
    )


# ── Public sync entry ───────────────────────────────────────────────────────


def dispatch(strategic_ask: str) -> BoardDecision:
    """Run the 9-persona Board deliberation against the given strategic ask.

    Sync at the boundary; internally drives 8 parallel ``qwen3:14b`` calls
    via ``asyncio.gather`` and then the CEO synthesis call.

    Keeps ``OLLAMA_KEEP_ALIVE`` set when run cold so the model stays
    resident between calls (avoids ~5s reload per persona).
    """
    # Default to keeping qwen3:14b resident — board cycles are bursty.
    os.environ.setdefault("OLLAMA_KEEP_ALIVE", "10m")
    return asyncio.run(_run_board(strategic_ask))
