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


def append_turn(turn: MargotTurn, *, repo_root: Path | None = None) -> Path:
    rr = repo_root or REPO_ROOT
    p = _conversation_path(turn.chat_id, rr)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(turn), ensure_ascii=False) + "\n")
    return p


def load_history(chat_id: str, *,
                  limit: int = DEFAULT_HISTORY_TURNS,
                  repo_root: Path | None = None) -> list[MargotTurn]:
    rr = repo_root or REPO_ROOT
    p = _conversation_path(chat_id, rr)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    out: list[MargotTurn] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            out.append(MargotTurn(**row))
        except Exception:  # noqa: BLE001
            continue
    return out


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
- Synthex (prosumer template platform)
- CARSI (vertical delivery)
- Unite-Group CRM (internal + dogfood)

Plus CCW (Carpet Cleaners Warehouse) — first paying SaaS client of the
ccw-crm system Unite-Group built. Live + paying, marketing-cleared.
CCW client success is the #1 priority right now.

Trajectory: strategic buyout in 12-18+ months is a positioning backdrop,
not the current build target.

Your behaviour
==============
1. Be direct and concise. Phill values brevity over hedging.
2. Reference real numbers from the operating context when relevant —
   don't make up figures.
3. When asked something that needs current external knowledge (market
   moves, competitor research, regulatory shifts), use deep_research
   via the Margot MCP. Don't speculate.
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


# ── Response parsing ────────────────────────────────────────────────────────


_BOARD_TRIGGER_RE = re.compile(
    r"\[BOARD-TRIGGER\s+score\s*=\s*(\d+)\s+topic\s*=\s*\"([^\"]+)\"\]"
    r"\s*([\s\S]*?)\s*\[/BOARD-TRIGGER\]",
    re.MULTILINE,
)


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
                     turn_id: str = "") -> tuple[int, str, float, str | None]:
    """Call Claude via the Agent SDK. Returns (rc, text, cost_usd, error).

    Margot uses the same orchestrator-role model as the Board (Opus-allowed
    per RA-1099). Adaptive thinking for conversational latency.
    """
    import tempfile

    workspace = workspace or tempfile.mkdtemp(prefix="pi-ceo-margot-")
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


def _send_telegram(*, chat_id: str, text: str,
                    reply_to_message_id: str | None = None) -> bool:
    """Direct send to Telegram. Uses the existing telegram_alerts helper
    when available; falls back to log-only in test environments."""
    try:
        from . import telegram_alerts  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("margot: telegram_alerts unavailable (%s) — log only", exc)
        log.info("margot reply (chat=%s): %s", chat_id, text[:500])
        return False
    try:
        # telegram_alerts.send signature varies; degrade safely
        sender = getattr(telegram_alerts, "send", None)
        if not callable(sender):
            log.info("margot reply (chat=%s, no send fn): %s",
                     chat_id, text[:500])
            return False
        sender(text, severity="info", bot_name="Margot",
                chat_id=chat_id)
        return True
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

    rc, response_text, cost, error = await _call_llm(
        prompt=prompt, turn_id=turn.turn_id,
    )
    turn.cost_usd = cost
    turn.ended_at = _now_iso()

    if rc != 0 or error:
        turn.margot_text = "(Margot is unavailable right now.)"
        turn.error = error or f"rc={rc}"
        append_turn(turn, repo_root=rr)
        _audit("margot_turn_failed",
                turn_id=turn.turn_id, chat_id=str(chat_id),
                error=turn.error)
        if _send:
            _send_telegram(chat_id=str(chat_id), text=turn.margot_text,
                            reply_to_message_id=message_id)
        return turn

    triggers, cleaned = parse_board_triggers(response_text)
    turn.margot_text = cleaned

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
        _send_telegram(chat_id=str(chat_id), text=cleaned,
                        reply_to_message_id=message_id)

    append_turn(turn, repo_root=rr)
    _audit("margot_turn_complete",
            turn_id=turn.turn_id, chat_id=str(chat_id),
            cost_usd=cost,
            board_triggers=len(turn.board_session_ids))
    return turn


__all__ = [
    "MargotTurn", "BoardTrigger",
    "handle_turn", "load_history", "append_turn",
    "build_context", "build_prompt", "parse_board_triggers",
    "DEFAULT_HISTORY_TURNS", "DEFAULT_BOARD_TRIGGER_THRESHOLD",
]
