"""
plan_discovery.py — RA-679: Plan variation discovery loop.

Implements Karpathy-autoresearch-style plan selection: before the main
generator runs, generate 3 alternative plan approaches and score each with a
fast lightweight evaluator.  The winning approach is prepended to the generator
spec so Claude has the best strategy as context.

Discovery flow:
  1. Generate 3 plan variants for the same brief (parallel, using haiku for speed)
  2. Score each variant with a single lightweight scorer (sonnet, text-only)
  3. Pick the highest-scoring variant (ties broken by first)
  4. Append the winner to the generator spec
  5. Log discovery data to .harness/plan-discoveries/<date>.jsonl

After 50 discoveries, pattern_analyser() proposes updates to RESEARCH_INTENT.md.

Usage (called from sessions.py _phase_generate):
    from .agents.plan_discovery import discover_best_plan
    enriched_spec = await discover_best_plan(session, original_spec, brief)
"""
from __future__ import annotations

import asyncio
import datetime
import os
import json
import logging
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("pi-ceo.plan_discovery")

# Discovery log directory
_HARNESS_ROOT = Path(__file__).resolve().parents[3] / ".harness"
_DISCOVERY_DIR = _HARNESS_ROOT / "plan-discoveries"
_PATTERN_THRESHOLD = 50  # run analyser after this many discoveries


# ── Plan variant prompt templates ─────────────────────────────────────────────

_VARIANT_PROMPTS = [
    # Variant A — Direct: implement the most obvious approach first
    (
        "PLANNING APPROACH: Direct Implementation\n"
        "Identify the minimal set of changes that satisfies the brief exactly.\n"
        "Prioritise: speed, minimal diff, no scope creep.\n"
        "Output a concise numbered plan (max 10 steps)."
    ),
    # Variant B — Defensive: correctness and tests first
    (
        "PLANNING APPROACH: Correctness-First\n"
        "Start by identifying what tests exist, what must not break, "
        "and what edge cases the brief implies.\n"
        "Plan: write/update tests → implement → verify → commit.\n"
        "Output a concise numbered plan (max 10 steps)."
    ),
    # Variant C — Refactor-aware: check if existing code can be reused/simplified
    (
        "PLANNING APPROACH: Leverage Existing Code\n"
        "Before writing new code, scan for existing utilities, helpers, or patterns "
        "that can be extended. Prefer modifying over creating.\n"
        "Plan: read codebase → identify reuse → implement with minimal new code → commit.\n"
        "Output a concise numbered plan (max 10 steps)."
    ),
]

_PLAN_GEN_PROMPT_TMPL = """You are a senior software architect.
Given the brief below, produce a step-by-step implementation plan using the approach described.

Brief:
{brief}

{approach}

Respond ONLY with the numbered plan. No explanation, no preamble.
"""

_PLAN_SCORE_PROMPT_TMPL = """Score this implementation plan on how well it would solve the brief.

Brief: {brief}

Plan to score:
{plan}

Score on 3 criteria (1-10 each):
FEASIBILITY: <n>/10 — can this be done as described without ambiguity?
COMPLETENESS: <n>/10 — does the plan cover all requirements in the brief?
EFFICIENCY: <n>/10 — is the approach lean or does it over-engineer?
PLAN_SCORE: <average>/10
"""


# ── Core functions ─────────────────────────────────────────────────────────────

async def _generate_plan_variant(
    brief: str,
    approach: str,
    session_id: str = "",
) -> str:
    """Generate one plan variant using haiku (fast + cheap)."""
    try:
        from claude_agent_sdk import (  # noqa: PLC0415
            AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient,
            ResultMessage, TextBlock,
        )
    except ImportError:
        return ""

    # RA-1420 — pop ANTHROPIC_API_KEY if OAuth token
    _k = os.environ.get("ANTHROPIC_API_KEY", "")
    if _k == "" or _k.startswith("sk-ant-oat01-"):
        os.environ.pop("ANTHROPIC_API_KEY", None)
    prompt = _PLAN_GEN_PROMPT_TMPL.format(brief=brief[:1500], approach=approach)
    try:
        options = ClaudeAgentOptions(model="haiku", permission_mode="bypassPermissions")
        client = ClaudeSDKClient(options)
        parts: list[str] = []
        try:
            await client.connect()
            await client.query(prompt)
            async for msg in client.receive_messages():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            parts.append(block.text)
                elif isinstance(msg, ResultMessage):
                    break
        finally:
            await client.disconnect()
        return "\n".join(parts).strip()
    except Exception as exc:
        log.warning("plan_discovery: variant generation failed: %s", exc)
        return ""


