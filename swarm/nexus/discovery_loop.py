"""Per-client Discovery loop orchestrator — pure logic.

Phase B / B3. Given a Loop + injected stores, runs one cycle:

  1. Read outcomes since last_run_at (bounded by MAX_OUTCOMES_PER_CYCLE)
  2. Ask the LLM for a discovery brief (signals + recommendation)
  3. Persist the brief as an Outcome row (source='manual', metric='discovery_brief')
  4. Compute next_run_at from cadence
  5. Return CycleResult

The module has no knowledge of HTTP, Anthropic, or Supabase. All I/O
goes through injected Protocols.

Tier for the LLM call should be WORKING per the Phase B plan; the
caller is responsible for wiring that (this module just calls
`llm.complete(...)`).
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Literal, Protocol

from .outcomes import OutcomesStore
from .types import Loop, Outcome

log = logging.getLogger("pi-ceo.nexus.discovery_loop")

MAX_OUTCOMES_PER_CYCLE = 200
LOOP_COST_USD_CAP = 0.50

CYCLE_DEFAULT_WINDOW = timedelta(days=7)
VALID_CADENCES = ("24h", "7d", "30d")


# ============================================================
# Protocols
# ============================================================


class LLMProtocol(Protocol):
    def complete(self, *, system: str, user: str,
                 max_tokens: int = 1024, temperature: float = 0.3) -> str: ...


class ClockProtocol(Protocol):
    def now(self) -> datetime: ...


class LoopsStore(Protocol):
    def list_due(self, *, now: datetime) -> list[Loop]: ...
    def save(self, loop: Loop) -> Loop: ...


# ============================================================
# Result + summary types
# ============================================================


CycleResultKind = Literal[
    "ok",
    "no_outcomes",
    "llm_error",
    "cost_capped",
    "invalid_cadence",
]


@dataclass(frozen=True)
class CycleResult:
    result: CycleResultKind
    loop_id: str
    brief_outcome_id: str | None = None
    next_run_at: str = ""
    outcomes_consumed: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class RunSummary:
    processed: int = 0
    ok: int = 0
    skipped_no_outcomes: int = 0
    llm_errors: int = 0
    cost_capped: int = 0
    invalid_cadence: int = 0
    cycle_results: list[CycleResult] = field(default_factory=list)


# ============================================================
# Cadence parsing
# ============================================================


def parse_cadence(cadence: str) -> timedelta:
    """Return the timedelta for a cadence label.

    Raises ValueError for unknown labels. UTC-anchored so DST has no
    effect (we never operate in local time).
    """
    table = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    if cadence not in table:
        raise ValueError(f"invalid cadence {cadence!r} (expected one of {VALID_CADENCES})")
    return table[cadence]


# ============================================================
# Single-loop cycle
# ============================================================


_DISCOVERY_SYSTEM_PROMPT = """You are the Discovery analyst for an autonomous
client growth platform. You receive recent outcome signals for ONE workspace
and produce ONE structured discovery brief.

Return STRICT JSON with these keys only:

  brief                (string, 1-2 sentences — what changed in the window)
  top_signals          (array of {id: string, why_it_matters: string}, max 3)
  recommended_action   (string, 1 sentence — the next concrete step)
  recommended_loop     (one of: 'content', 'kpi', 'geo', 'support', 'compliance', null)

Do NOT include any other keys. Do NOT explain. Output JSON only."""


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_outcomes_for_prompt(outcomes: Iterable[Outcome]) -> str:
    lines = []
    for o in outcomes:
        bits = [f"id={o.id}", f"source={o.source}", f"metric={o.metric}"]
        if o.value_numeric is not None:
            bits.append(f"value={o.value_numeric}")
        if o.value_text:
            bits.append(f"text={o.value_text}")
        bits.append(f"captured_at={o.captured_at}")
        lines.append(" ".join(bits))
    return "\n".join(lines)


def run_discovery_cycle(
    loop: Loop,
    *,
    llm: LLMProtocol,
    outcomes_store: OutcomesStore,
    clock: ClockProtocol,
    max_outcomes: int = MAX_OUTCOMES_PER_CYCLE,
) -> CycleResult:
    """Run ONE discovery cycle for `loop`. Pure side-effects: one read
    from outcomes_store, one optional write back via outcomes_store.write.
    Never raises — failures surface as CycleResult.result values.
    """
    try:
        delta = parse_cadence(loop.cadence)
    except ValueError as exc:
        return CycleResult(
            result="invalid_cadence", loop_id=loop.id, reason=str(exc),
        )

    now = clock.now()
    last_run = _parse_iso(loop.last_run_at)
    window_start = last_run if last_run else (now - CYCLE_DEFAULT_WINDOW)

    # Pull outcomes for this workspace; in-memory + Supabase impls both
    # return newest-first ordering with a bounded limit.
    raw_outcomes = outcomes_store.list(
        workspace_slug=loop.workspace_slug, limit=max_outcomes,
    )
    in_window = [
        o for o in raw_outcomes
        if (_parse_iso(o.captured_at) or window_start) >= window_start
    ]

    next_run_at = (now + delta).isoformat()

    if not in_window:
        return CycleResult(
            result="no_outcomes",
            loop_id=loop.id,
            next_run_at=next_run_at,
            outcomes_consumed=0,
        )

    user_prompt = (
        f"Workspace: {loop.workspace_slug}\n"
        f"Window: {window_start.isoformat()} → {now.isoformat()}\n\n"
        f"Outcomes (newest first):\n{_format_outcomes_for_prompt(in_window)}"
    )

    try:
        raw = llm.complete(
            system=_DISCOVERY_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=600,
            temperature=0.2,
        )
        brief = json.loads(raw)
        if not isinstance(brief, dict) or "brief" not in brief:
            raise ValueError("LLM response missing 'brief' key")
    except Exception as exc:  # noqa: BLE001 — pure-logic fallthrough
        log.warning(
            "discovery cycle llm_error loop=%s err=%s", loop.id, exc,
        )
        return CycleResult(
            result="llm_error",
            loop_id=loop.id,
            next_run_at=next_run_at,
            outcomes_consumed=len(in_window),
            reason=str(exc),
        )

    brief_outcome = Outcome(
        id=f"nex-brf-{uuid.uuid4().hex[:12]}",
        workspace_id=loop.workspace_id,
        workspace_slug=loop.workspace_slug,
        source="manual",
        metric="discovery_brief",
        captured_at=now.isoformat(),
        value_text=str(brief.get("brief", ""))[:2000],
        raw_payload=brief,
    )
    outcomes_store.write(brief_outcome)

    return CycleResult(
        result="ok",
        loop_id=loop.id,
        brief_outcome_id=brief_outcome.id,
        next_run_at=next_run_at,
        outcomes_consumed=len(in_window),
    )
