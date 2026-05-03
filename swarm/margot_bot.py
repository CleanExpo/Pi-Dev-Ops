"""swarm/margot_bot.py — Wave 5.1: Margot Telegram personal-assistant engine.

Pure-Python engine for the Margot conversational surface. The orchestrator
+ a thin bot wrapper feed turns in via ``handle_turn``; this module owns:

  * Conversation persistence (.harness/margot/conversations/<chat_id>.jsonl)
  * Context assembly (senior-bot snapshots + Board state + last 10 turns +
    CCW state + MEMORY.md hooks)
  * Prompt construction for the LLM call
  * Response parsing including Board-trigger sentinels
  * Direct Telegram send (no draft_review HITL — Margot talking to the
    founder doesn't need approval; that gate is for outbound to others)

Decisions locked (2026-05-03):
  * Direct send to founder (no HITL gate)
  * JSONL conversation per chat_id (Honcho promotion is Wave 5.2)
  * Operating + last-10-turns + on-demand deep_research
  * Margot autonomously triggers Board via from_margot when finding
    score ≥ 7/10 (sentinel pattern below)

Sentinel for autonomous Board trigger — Margot's response can include:
    [BOARD-TRIGGER score=8 topic="Competitor X raised series B"]
    [insight body...]
    [/BOARD-TRIGGER]
The engine extracts these, queues board_bot.from_margot, and strips the
sentinel from the user-facing reply.

Public API:
  handle_turn(chat_id, user_text, *, message_id=None, repo_root=None)
      -> MargotTurn   — main entry
  load_history(chat_id, *, limit=10, repo_root=None) -> list[MargotTurn]
  build_context(repo_root) -> dict[str, Any]
  parse_board_triggers(response_text) -> list[BoardTrigger]
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.margot_bot")

REPO_ROOT = Path(__file__).resolve().parents[1]
CONVERSATIONS_DIR_REL = ".harness/margot/conversations"
DEFAULT_HISTORY_TURNS = 10
DEFAULT_BOARD_TRIGGER_THRESHOLD = 7  # 1-10 scale; ≥7 fires from_margot


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class MargotTurn:
    """One turn in the conversation."""
    turn_id: str = field(default_factory=lambda: f"mt-{uuid.uuid4().hex[:10]}")
    chat_id: str = ""
    user_text: str = ""
    margot_text: str = ""
    user_message_id: str | None = None
    board_session_ids: list[str] = field(default_factory=list)
    research_called: bool = False
    cost_usd: float = 0.0
    started_at: str = ""
    ended_at: str = ""
    error: str | None = None


@dataclass
class BoardTrigger:
    """A [BOARD-TRIGGER] sentinel parsed out of Margot's response."""
    topic: str
    insight: str
    score: int  # 1-10


# ── Persistence ─────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conversation_path(chat_id: str, repo_root: Path) -> Path:
    p = repo_root / CONVERSATIONS_DIR_REL / f"{chat_id}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _supabase_payload(turn: MargotTurn) -> dict[str, Any]:
    """Map MargotTurn → margot_conversations row. tenant_id default 'pi-ceo'
    per RA-1838 forward-compat (per-tenant verdict)."""
    return {
        "turn_id": turn.turn_id,
        "chat_id": turn.chat_id,
        "tenant_id": "pi-ceo",
        "user_text": turn.user_text,
        "margot_text": turn.margot_text,
        "user_message_id": turn.user_message_id,
        "board_session_ids": list(turn.board_session_ids or []),
        "research_called": bool(turn.research_called),
        "cost_usd": float(turn.cost_usd or 0.0),
        "started_at": turn.started_at or None,
        "ended_at": turn.ended_at or None,
        "error": turn.error,
    }


def _row_to_turn(row: dict[str, Any]) -> MargotTurn | None:
    """Map margot_conversations row → MargotTurn, tolerating missing fields."""
    try:
        return MargotTurn(
            turn_id=row.get("turn_id") or f"mt-{uuid.uuid4().hex[:10]}",
            chat_id=str(row.get("chat_id") or ""),
            user_text=row.get("user_text") or "",
            margot_text=row.get("margot_text") or "",
            user_message_id=row.get("user_message_id"),
            board_session_ids=list(row.get("board_session_ids") or []),
            research_called=bool(row.get("research_called") or False),
            cost_usd=float(row.get("cost_usd") or 0.0),
            started_at=row.get("started_at") or "",
            ended_at=row.get("ended_at") or "",
            error=row.get("error"),
        )
    except Exception:  # noqa: BLE001
        return None


def append_turn(turn: MargotTurn, *, repo_root: Path | None = None) -> Path:
    """Persist a turn to BOTH the JSONL hot cache and Supabase (RA-1905).

    JSONL is on Railway ephemeral disk and is wiped on redeploy; Supabase is
    the durable source of truth. Supabase write is fire-and-forget — failures
    log WARN and never raise (matches the existing supabase_log pattern). If
    Supabase is unconfigured (test envs), only the JSONL is written.
    """
    rr = repo_root or REPO_ROOT
    p = _conversation_path(turn.chat_id, rr)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(turn), ensure_ascii=False) + "\n")

    try:
        from app.server import supabase_log  # noqa: PLC0415
        supabase_log.insert_margot_conversation(_supabase_payload(turn))
    except Exception as exc:  # noqa: BLE001
        log.warning("margot: supabase insert suppressed (%s)", exc)
    return p


