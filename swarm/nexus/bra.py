"""BRA — Brief / Recommendation / Action generator.

Phase B / B5. Given a workspace + a recent-outcomes window, ask the
WORKING-tier LLM for a list of BRA cards. Every card MUST cite the
outcome.id values it draws from; cards whose evidence_ids do not
match a real Outcome in the fetched window are dropped (with a
metric incremented for observability).

Pure-logic — no real LLM or HTTP in this module. Caller injects
LLMProtocol + OutcomesStore.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal, Protocol

from .outcomes import OutcomesStore
from .types import Outcome

log = logging.getLogger("pi-ceo.nexus.bra")

Severity = Literal["info", "low", "medium", "high", "critical"]
Window = Literal["24h", "7d", "30d"]

_SEVERITY_RANK: dict[Severity, int] = {
    "critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0,
}

MAX_BRA_CARDS = 8
MIN_EVIDENCE_IDS_PER_CARD = 1


class LLMProtocol(Protocol):
    def complete(self, *, system: str, user: str,
                 max_tokens: int = 1024, temperature: float = 0.3) -> str: ...


@dataclass(frozen=True)
class BRACard:
    brief: str
    recommendation: str
    action: str
    severity: Severity
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class BRAReport:
    workspace_slug: str
    window: Window
    cards: tuple[BRACard, ...] = ()
    dropped_unanchored: int = 0
    dropped_malformed: int = 0


_BRA_SYSTEM_PROMPT = """You are the BRA analyst for one workspace at a time.

Given a list of recent Outcome rows (id + source + metric + value), produce
up to 8 BRA cards. Each card MUST cite the outcome ids it draws from.

Return STRICT JSON with this shape:

  {
    "cards": [
      {
        "brief": "<1-2 sentence statement of what happened>",
        "recommendation": "<1 sentence: what we should do about it>",
        "action": "<1 sentence: the next concrete step>",
        "severity": "info" | "low" | "medium" | "high" | "critical",
        "evidence_ids": ["<outcome.id>", ...]
      }
    ]
  }

Do NOT invent outcome ids. Every evidence_ids entry MUST exist in the
provided list. Do NOT include other keys. Output JSON only."""


def _format_outcomes(outcomes: list[Outcome]) -> str:
    lines = []
    for o in outcomes:
        bits = [f"id={o.id}", f"source={o.source}", f"metric={o.metric}"]
        if o.value_numeric is not None:
            bits.append(f"value_numeric={o.value_numeric}")
        if o.value_text:
            bits.append(f"value_text={o.value_text}")
        bits.append(f"captured_at={o.captured_at}")
        lines.append(" ".join(bits))
    return "\n".join(lines)


def _coerce_card(raw: dict, valid_ids: set[str]) -> tuple[BRACard | None, str]:
    """Return (card, reason). reason is one of 'ok', 'malformed', 'unanchored'."""
    if not isinstance(raw, dict):
        return None, "malformed"
    brief = raw.get("brief")
    recommendation = raw.get("recommendation")
    action = raw.get("action")
    severity = raw.get("severity")
    evidence = raw.get("evidence_ids")
    if not (
        isinstance(brief, str) and brief.strip()
        and isinstance(recommendation, str) and recommendation.strip()
        and isinstance(action, str) and action.strip()
        and severity in _SEVERITY_RANK
        and isinstance(evidence, list)
    ):
        return None, "malformed"
    anchored = tuple(eid for eid in evidence if isinstance(eid, str) and eid in valid_ids)
    if len(anchored) < MIN_EVIDENCE_IDS_PER_CARD:
        return None, "unanchored"
    return (
        BRACard(
            brief=brief.strip(),
            recommendation=recommendation.strip(),
            action=action.strip(),
            severity=severity,  # type: ignore[arg-type]
            evidence_ids=anchored,
        ),
        "ok",
    )


def generate_bra(
    *,
    workspace_slug: str,
    window: Window,
    outcomes_store: OutcomesStore,
    llm: LLMProtocol,
    limit: int = 100,
) -> BRAReport:
    """Pull outcomes → ask LLM → validate evidence_ids → return ranked cards.

    Never raises. LLM/JSON failures surface as an empty report with
    `dropped_malformed` incremented. Cards whose evidence_ids do not
    anchor in the fetched window are dropped with `dropped_unanchored`
    incremented.
    """
    outcomes = outcomes_store.list(workspace_slug=workspace_slug, limit=limit)

    if not outcomes:
        return BRAReport(workspace_slug=workspace_slug, window=window)

    valid_ids = {o.id for o in outcomes}
    user_prompt = (
        f"Workspace: {workspace_slug}\nWindow: {window}\n\n"
        f"Outcomes (newest first):\n{_format_outcomes(outcomes)}"
    )
    try:
        raw = llm.complete(
            system=_BRA_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=900,
            temperature=0.2,
        )
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response is not a JSON object")
        raw_cards = parsed.get("cards")
        if not isinstance(raw_cards, list):
            raise ValueError("LLM response missing 'cards' list")
    except Exception as exc:  # noqa: BLE001
        log.warning("BRA generation failed (workspace=%s): %s", workspace_slug, exc)
        return BRAReport(
            workspace_slug=workspace_slug, window=window, dropped_malformed=1,
        )

    cards: list[BRACard] = []
    dropped_unanchored = 0
    dropped_malformed = 0
    for raw_card in raw_cards[:MAX_BRA_CARDS]:
        card, reason = _coerce_card(raw_card, valid_ids)
        if reason == "ok" and card is not None:
            cards.append(card)
        elif reason == "unanchored":
            dropped_unanchored += 1
        else:
            dropped_malformed += 1

    cards.sort(key=lambda c: _SEVERITY_RANK[c.severity], reverse=True)
    return BRAReport(
        workspace_slug=workspace_slug,
        window=window,
        cards=tuple(cards),
        dropped_unanchored=dropped_unanchored,
        dropped_malformed=dropped_malformed,
    )
