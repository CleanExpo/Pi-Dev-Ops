"""Multi-model boardroom synthesis — port of Synthex lib/ai/boardroom.ts."""
from __future__ import annotations

import asyncio
import logging
import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .llm import complete_with_evidence
from app.server.provider_policy import independent_identity

log = logging.getLogger("pi-ceo.spec_pipeline.boardroom")

STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "could", "may", "might", "must", "shall", "can", "of", "in", "on", "at", "to",
    "for", "with", "by", "from", "as", "into", "this", "that", "these", "those",
    "not", "no", "yes", "also", "only", "very", "too", "just",
})

DEFAULT_PANEL = (
    {"role": "boardroom_panellist_primary"},
    {"role": "boardroom_panellist_secondary"},
)

DEFAULT_SYNTHESISER = {"role": "boardroom_synthesis"}
DEFAULT_ESCALATION = {"role": "boardroom_escalation"}


@dataclass
class PanellistOutcome:
    model_id: str
    response: str | None
    latency_ms: int = 0
    error: str | None = None
    requested_model: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BoardroomResponse:
    answer: str
    panel: list[PanellistOutcome] = field(default_factory=list)
    min_pairwise_similarity: float = 1.0
    escalated: bool = False
    synthesised_by: str = ""
    decision: str = "REJECT"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "panel": [p.to_dict() for p in self.panel],
            "min_pairwise_similarity": self.min_pairwise_similarity,
            "escalated": self.escalated,
            "synthesised_by": self.synthesised_by,
            "decision": self.decision,
            "confidence": self.confidence,
        }


def tokenise(text: str) -> set[str]:
    return {
        t for t in re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()
        if len(t) > 2 and t not in STOPWORDS
    }


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def compute_min_pairwise_jaccard(responses: list[str]) -> float:
    if len(responses) < 2:
        return 1.0
    sets = [tokenise(r) for r in responses]
    minimum = 1.0
    for i, sa in enumerate(sets):
        for sb in sets[i + 1:]:
            minimum = min(minimum, jaccard(sa, sb))
    return minimum


async def _call_panellist(seat: dict[str, str], prompt: str, system: str, max_tokens: int) -> PanellistOutcome:
    import time
    t0 = time.monotonic()
    try:
        outcome = await complete_with_evidence(
            prompt=prompt,
            system=system,
            model_id=seat.get("model_id"),
            provider=seat.get("provider"),
            max_tokens=max_tokens,
            role=seat.get("role", "boardroom_panellist"),
        )
        return PanellistOutcome(
            model_id=outcome.provenance["actual_model"],
            response=outcome.text,
            latency_ms=int((time.monotonic() - t0) * 1000),
            requested_model=outcome.provenance.get("requested_model"),
            provenance=outcome.provenance,
        )
    except Exception as exc:  # noqa: BLE001
        return PanellistOutcome(
            model_id="",
            requested_model=seat.get("model_id"),
            response=None,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=str(exc),
        )


def _parse_decision(answer: str) -> tuple[str, float]:
    """Only the final structured decision can authorize a build."""
    cleaned = answer.strip()
    if not cleaned:
        return "REJECT", 0.0
    try:
        payload = json.loads(cleaned)
    except ValueError:
        try:
            payload = json.loads(cleaned.splitlines()[-1])
        except ValueError:
            return "REJECT", 0.0
    if not isinstance(payload, dict):
        return "REJECT", 0.0
    decision, confidence = payload.get("decision"), payload.get("confidence")
    if (decision not in ("APPROVE_BUILD", "REDUCE_SCOPE", "REJECT")
            or isinstance(confidence, bool) or not isinstance(confidence, (float, int))
            or not 0 <= confidence <= 1 or not math.isfinite(confidence)):
        return "REJECT", 0.0
    return decision, float(confidence)


async def boardroom_query(
    *,
    prompt: str,
    system_prompt: str = "",
    panel: tuple[dict[str, str], ...] | None = None,
    divergence_threshold: float = 0.25,
) -> BoardroomResponse:
    seats = panel or DEFAULT_PANEL
    if len(seats) < 2:
        raise ValueError("boardroom needs at least 2 panellists")

    outcomes = await asyncio.gather(*[
        _call_panellist(s, prompt, system_prompt, 800)
        for s in seats
    ])
    successful = [o for o in outcomes if o.response]
    if not any(independent_identity(a.provenance, b.provenance)
               for i, a in enumerate(successful) for b in successful[i + 1:]):
        raise RuntimeError("boardroom: independent verified model panel unavailable")

    min_sim = compute_min_pairwise_jaccard([o.response or "" for o in successful])
    escalated = min_sim < divergence_threshold
    synthesiser = (
        DEFAULT_ESCALATION if escalated else DEFAULT_SYNTHESISER
    )

    transcript = "\n\n---\n\n".join(
        f"### {o.model_id}\n{o.response}" for o in successful
    )
    synthesis_prompt = (
        "Synthesise this boardroom discussion into one recommendation.\n"
        "Note disagreements. End with JSON on its own line:\n"
        '{"decision":"APPROVE_BUILD|REDUCE_SCOPE|REJECT","confidence":0.0}\n\n'
        f"Question:\n{prompt}\n\nPanel:\n{transcript}"
    )
    synthesis = await complete_with_evidence(
        prompt=synthesis_prompt,
        max_tokens=1200,
        role=synthesiser["role"],
    )
    answer = synthesis.text
    decision, confidence = _parse_decision(answer)
    return BoardroomResponse(
        answer=answer,
        panel=list(outcomes),
        min_pairwise_similarity=min_sim,
        escalated=escalated,
        synthesised_by=synthesis.provenance["actual_model"],
        decision=decision,
        confidence=confidence,
    )