async def _score_plan(brief: str, plan: str) -> float:
    """Score a plan variant (0-10). Returns 0.0 on failure."""
    if not plan:
        return 0.0
    try:
        from claude_agent_sdk import (  # noqa: PLC0415
            AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient,
            ResultMessage, TextBlock,
        )
    except ImportError:
        return 5.0  # neutral default

    # RA-1420 — pop ANTHROPIC_API_KEY if OAuth token
    _k = os.environ.get("ANTHROPIC_API_KEY", "")
    if _k == "" or _k.startswith("sk-ant-oat01-"):
        os.environ.pop("ANTHROPIC_API_KEY", None)
    prompt = _PLAN_SCORE_PROMPT_TMPL.format(brief=brief[:800], plan=plan[:1200])
    try:
        options = ClaudeAgentOptions(model="haiku", permission_mode="bypassPermissions")
        client = ClaudeSDKClient(options)
        parts: list[str] = []
        try:
            await client.connect()
            await client.query(prompt)
            async for msg in client.receive_messages():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            parts.append(block.text)
                elif isinstance(msg, ResultMessage):
                    break
        finally:
            await client.disconnect()
        text = "\n".join(parts)
        for line in text.splitlines():
            if line.upper().startswith("PLAN_SCORE:"):
                try:
                    return float(line.split(":")[1].strip().split("/")[0].strip())
                except (ValueError, IndexError):
                    pass
    except Exception as exc:
        log.warning("plan_discovery: scoring failed: %s", exc)
    return 0.0


def _log_discovery(
    brief: str,
    variants: list[str],
    scores: list[float],
    winner_idx: int,
    duration_s: float,
    session_id: str = "",
) -> None:
    """Append a discovery record to today's JSONL file (non-fatal)."""
    try:
        _DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.date.today().isoformat()
        path = _DISCOVERY_DIR / f"{today}.jsonl"
        row = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "session_id": session_id,
            "brief_hash": _brief_hash(brief),
            "brief_preview": brief[:100],
            "scores": scores,
            "winner": winner_idx,
            "winner_score": scores[winner_idx] if scores else 0,
            "duration_s": round(duration_s, 1),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception as exc:
        log.warning("plan_discovery: log failed (non-fatal): %s", exc)


def _brief_hash(brief: str) -> str:
    import hashlib  # noqa: PLC0415
    return hashlib.sha256(brief.encode()).hexdigest()[:12]


def _count_discoveries() -> int:
    """Count total discovery records across all JSONL files."""
    total = 0
    if not _DISCOVERY_DIR.exists():
        return 0
    for p in _DISCOVERY_DIR.glob("*.jsonl"):
        try:
            total += sum(1 for _ in open(p, encoding="utf-8"))
        except OSError:
            pass
    return total