def load_history(chat_id: str, *,
                  limit: int = DEFAULT_HISTORY_TURNS,
                  repo_root: Path | None = None) -> list[MargotTurn]:
    """Load the last `limit` turns for a chat.

    RA-1905: Reads Supabase first (durable, survives redeploys). Falls back to
    the JSONL hot cache when Supabase is unconfigured (test envs) or returns
    nothing. After a Railway redeploy, JSONL is empty but Supabase rehydrates
    the conversation history.
    """
    rr = repo_root or REPO_ROOT

    # Supabase: source of truth (post-redeploy hydration path).
    rows: list[dict[str, Any]] = []
    try:
        from app.server import supabase_log  # noqa: PLC0415
        rows = supabase_log.select_margot_conversations(
            chat_id=chat_id, limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("margot: supabase select suppressed (%s)", exc)
        rows = []

    if rows:
        # Supabase returned rows ordered started_at desc → reverse to chrono.
        out: list[MargotTurn] = []
        for row in reversed(rows):
            t = _row_to_turn(row)
            if t is not None:
                out.append(t)
        if out:
            return out

    # Fallback: JSONL hot cache (test envs, Supabase outage, or pre-RA-1905).
    p = _conversation_path(chat_id, rr)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    out_jsonl: list[MargotTurn] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            out_jsonl.append(MargotTurn(**row))
        except Exception:  # noqa: BLE001
            continue
    return out_jsonl


# ── Context assembly ────────────────────────────────────────────────────────


def _load_last_per_business(jsonl_rel: str,
                              repo_root: Path) -> list[dict[str, Any]]:
    p = repo_root / jsonl_rel
    if not p.exists():
        return []
    last_per_biz: dict[str, dict[str, Any]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        bid = row.get("business_id")
        if bid:
            last_per_biz[bid] = row
    return list(last_per_biz.values())


def _load_recent_board_sessions(repo_root: Path,
                                  *, limit: int = 3) -> list[dict[str, Any]]:
    sessions_dir = repo_root / ".harness/board/sessions"
    if not sessions_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(sessions_dir.glob("*.json"))[-limit:]:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def _ccw_state_summary(repo_root: Path) -> dict[str, Any] | None:
    """Pull the most recent CCW row from each senior-bot ledger."""
    out: dict[str, Any] = {}
    for bot, jsonl_rel in (
        ("cs", ".harness/swarm/cs_state.jsonl"),
        ("cfo", ".harness/swarm/cfo_state.jsonl"),
        ("cmo", ".harness/swarm/cmo_state.jsonl"),
        ("cto", ".harness/swarm/cto_state.jsonl"),
    ):
        rows = _load_last_per_business(jsonl_rel, repo_root)
        for r in rows:
            if r.get("business_id") == "ccw-crm":
                out[bot] = r
                break
    return out or None


def build_context(*, repo_root: Path | None = None) -> dict[str, Any]:
    """Assemble per-turn operating context for Margot's prompt.

    Bounded prompt size — each section trimmed. Returns a structured dict
    that the prompt builder serialises.
    """
    rr = repo_root or REPO_ROOT
    return {
        "cfo": _load_last_per_business(
            ".harness/swarm/cfo_state.jsonl", rr,
        ),
        "cmo": _load_last_per_business(
            ".harness/swarm/cmo_state.jsonl", rr,
        ),
        "cto": _load_last_per_business(
            ".harness/swarm/cto_state.jsonl", rr,
        ),
        "cs": _load_last_per_business(
            ".harness/swarm/cs_state.jsonl", rr,
        ),
        "board_recent": _load_recent_board_sessions(rr, limit=3),
        "ccw": _ccw_state_summary(rr),
    }


# ── Prompt construction ─────────────────────────────────────────────────────


_MARGOT_SYSTEM_PROMPT = """You are Margot — Phill McGurk's personal
assistant and research bridge. You are conversational, accurate, and
deeply tied to the operating reality of the Unite-Group portfolio.

Operating context
=================
Phill operates 5 businesses under Unite-Group:
- RestoreAssist (restoration / compliance platform)
- Disaster Recovery | NRPG (operations platform + onboarding framework)
- Synthex (marketing-automation platform — used internally + sold to clients)
- CARSI (vertical delivery)
- Unite-Group CRM (the ccw-crm SaaS product, also dogfooded internally)

CCW (Carpet Cleaners Warehouse) — first paying SaaS client of the
`ccw-crm` system Unite-Group built. CCW is an external company running
Shopify + a website; Unite-Group's role is the AI integration into
their newly built CRM-ERP. CCW also uses Synthex for marketing
automation downstream of the CRM-ERP. CCW is a customer, not a
portfolio business. CCW client success is the #1 priority right now,
and CCW is the marquee public marketing case study (logo rights agreed).

Do NOT confuse:
- "CCW the company" → external SaaS customer
- "ccw-crm the codebase" → Unite-Group's SaaS product, of which CCW is
  the first paying instance

Trajectory: strategic buyout in 12-18+ months is a positioning backdrop,
not the current build target.

Your behaviour
==============
1. Be direct and concise. Phill values brevity over hedging.
2. Reference real numbers from the operating context when relevant —
   don't make up figures.
3. When asked something that needs current external knowledge (market
   moves, competitor research, regulatory shifts), DO NOT speculate.
   Instead, emit a research-request sentinel anywhere in your response:

       [RESEARCH topic="<specific search query>" depth="quick"]

   depth="quick" runs deep_research (returns within ~20-60s).
   depth="deep" runs deep_research_max (returns within 5-20min — async,
   results land in the next conversation turn rather than this one).

   The system fires the research, injects the results into your prompt,
   and you produce the final reply on a second pass. So:
     - Use [RESEARCH] sentinels freely when current data matters
     - The user never sees the raw sentinel — it's stripped before send
     - On the second pass, your prompt will include the research output;
       use it directly in your reply instead of re-querying

   Multiple [RESEARCH] sentinels in one draft are fine — they fire in
   parallel.
4. If your research surfaces a finding scoring ≥ 7/10 in materiality
   (competitor strategic move, regulatory change, market shift that
   affects strategy), emit a Board trigger sentinel:

       [BOARD-TRIGGER score=N topic="<short topic>"]
       <insight body, 2-4 sentences>
       [/BOARD-TRIGGER]

   The system parses this and queues a Pi-CEO Board deliberation. Do
   NOT ask Phill's permission first — a senior PA escalates judgment
   calls; Phill reviews the Board minutes after.

5. Acceptable scoring guide:
   - 9-10: existential — competitor acquisition of a top-3 ANZ player,
     regulatory change banning a core product, etc.
   - 7-8: material — competitor major fundraise, pricing-model shift
     in the vertical, new ANZ-relevant compliance regime.
   - 5-6: notable — interesting but routine; mention without trigger.
   - 1-4: minor — answer the question, no trigger.

5b. TRUTH-CHECK CAPABILITY (Grok 4.3, contrarian / red-team voice):
   For any question that genuinely benefits from a different-threshold
   perspective (strategic decisions, claims to verify, devil's advocate
   review, founder making a call where blind spots matter), emit:

       [TRUTH-CHECK topic="<concise question or claim>"]

   The system fires Grok 4.3 with the topic; Grok's reply is injected
   into the Phase-2 prompt and you weave the contrarian view into your
   final reply. Use SPARINGLY — only when divergent perspective adds
   real value. Not for every question; not for chitchat. Multiple
   sentinels fire in parallel.

5c. REALTIME CAPABILITY (Perplexity Sonar Pro, live web data):
   Founder directive: "without real-time data we are 3 months behind".
   Your training cutoff is stale. For ANY question where current
   external data matters — competitor announcements, market moves,
   regulatory changes today, product releases this week, current
   pricing, news today — emit:

       [REALTIME topic="<specific search query, framed as a real query>"]

   The system fires Perplexity Sonar Pro (live web + citations), and the
   findings are injected into Phase-2 so you can produce an answer with
   FRESH data. Use this LIBERALLY — anything that might have changed
   recently is a candidate. Cheap, fast (~3-8s), and the alternative is
   you confidently citing 6-month-old training knowledge as fact, which
   is worse than saying nothing.

   Examples that warrant [REALTIME]:
     - "What did Anthropic announce this week?"
     - "Current Claude API pricing"
     - "Latest Sonar Pro vs sonar-deep-research benchmarks"
     - "Has X competitor raised since their Series B?"
     - "Today's AUD/USD" / "this morning's market open"
   Examples that do NOT need [REALTIME]:
     - Questions about CCW / Unite-Group operating context (you have it)
     - Conversation continuity / personal scheduling
     - Code explanations / pure reasoning

   Multiple [REALTIME] sentinels fire in parallel. Citations from Sonar
   come through to Phase-2 — preserve them inline so Phill can verify.

6. Never use first-person business language ("we / our / my company").
   Refer to "Unite-Group" or "the portfolio". Phill's strict rule.

7. Avoid AI filler words: delve, tapestry, landscape, leverage, robust,
   seamless, elevate. Direct prose only.
"""


def _trim_dict_for_prompt(d: dict[str, Any] | None,
                            *, max_chars: int = 600) -> str:
    if not d:
        return "(none)"
    s = json.dumps(d, indent=2, default=str)
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n... [truncated]"


def build_prompt(*, user_text: str, history: list[MargotTurn],
                  context: dict[str, Any]) -> str:
    """Build the full prompt sent to the LLM."""
    history_block = ""
    if history:
        for turn in history[-DEFAULT_HISTORY_TURNS:]:
            history_block += f"\n[Phill] {turn.user_text}\n"
            history_block += f"[Margot] {turn.margot_text}\n"

    ctx_block = (
        "Operating snapshots\n"
        "===================\n"
        f"CFO (per-business latest):\n{_trim_dict_for_prompt(context.get('cfo'))}\n\n"
        f"CMO:\n{_trim_dict_for_prompt(context.get('cmo'))}\n\n"
        f"CTO:\n{_trim_dict_for_prompt(context.get('cto'))}\n\n"
        f"CS:\n{_trim_dict_for_prompt(context.get('cs'))}\n\n"
        f"Recent Board sessions (last 3):\n"
        f"{_trim_dict_for_prompt(context.get('board_recent'), max_chars=1200)}\n\n"
        f"CCW first-client state:\n{_trim_dict_for_prompt(context.get('ccw'))}\n"
    )

    prompt = (
        f"{_MARGOT_SYSTEM_PROMPT}\n\n"
        f"{ctx_block}\n"
        f"Conversation so far\n"
        f"===================\n"
        f"{history_block.strip() or '(this is the first turn)'}\n\n"
        f"Current message from Phill\n"
        f"==========================\n"
        f"{user_text}\n\n"
        f"Margot's reply (concise, direct, with optional [BOARD-TRIGGER] "
        f"sentinels if material):"
    )
    return prompt


# ── Phase-2 research execution ──────────────────────────────────────────────


async def _run_research_batch(requests: list["ResearchRequest"]
                                ) -> list[dict[str, Any]]:
    """Fire deep_research for each [RESEARCH] sentinel in parallel.

    Returns a list of {topic, depth, status, summary, error} dicts in the
    same order as the input requests. Failures are non-fatal — the
    corresponding entry has error set + summary empty.
    """
    import asyncio  # noqa: PLC0415 — keep heavy imports local

    try:
        from . import margot_tools  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("margot: margot_tools import failed (%s)", exc)
        return [
            {"topic": r.topic, "depth": r.depth, "summary": "",
             "error": f"margot_tools_unavailable: {exc}"}
            for r in requests
        ]

    def _fire(r: "ResearchRequest") -> dict[str, Any]:
        """Sync call wrapped for asyncio.to_thread."""
        try:
            if r.depth == "deep":
                # Async deep_research_max — returns interaction_id only.
                # Result lands on next turn; we surface the dispatch ack.
                out = margot_tools.deep_research_max(
                    topic=r.topic, use_corpus=False,
                )
                if out.get("error"):
                    return {"topic": r.topic, "depth": "deep",
                            "summary": "",
                            "error": out["error"]}
                return {
                    "topic": r.topic, "depth": "deep",
                    "summary": (
                        f"Deep research dispatched (interaction_id="
                        f"{out.get('interaction_id', 'unknown')}); "
                        f"results will land in the next conversation turn."
                    ),
                    "error": None,
                }
            # Default: sync deep_research
            out = margot_tools.deep_research(
                topic=r.topic, use_corpus=False,
            )
            if out.get("error"):
                return {"topic": r.topic, "depth": "quick",
                        "summary": "",
                        "error": out["error"]}
            return {
                "topic": r.topic, "depth": "quick",
                "summary": out.get("summary") or out.get("body") or "",
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            return {"topic": r.topic, "depth": r.depth, "summary": "",
                    "error": f"research_call_raised: {exc}"}

    findings = await asyncio.gather(
        *(asyncio.to_thread(_fire, r) for r in requests),
    )
    return list(findings)


async def _run_truth_check_batch(requests: list["TruthCheckRequest"]
                                   ) -> list[dict[str, Any]]:
    """Fire Grok 4.3 (margot.truth_check role) for each TRUTH-CHECK
    sentinel in parallel. Returns a list of {topic, response, error} dicts.

    Failures are non-fatal — the corresponding entry has error set + an
    empty response. The Phase-2 prompt builder handles missing results.
    """
    import asyncio  # noqa: PLC0415

    try:
        from app.server.provider_router import run_via_provider  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("margot truth-check: provider_router import failed (%s)", exc)
        return [
            {"topic": r.topic, "response": "",
             "error": f"provider_router_unavailable: {exc}"}
            for r in requests
        ]

    async def _fire(r: "TruthCheckRequest") -> dict[str, Any]:
        # Frame the topic for Grok — explicit contrarian / truth-seeker brief.
        prompt = (
            "You are a contrarian / red-team voice. Phill McGurk's chief-of-staff "
            "Margot has flagged the following for a different-threshold "
            "perspective. Your job: surface what other models would soften, "
            "miss, or refuse to say. Be direct, evidence-grounded, and concise "
            "(≤400 words). If the claim is solid, say so plainly — don't "
            "invent disagreement.\n\n"
            f"Topic: {r.topic}\n\n"
            "Contrarian response:"
        )
        try:
            rc, text, _cost, error = await run_via_provider(
                prompt=prompt, role="margot.truth_check",
                timeout_s=60, session_id=f"truth-{r.topic[:30]}",
                thinking="adaptive",
            )
            if rc != 0 or error:
                return {"topic": r.topic, "response": "",
                        "error": error or f"rc={rc}"}
            return {"topic": r.topic, "response": text, "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"topic": r.topic, "response": "",
                    "error": f"truth_check_raised: {exc}"}

    return list(await asyncio.gather(*(_fire(r) for r in requests)))


async def _run_realtime_batch(requests: list["RealtimeRequest"]
                                ) -> list[dict[str, Any]]:
    """Fire Perplexity Sonar (realtime_lookup role) for each REALTIME
    sentinel in parallel — RA-1903.

    Returns a list of {topic, response, citations, error} dicts. Failures
    are non-fatal. Sonar's reply already includes citations inline; we
    surface them in the response field as the model returned them.
    """
    import asyncio  # noqa: PLC0415

    try:
        from app.server.provider_router import run_via_provider  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("margot realtime: provider_router import failed (%s)", exc)
        return [
            {"topic": r.topic, "response": "", "citations": [],
             "error": f"provider_router_unavailable: {exc}"}
            for r in requests
        ]

    async def _fire(r: "RealtimeRequest") -> dict[str, Any]:
        # Sonar Pro is built for direct queries — minimal framing wins.
        prompt = (
            "Search the live web and answer this query. Be concise (≤350 "
            "words), include citations inline (Sonar does this natively), "
            "and prefer recency — the user needs current data, not "
            "training-era knowledge.\n\n"
            f"Query: {r.topic}"
        )
        try:
            rc, text, _cost, error = await run_via_provider(
                prompt=prompt, role="realtime_lookup",
                timeout_s=60, session_id=f"realtime-{r.topic[:30]}",
                thinking="adaptive",
            )
            if rc != 0 or error:
                return {"topic": r.topic, "response": "", "citations": [],
                        "error": error or f"rc={rc}"}
            return {"topic": r.topic, "response": text,
                    "citations": [], "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"topic": r.topic, "response": "", "citations": [],
                    "error": f"realtime_call_raised: {exc}"}

    return list(await asyncio.gather(*(_fire(r) for r in requests)))


def build_prompt_with_research(*, user_text: str,
                                  history: list[MargotTurn],
                                  context: dict[str, Any],
                                  draft: str,
                                  research_findings: list[dict[str, Any]],
                                  truth_check_findings: (
                                      list[dict[str, Any]] | None
                                  ) = None,
                                  realtime_findings: (
                                      list[dict[str, Any]] | None
                                  ) = None,
                                  ) -> str:
    """Construct the Phase-2 prompt — Phase 1 prompt + draft + research +
    optional truth-check findings.

    truth_check_findings is a list of {topic, response, error} dicts from
    _run_truth_check_batch. Pass None or [] when no TRUTH-CHECK sentinels
    were emitted.
    """
    base = build_prompt(user_text=user_text, history=history,
                         context=context)

    findings_block = ""
    for i, f in enumerate(research_findings, start=1):
        findings_block += (
            f"\n--- Research finding {i} "
            f"(topic: {f['topic']!r}, depth: {f.get('depth', 'quick')}) ---\n"
        )
        if f.get("error"):
            findings_block += f"[error: {f['error']}]\n"
        else:
            summary = f.get("summary") or "(empty)"
            # Bound size — research summaries can be huge
            findings_block += (
                summary[:4000] + ("…" if len(summary) > 4000 else "")
            )
            findings_block += "\n"

    truth_block = ""
    for i, f in enumerate(truth_check_findings or [], start=1):
        truth_block += (
            f"\n--- Truth-check (Grok 4.3) finding {i} "
            f"(topic: {f['topic']!r}) ---\n"
        )
        if f.get("error"):
            truth_block += f"[error: {f['error']}]\n"
        else:
            response = f.get("response") or "(empty)"
            truth_block += response[:3000] + ("…" if len(response) > 3000 else "")
            truth_block += "\n"

    realtime_block = ""
    for i, f in enumerate(realtime_findings or [], start=1):
        realtime_block += (
            f"\n--- Realtime (Perplexity Sonar) finding {i} "
            f"(topic: {f['topic']!r}) ---\n"
        )
        if f.get("error"):
            realtime_block += f"[error: {f['error']}]\n"
        else:
            response = f.get("response") or "(empty)"
            realtime_block += response[:3500] + ("…" if len(response) > 3500 else "")
            realtime_block += "\n"

    sections = (
        f"{base}\n\n"
        f"==============================================================\n"
        f"PHASE 2 — research / truth-check / realtime completed. Your Phase 1 draft was:\n"
        f"==============================================================\n\n"
        f"{draft}\n\n"
    )
    if research_findings:
        sections += f"Research findings:\n{findings_block}\n"
    if truth_check_findings:
        sections += (
            f"Truth-check (Grok 4.3 contrarian) findings:\n{truth_block}\n"
        )
    if realtime_findings:
        sections += (
            f"Realtime (Perplexity Sonar — current web) findings:\n{realtime_block}\n"
        )
    sections += (
        "==============================================================\n"
        "Produce the FINAL reply now, integrating the findings above.\n"
        "Do NOT emit [RESEARCH] / [TRUTH-CHECK] / [REALTIME] sentinels in\n"
        "this Phase 2 response — those calls are already done. Preserve\n"
        "any citations from realtime findings inline so Phill can verify.\n"
        "[BOARD-TRIGGER] sentinels are still valid if any finding scores\n"
        "≥7/10 material.\n"
        "=============================================================="
    )
    return sections


# ── Response parsing ────────────────────────────────────────────────────────


_BOARD_TRIGGER_RE = re.compile(
    r"\[BOARD-TRIGGER\s+score\s*=\s*(\d+)\s+topic\s*=\s*\"([^\"]+)\"\]"
    r"\s*([\s\S]*?)\s*\[/BOARD-TRIGGER\]",
    re.MULTILINE,
)

# Order-agnostic sentinel match — RA-1885 fix.
# Captures everything between [TAG and ] and the caller parses attrs.
_RESEARCH_REQUEST_RE = re.compile(
    r"\[RESEARCH(\s+[^\]]*)?\]",
    re.MULTILINE,
)
_TRUTH_CHECK_REQUEST_RE = re.compile(
    r"\[TRUTH-CHECK(\s+[^\]]*)?\]",
    re.MULTILINE,
)
# RA-1903: real-time web data via Perplexity Sonar Pro.
_REALTIME_REQUEST_RE = re.compile(
    r"\[REALTIME(\s+[^\]]*)?\]",
    re.MULTILINE,
)
_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def _parse_attrs(attr_str: str | None) -> dict[str, str]:
    """Parse `key="value" key2="value2"` into dict. Order-agnostic."""
    if not attr_str:
        return {}
    return {m.group(1): m.group(2) for m in _ATTR_RE.finditer(attr_str)}


@dataclass
class ResearchRequest:
    """A [RESEARCH] sentinel parsed out of Margot's draft response."""
    topic: str
    depth: str = "quick"  # "quick" → deep_research; "deep" → deep_research_max


@dataclass
class TruthCheckRequest:
    """A [TRUTH-CHECK] sentinel parsed out of Margot's draft response.

    RA-1886: when Margot wants a contrarian / truth-seeker view (Grok 4.3
    via TAO_MODEL_MARGOT_TRUTH_CHECK), she emits:

        [TRUTH-CHECK topic="<concise question/claim to red-team>"]

    The system fires the truth-check call and injects the response into
    Phase-2 so Margot can weave the contrarian view into her final reply.
    """
    topic: str


@dataclass
class RealtimeRequest:
    """A [REALTIME] sentinel parsed out of Margot's draft response.

    RA-1903: when Margot needs current web data the LLM's training cutoff
    can't see (today's news, market moves, current pricing, competitor
    announcements, regulatory updates), she emits:

        [REALTIME topic="<specific search query>"]

    The system fires Perplexity Sonar Pro via the realtime_lookup role
    (TAO_MODEL_REALTIME_LOOKUP=openrouter:perplexity/sonar-pro) and
    injects the live findings + citations into Phase-2 so Margot's final
    reply uses fresh data instead of stale training knowledge.
    """
    topic: str


def parse_research_requests(response_text: str
                              ) -> tuple[list[ResearchRequest], str]:
    """Extract [RESEARCH] sentinels from Margot's draft response.

    Format (order-agnostic, RA-1885):
        [RESEARCH topic="..." depth="quick"]
        [RESEARCH depth="deep" topic="..."]
        [RESEARCH topic="..."]                  (defaults to quick)

    Returns (requests, cleaned_text). Sentinels stripped from cleaned_text
    so the user-facing reply never shows the raw markup.
    """
    requests: list[ResearchRequest] = []
    for m in _RESEARCH_REQUEST_RE.finditer(response_text):
        attrs = _parse_attrs(m.group(1))
        topic = (attrs.get("topic") or "").strip()
        if not topic:
            continue
        depth = (attrs.get("depth") or "quick").strip().lower()
        if depth not in ("quick", "deep"):
            depth = "quick"
        requests.append(ResearchRequest(topic=topic, depth=depth))
    cleaned = _RESEARCH_REQUEST_RE.sub("", response_text).strip()
    return requests, cleaned


def parse_truth_check_requests(response_text: str
                                  ) -> tuple[list[TruthCheckRequest], str]:
    """Extract [TRUTH-CHECK] sentinels from Margot's draft response.

    Format:
        [TRUTH-CHECK topic="<concise question/claim>"]

    Returns (requests, cleaned_text). Sentinels stripped from cleaned_text.
    """
    requests: list[TruthCheckRequest] = []
    for m in _TRUTH_CHECK_REQUEST_RE.finditer(response_text):
        attrs = _parse_attrs(m.group(1))
        topic = (attrs.get("topic") or "").strip()
        if topic:
            requests.append(TruthCheckRequest(topic=topic))
    cleaned = _TRUTH_CHECK_REQUEST_RE.sub("", response_text).strip()
    return requests, cleaned


def parse_realtime_requests(response_text: str
                              ) -> tuple[list[RealtimeRequest], str]:
    """Extract [REALTIME] sentinels from Margot's draft response — RA-1903.

    Format:
        [REALTIME topic="<specific search query>"]

    Returns (requests, cleaned_text). Sentinels stripped from cleaned_text.
    """
    requests: list[RealtimeRequest] = []
    for m in _REALTIME_REQUEST_RE.finditer(response_text):
        attrs = _parse_attrs(m.group(1))
        topic = (attrs.get("topic") or "").strip()
        if topic:
            requests.append(RealtimeRequest(topic=topic))
    cleaned = _REALTIME_REQUEST_RE.sub("", response_text).strip()
    return requests, cleaned


def parse_board_triggers(response_text: str
                          ) -> tuple[list[BoardTrigger], str]:
    """Extract [BOARD-TRIGGER] sentinels and return (triggers, cleaned_text).

    The cleaned text has the sentinel blocks removed so the user-facing
    Telegram reply doesn't show the raw sentinel syntax.
    """
    triggers: list[BoardTrigger] = []
    for m in _BOARD_TRIGGER_RE.finditer(response_text):
        try:
            score = int(m.group(1))
        except ValueError:
            continue
        triggers.append(BoardTrigger(
            score=max(1, min(10, score)),
            topic=m.group(2).strip(),
            insight=m.group(3).strip(),
        ))
    cleaned = _BOARD_TRIGGER_RE.sub("", response_text).strip()
    return triggers, cleaned


# ── LLM call ────────────────────────────────────────────────────────────────


async def _call_llm(*, prompt: str, timeout_s: int = 120,
                     workspace: str | None = None,
                     turn_id: str = "",
                     role: str = "margot.casual",
                     ) -> tuple[int, str, float, str | None]:
    """Margot's LLM call — routed via provider_router for cost control.

    Default role="margot.casual" → cheap tier (OpenRouter Gemma by
    default). Phase 2 callers pass role="margot.synthesis" → top tier
    (Anthropic Opus) for quality on research integration.

    Falls back to direct Anthropic SDK if provider_router is unavailable.
    """
    import tempfile

    workspace = workspace or tempfile.mkdtemp(prefix="pi-ceo-margot-")

    # Preferred path: provider_router (multi-provider, cost-aware)
    try:
        from app.server.provider_router import run_via_provider  # noqa: PLC0415
        return await run_via_provider(
            prompt=prompt, role=role,
            timeout_s=timeout_s, workspace=workspace,
            session_id=turn_id, thinking="adaptive",
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("margot: provider_router unavailable (%s) — Anthropic fallback",
                  exc)

    # Fallback: direct Anthropic SDK call (Opus, role=orchestrator)
    try:
        from app.server.model_policy import (  # noqa: PLC0415
            select_model, resolve_to_id,
        )
        from app.server.session_sdk import _run_claude_via_sdk  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"sdk_import_failed: {exc}"

    short = select_model("orchestrator")
    model_id = resolve_to_id(short)

    try:
        rc, text, cost = await _run_claude_via_sdk(
            prompt=prompt, model=model_id, workspace=workspace,
            timeout=timeout_s, session_id=turn_id,
            phase="orchestrator", thinking="adaptive",
        )
        return int(rc), text or "", float(cost or 0.0), None
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"sdk_call_raised: {exc}"


# ── Telegram delivery ───────────────────────────────────────────────────────


def _voice_reply_enabled() -> bool:
    return os.environ.get("MARGOT_VOICE_REPLY_ENABLED", "0") == "1"


def _maybe_compose_voice(*, text: str, turn_id: str,
                          repo_root: Path) -> Path | None:
    """Compose a voice variant for Margot's reply when enabled + short enough.

    Returns the audio path or None. Failure is non-fatal — caller falls
    back to text-only.
    """
    if not _voice_reply_enabled():
        return None
    try:
        # Look up via sys.modules first so test monkeypatches via
        # monkeypatch.setitem(sys.modules, "swarm.voice_compose", ...) win
        # over the cached import binding.
        import sys as _sys  # noqa: PLC0415
        voice_compose = _sys.modules.get("swarm.voice_compose")
        if voice_compose is None:
            from . import voice_compose  # noqa: PLC0415
        out_dir = repo_root / ".harness/swarm/voice/margot"
        _, audio_path = voice_compose.compose_margot_voice_reply(
            text, out_dir=out_dir, filename_stem=turn_id,
        )
        return audio_path
    except Exception as exc:  # noqa: BLE001
        log.debug("margot voice: compose suppressed (%s)", exc)
        return None


def _send_telegram(*, chat_id: str, text: str,
                    reply_to_message_id: str | None = None,
                    audio_path: Path | None = None) -> bool:
    """Direct send to Telegram. Uses the existing telegram_alerts helper
    when available; falls back to log-only in test environments.

    When audio_path is provided, the caller's intent is voice + text. The
    underlying telegram_alerts.send signature may or may not support audio
    attachments — this wrapper passes the path as a kwarg and lets the
    sender decide. If the sender doesn't support audio, the text still
    sends (audio is best-effort).
    """
    try:
        from . import telegram_alerts  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("margot: telegram_alerts unavailable (%s) — log only", exc)
        log.info("margot reply (chat=%s, audio=%s): %s",
                 chat_id, audio_path is not None, text[:500])
        return False
    try:
        sender = getattr(telegram_alerts, "send", None)
        if not callable(sender):
            log.info("margot reply (chat=%s, no send fn): %s",
                     chat_id, text[:500])
            return False
        kwargs: dict[str, Any] = {
            "severity": "info", "bot_name": "Margot",
            "chat_id": chat_id,
        }
        if audio_path is not None:
            kwargs["audio_path"] = str(audio_path)
        sender(text, **kwargs)
        return True
    except TypeError:
        # Fallback: sender doesn't accept audio_path / chat_id → call
        # without the optional kwargs.
        try:
            sender(text, severity="info", bot_name="Margot")
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("margot: telegram send fallback failed (%s)", exc)
            return False
    except Exception as exc:  # noqa: BLE001
        log.warning("margot: telegram send failed (%s)", exc)
        return False


# ── Audit ───────────────────────────────────────────────────────────────────


def _audit(type_: str, **fields: Any) -> None:
    try:
        from . import audit_emit  # noqa: PLC0415
        audit_emit.row(type_, "Margot", **fields)
    except Exception as exc:  # noqa: BLE001
        log.debug("margot: audit_emit suppressed (%s): %s", type_, exc)


# ── Public entry point ─────────────────────────────────────────────────────


async def handle_turn(*, chat_id: str, user_text: str,
                       message_id: str | None = None,
                       repo_root: Path | None = None,
                       _send: bool = True) -> MargotTurn:
    """Handle one Margot turn end-to-end.

    1. Loads conversation history + operating context
    2. Builds the prompt + calls the LLM
    3. Parses [BOARD-TRIGGER] sentinels and queues from_margot for each
    4. Sends the cleaned response to Telegram (unless _send=False for tests)
    5. Persists the turn to the conversation jsonl

    Returns the completed MargotTurn (with margot_text + any
    board_session_ids populated).
    """
    rr = repo_root or REPO_ROOT
    started_at = _now_iso()
    turn = MargotTurn(
        chat_id=str(chat_id), user_text=user_text,
        user_message_id=message_id, started_at=started_at,
    )

    history = load_history(str(chat_id), repo_root=rr)
    context = build_context(repo_root=rr)
    prompt = build_prompt(user_text=user_text, history=history,
                           context=context)

    # ── Phase 1: draft response ────────────────────────────────────────
    # role=margot.casual → cheap tier by default (OpenRouter Gemma).
    # If the message is clearly research-needing, the Phase 1 model will
    # emit a [RESEARCH] sentinel; Phase 2 then runs on top tier.
    rc, response_text, cost, error = await _call_llm(
        prompt=prompt, turn_id=turn.turn_id, role="margot.casual",
    )
    turn.cost_usd = cost

    # ── Phase 2: research / truth-check / realtime-on-demand ──────────
    # If Phase 1 contained [RESEARCH], [TRUTH-CHECK], or [REALTIME]
    # sentinels, fire the corresponding calls in parallel, inject results
    # into a follow-up prompt, and call the LLM again. User-facing reply
    # is Phase 2 output.
    if rc == 0 and not error:
        research_requests, after_research = parse_research_requests(response_text)
        truth_requests, after_truth = parse_truth_check_requests(after_research)
        realtime_requests, draft_clean = parse_realtime_requests(after_truth)

        if research_requests or truth_requests or realtime_requests:
            log.info(
                "margot %s: phase 2 — %d research, %d truth-check, %d realtime request(s)",
                turn.turn_id, len(research_requests),
                len(truth_requests), len(realtime_requests),
            )
            turn.research_called = bool(research_requests or realtime_requests)
            # Fire research + truth-check + realtime in parallel
            import asyncio as _aio  # noqa: PLC0415
            research_findings, truth_findings, realtime_findings = await _aio.gather(
                _run_research_batch(research_requests) if research_requests
                else _aio.sleep(0, result=[]),
                _run_truth_check_batch(truth_requests) if truth_requests
                else _aio.sleep(0, result=[]),
                _run_realtime_batch(realtime_requests) if realtime_requests
                else _aio.sleep(0, result=[]),
            )

            phase2_prompt = build_prompt_with_research(
                user_text=user_text, history=history,
                context=context, draft=draft_clean,
                research_findings=research_findings,
                truth_check_findings=truth_findings,
                realtime_findings=realtime_findings,
            )
            # Phase 2 uses role=margot.synthesis → top tier (Anthropic Opus)
            # for quality on integration. Cost is justified — this is the
            # path that produces the user-visible reply when real research
            # or truth-check is in play.
            rc2, response_text2, cost2, error2 = await _call_llm(
                prompt=phase2_prompt, turn_id=f"{turn.turn_id}-p2",
                role="margot.synthesis",
            )
            turn.cost_usd += cost2
            if rc2 == 0 and not error2:
                response_text = response_text2
            else:
                # Phase 2 failure → use the Phase 1 draft (sentinels
                # already stripped). Don't propagate Phase 2's error to
                # the turn — Phase 1 succeeded, so the turn succeeded;
                # the user gets the draft instead of integrated findings,
                # but the conversation continues.
                log.warning("margot %s: phase 2 failed (%s) — using draft",
                            turn.turn_id, error2 or f"rc={rc2}")
                response_text = draft_clean

    turn.ended_at = _now_iso()

    if rc != 0 or error:
        turn.margot_text = "(Margot is unavailable right now.)"
        turn.error = error or f"rc={rc}"
        append_turn(turn, repo_root=rr)
        _audit("margot_turn_failed",
                turn_id=turn.turn_id, chat_id=str(chat_id),
                error=turn.error)
        if _send:
            # No voice on failure — text-only fallback message
            _send_telegram(chat_id=str(chat_id), text=turn.margot_text,
                            reply_to_message_id=message_id)
        return turn

    triggers, cleaned = parse_board_triggers(response_text)
    turn.margot_text = cleaned

    # Optional voice variant (enabled via MARGOT_VOICE_REPLY_ENABLED=1)
    audio_path = _maybe_compose_voice(
        text=cleaned, turn_id=turn.turn_id, repo_root=rr,
    )

    # Queue Board deliberations for any ≥-threshold triggers
    threshold = int(os.environ.get(
        "MARGOT_BOARD_TRIGGER_THRESHOLD",
        DEFAULT_BOARD_TRIGGER_THRESHOLD,
    ))
    for t in triggers:
        if t.score < threshold:
            log.info("margot: trigger score %d < %d — skipped",
                     t.score, threshold)
            continue
        try:
            from .bots import board as board_bot  # noqa: PLC0415
            sid = board_bot.from_margot(
                topic=t.topic, insight=t.insight,
                citations=[],
                repo_root=rr,
            )
            turn.board_session_ids.append(sid)
            log.info("margot: queued Board %s — %s (score %d)",
                     sid, t.topic[:60], t.score)
        except Exception as exc:  # noqa: BLE001
            log.warning("margot: from_margot raised (%s)", exc)

    if _send:
        _send_telegram(
            chat_id=str(chat_id), text=cleaned,
            reply_to_message_id=message_id,
            audio_path=audio_path,
        )

    append_turn(turn, repo_root=rr)
    _audit("margot_turn_complete",
            turn_id=turn.turn_id, chat_id=str(chat_id),
            cost_usd=turn.cost_usd,
            board_triggers=len(turn.board_session_ids),
            voice_attached=audio_path is not None,
            research_called=turn.research_called)
    return turn


__all__ = [
    "MargotTurn", "BoardTrigger", "ResearchRequest", "TruthCheckRequest",
    "RealtimeRequest",
    "handle_turn", "load_history", "append_turn",
    "build_context", "build_prompt", "build_prompt_with_research",
    "parse_board_triggers", "parse_research_requests",
    "parse_truth_check_requests", "parse_realtime_requests",
    "DEFAULT_HISTORY_TURNS", "DEFAULT_BOARD_TRIGGER_THRESHOLD",
]
