"""Multi-model boardroom synthesis — port of Synthex lib/ai/boardroom.ts."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .llm import complete, parse_json_object

from app.server.model_registry import (
    OPENROUTER_DEEPSEEK_FLASH,
    OPENROUTER_OPUS,
    OPENROUTER_SONNET,
)

log = logging.getLogger("pi-ceo.spec_pipeline.boardroom")

STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "could", "may", "might", "must", "shall", "can", "of", "in", "on", "at", "to",
    "for", "with", "by", "from", "as", "into", "this", "that", "these", "those",
    "not", "no", "yes", "also", "only", "very", "too", "just",
})

DEFAULT_PANEL = (
    {"provider": "openrouter", "model_id": OPENROUTER_DEEPSEEK_FLASH},
    {"provider": "openrouter", "model_id": OPENROUTER_SONNET},
)

DEFAULT_SYNTHESISER = {"provider": "openrouter", "model_id": OPENROUTER_SONNET}
DEFAULT_ESCALATION = {"provider": "openrouter", "model_id": OPENROUTER_OPUS}


@dataclass
class PanellistOutcome:
    model_id: str
    response: str | None
    latency_ms: int = 0
    error: str | None = None

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


async def _call_panellist(model_id: str, prompt: str, system: str, max_tokens: int) -> PanellistOutcome:
    import time
    t0 = time.monotonic()
    try:
        text, _ = await complete(
            prompt=prompt,
            system=system,
            model_id=model_id,
            max_tokens=max_tokens,
            role="boardroom_panellist",
        )
        return PanellistOutcome(
            model_id=model_id,
            response=text,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        return PanellistOutcome(
            model_id=model_id,
            response=None,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=str(exc),
        )


def _parse_decision(answer: str) -> tuple[str, float]:
    m = re.search(
        r'\{"decision"\s*:\s*"(APPROVE_BUILD|REDUCE_SCOPE|REJECT)"\s*,\s*"confidence"\s*:\s*([\d.]+)\s*\}',
        answer,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).upper(), float(m.group(2))
    upper = answer.upper()
    if "APPROVE_BUILD" in upper or "APPROVE BUILD" in upper:
        return "APPROVE_BUILD", 0.75
    if "REDUCE_SCOPE" in upper:
        return "REDUCE_SCOPE", 0.5
    return "REJECT", 0.3


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
        _call_panellist(s["model_id"], prompt, system_prompt, 800)
        for s in seats
    ])
    successful = [o for o in outcomes if o.response]
    if not successful:
        raise RuntimeError("boardroom: no panellist responses")

    min_sim = compute_min_pairwise_jaccard([o.response or "" for o in successful])
    escalated = min_sim < divergence_threshold
    synth_model = (
        DEFAULT_ESCALATION["model_id"] if escalated
        else DEFAULT_SYNTHESISER["model_id"]
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
    answer, _ = await complete(
        prompt=synthesis_prompt,
        model_id=synth_model,
        max_tokens=1200,
        role="boardroom_synthesis",
    )
    decision, confidence = _parse_decision(answer)
    return BoardroomResponse(
        answer=answer,
        panel=list(outcomes),
        min_pairwise_similarity=min_sim,
        escalated=escalated,
        synthesised_by=synth_model,
        decision=decision,
        confidence=confidence,
    )