def _maybe_propose_research_intent() -> None:
    """After PATTERN_THRESHOLD discoveries, propose RESEARCH_INTENT.md updates.

    Reads the last N discoveries, looks for patterns (consistently high-scoring
    approaches per intent type), and appends suggestions to RESEARCH_INTENT.md.
    Non-fatal.
    """
    n = _count_discoveries()
    if n < _PATTERN_THRESHOLD or n % _PATTERN_THRESHOLD != 0:
        return
    try:
        # Collect last 50 discovery records
        records: list[dict] = []
        for p in sorted(_DISCOVERY_DIR.glob("*.jsonl"), reverse=True)[:7]:
            for line in reversed(list(open(p, encoding="utf-8"))):
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
                if len(records) >= _PATTERN_THRESHOLD:
                    break
            if len(records) >= _PATTERN_THRESHOLD:
                break

        if not records:
            return

        # Simple analysis: which variant (0=Direct, 1=Defensive, 2=Leverage) wins most?
        winner_counts = [0, 0, 0]
        for rec in records:
            w = rec.get("winner", 0)
            if 0 <= w < 3:
                winner_counts[w] += 1

        dominant = winner_counts.index(max(winner_counts))
        variant_names = ["Direct Implementation", "Correctness-First", "Leverage Existing Code"]
        suggestion = (
            f"\n## Plan Discovery Insight (auto-generated, {datetime.date.today()})\n\n"
            f"After {n} plan variation experiments:\n"
            f"- Dominant winning approach: **{variant_names[dominant]}** "
            f"({winner_counts[dominant]}/{len(records)} wins)\n"
            f"- Variant win rates: Direct={winner_counts[0]}, "
            f"Defensive={winner_counts[1]}, Leverage={winner_counts[2]}\n"
        )
        intent_file = _HARNESS_ROOT / "intent" / "RESEARCH_INTENT.md"
        if intent_file.exists():
            existing = intent_file.read_text(encoding="utf-8")
            if "Plan Discovery Insight" not in existing:
                intent_file.write_text(existing + suggestion, encoding="utf-8")
                log.info("plan_discovery: RESEARCH_INTENT.md updated with pattern insight")
    except Exception as exc:
        log.warning("plan_discovery: pattern analysis failed (non-fatal): %s", exc)


# ── Public API ────────────────────────────────────────────────────────────────

async def discover_best_plan(
    brief: str,
    original_spec: str,
    session_id: str = "",
    enabled: bool = True,
) -> tuple[str, Optional[dict]]:
    """Generate 3 plan variants in parallel and return the best-scoring one.

    Returns (enriched_spec, discovery_meta).
      enriched_spec — original spec + winning plan prepended
      discovery_meta — {scores, winner, winner_score, duration_s} or None on skip/error

    When enabled=False (or on any error), returns (original_spec, None) unchanged.
    The generator spec works fine without a discovery plan — this is additive only.
    """
    if not enabled:
        return original_spec, None

    t0 = time.monotonic()
    log.info("plan_discovery: generating 3 variants for session=%s", session_id)

    try:
        # Generate all 3 variants in parallel
        plans = await asyncio.gather(
            *[_generate_plan_variant(brief, approach, session_id)
              for approach in _VARIANT_PROMPTS],
            return_exceptions=True,
        )
        plans = [p if isinstance(p, str) else "" for p in plans]

        if not any(plans):
            log.info("plan_discovery: all variants empty — skipping")
            return original_spec, None

        # Score all valid variants in parallel
        scores = await asyncio.gather(
            *[_score_plan(brief, plan) for plan in plans],
            return_exceptions=True,
        )
        scores = [s if isinstance(s, float) else 0.0 for s in scores]

        winner_idx = scores.index(max(scores))
        winner_plan = plans[winner_idx]
        winner_score = scores[winner_idx]
        duration_s = time.monotonic() - t0

        log.info(
            "plan_discovery: winner=variant_%d score=%.1f duration=%.1fs session=%s",
            winner_idx, winner_score, duration_s, session_id,
        )

        # Prepend winning plan to the spec as context
        variant_names = ["Direct", "Correctness-First", "Leverage-Existing"]
        enriched = (
            f"--- PLAN DISCOVERY: Winning approach: {variant_names[winner_idx]} "
            f"(score {winner_score:.1f}/10) ---\n"
            f"{winner_plan}\n"
            f"--- END PLAN DISCOVERY ---\n\n"
            + original_spec
        )

        meta = {
            "scores": scores,
            "winner": winner_idx,
            "winner_score": winner_score,
            "duration_s": round(duration_s, 1),
        }
        _log_discovery(brief, plans, scores, winner_idx, duration_s, session_id)
        _maybe_propose_research_intent()
        return enriched, meta

    except Exception as exc:
        log.warning("plan_discovery: failed (non-fatal): %s — using original spec", exc)
        return original_spec, None
