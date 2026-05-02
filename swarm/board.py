"""swarm/board.py — RA-1868 Wave 5: Pi-CEO Board deliberation kernel (Layer 2).

Request-driven module — NOT a per-cycle bot. Three trigger sources:
  1. Senior bot escalation (CMO wants new channel above routine ceiling)
  2. Margot insight (research surfaces material market/competitor signal)
  3. Founder request (Telegram intent: "Pi-CEO, deliberate on X")

When triggered, the Board:
  * Assembles a brief (trigger + senior-bot snapshots + Margot citations)
  * Runs the ``anthropic-skills:ceo-board`` skill (9 personas) via the
    Claude Agent SDK — same path used by ``swarm/debate_runner``.
  * Persists minutes to ``.harness/board-meetings/<date>-<slug>.md``
    (precedent already exists from the recovery snapshot).
  * Emits 0..N Directive objects to
    ``.harness/board/directives/<session_id>.jsonl`` (senior bots tail
    their target_role on next cycle).
  * Optionally raises a HITL flag that surfaces in the daily 6-pager.

Async pattern: persistent-pending queue.
  request_deliberation(brief) → writes pending file, returns session_id
                                immediately (non-blocking).
  process_pending(limit=N)    → orchestrator calls this per cycle; pulls
                                up to N pending sessions, runs each,
                                persists outputs.
  deliberate(brief)           → synchronous all-in-one helper for tests
                                + direct programmatic use.

Public API:
  BoardBrief / Directive / BoardSession dataclasses
  request_deliberation(brief, repo_root) -> str (session_id)
  process_pending(repo_root, limit=1)    -> list[BoardSession]
  deliberate(brief, repo_root)           -> BoardSession  (await; runs full flow)
  get_pending(repo_root)                  -> list[str]
  get_completed(session_id, repo_root)   -> BoardSession | None
  get_directives_for_role(role, repo_root, *, since_session_id=None)
                                          -> list[Directive]
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger("swarm.board")

# Precedent path already exists from recovery snapshot
MEETINGS_DIR_REL = ".harness/board-meetings"
PENDING_DIR_REL = ".harness/board/pending"
SESSIONS_DIR_REL = ".harness/board/sessions"
DIRECTIVES_DIR_REL = ".harness/board/directives"

CEO_BOARD_SKILL_INVOCATION = "anthropic-skills:ceo-board"

DEFAULT_BOARD_TIMEOUT_S = 300

TriggerSource = Literal["senior-bot", "margot", "founder"]


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class BoardBrief:
    """One deliberation request."""
    topic: str
    triggered_by: TriggerSource
    triggering_actor: str               # "CMO", "Margot.market-intel", "founder"
    material_input: str                  # research, snapshots, founder context
    requested_decisions: list[str] = field(default_factory=list)
    timeout_s: int = DEFAULT_BOARD_TIMEOUT_S
    workspace: str | None = None         # tempdir if None
    session_id: str = field(
        default_factory=lambda: f"brd-{uuid.uuid4().hex[:10]}"
    )


@dataclass
class Directive:
    """Structured instruction for a senior bot."""
    target_role: str                     # "CFO" / "CMO" / "CTO" / "CS"
    action: str                          # human-readable + machine-parseable
    rationale: str                       # tied to the persona debate
    deadline: str | None = None          # ISO date or None
    success_criteria: str | None = None
    session_id: str = ""                 # back-reference; populated by parser


@dataclass
class BoardSession:
    """Outcome of one deliberation."""
    session_id: str
    brief: BoardBrief
    deliberation_text: str               # full 9-persona debate output
    minutes_summary: str                 # condensed for the 6-pager
    directives: list[Directive]
    hitl_required: bool                  # True when founder must sign off
    hitl_question: str | None
    started_at: str
    ended_at: str
    cost_usd: float = 0.0
    rc: int = 0
    error: str | None = None

    def succeeded(self) -> bool:
        return self.rc == 0 and not self.error


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(s: str, *, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:max_len].strip("-") or "untitled"


def _ensure_dirs(repo_root: Path) -> None:
    for rel in (MEETINGS_DIR_REL, PENDING_DIR_REL,
                 SESSIONS_DIR_REL, DIRECTIVES_DIR_REL):
        (repo_root / rel).mkdir(parents=True, exist_ok=True)


def _audit(type_: str, **fields: Any) -> None:
    """Best-effort audit emit — never raises."""
    try:
        from . import audit_emit  # noqa: PLC0415
        audit_emit.row(type_, "Board", **fields)
    except Exception as exc:  # noqa: BLE001
        log.debug("board: audit_emit suppressed (%s): %s", type_, exc)


# ── Brief assembly ──────────────────────────────────────────────────────────


_BOARD_PROMPT_TEMPLATE = """You are convening the Pi-CEO Board of Directors.
Use the {skill} skill convention: a 9-persona deliberation (CEO, Revenue,
Product Strategist, Technical Architect, Contrarian, Compounder, Custom
Oracle, Market Strategist, Moonshot).

Topic
-----
{topic}

Triggered by
------------
{triggered_by} ({triggering_actor})

Requested decisions
-------------------
{requested_decisions}

Material input
--------------
{material_input}

Deliberation
------------
Run the 9-persona debate. Each persona contributes one short paragraph.
Surface dissent — the Contrarian and the Moonshot must NOT agree by
default with the CEO.

Then produce a "Minutes summary" (≤200 words, founder-readable).

Then produce a "Directives" block in fenced JSON, with this shape:

```json
{{
  "directives": [
    {{
      "target_role": "CFO" | "CMO" | "CTO" | "CS",
      "action": "<single-sentence imperative>",
      "rationale": "<2-3 sentence why, tied to the debate>",
      "deadline": "<ISO date or null>",
      "success_criteria": "<measurable; or null>"
    }}
  ],
  "hitl_required": true | false,
  "hitl_question": "<one question for the founder, or null>"
}}
```

Output format (in order, no preamble):
1. Deliberation (the 9-persona debate)
2. Minutes summary heading + body
3. Directives JSON in a fenced block
"""


def assemble_brief(brief: BoardBrief) -> str:
    """Render the brief into the prompt the ceo-board skill receives."""
    requested = "\n".join(f"- {d}" for d in brief.requested_decisions) or "(none specified)"
    return _BOARD_PROMPT_TEMPLATE.format(
        skill=CEO_BOARD_SKILL_INVOCATION,
        topic=brief.topic.strip(),
        triggered_by=brief.triggered_by,
        triggering_actor=brief.triggering_actor,
        requested_decisions=requested,
        material_input=brief.material_input.strip(),
    )


# ── Output parsing ──────────────────────────────────────────────────────────


_MINUTES_HEADING = re.compile(
    r"^#+\s*minutes\s+summary\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_DIRECTIVES_FENCE = re.compile(
    r"```json\s*(\{[\s\S]*?\})\s*```",
    re.MULTILINE,
)


def _extract_minutes_summary(text: str) -> str:
    """Pull the 'Minutes summary' block out of the deliberation text.

    Falls back to the first 1000 chars when the heading isn't found —
    better to log a usable summary than fail the session.
    """
    m = _MINUTES_HEADING.search(text)
    if not m:
        return text[:1000].strip()
    body = text[m.end():]
    # Stop at the next markdown heading or the directives fence
    end = body.find("\n#")
    fence = body.find("```")
    cuts = [c for c in (end, fence) if c >= 0]
    if cuts:
        body = body[: min(cuts)]
    return body.strip()[:2000]


def _parse_directives(text: str, *, session_id: str
                       ) -> tuple[list[Directive], bool, str | None]:
    """Find the fenced JSON directives block. Returns (directives, hitl, q)."""
    matches = list(_DIRECTIVES_FENCE.finditer(text))
    if not matches:
        return [], False, None
    # Use the LAST fenced block (the deliberation may quote example JSON
    # earlier; the final block is the actual output)
    raw = matches[-1].group(1)
    try:
        obj = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("board: directives JSON parse failed (%s)", exc)
        return [], False, None

    directives: list[Directive] = []
    for d in obj.get("directives") or []:
        try:
            directives.append(Directive(
                target_role=str(d.get("target_role", "")).strip(),
                action=str(d.get("action", "")).strip(),
                rationale=str(d.get("rationale", "")).strip(),
                deadline=d.get("deadline") or None,
                success_criteria=d.get("success_criteria") or None,
                session_id=session_id,
            ))
        except Exception as exc:  # noqa: BLE001
            log.debug("board: skipping malformed directive (%s)", exc)
            continue

    hitl_required = bool(obj.get("hitl_required") or False)
    hitl_question = obj.get("hitl_question") or None
    return directives, hitl_required, hitl_question


# ── Persistence ──────────────────────────────────────────────────────────────


def _pending_path(repo_root: Path, session_id: str) -> Path:
    return repo_root / PENDING_DIR_REL / f"{session_id}.json"


def _session_path(repo_root: Path, session_id: str) -> Path:
    return repo_root / SESSIONS_DIR_REL / f"{session_id}.json"


def _directives_path(repo_root: Path, session_id: str) -> Path:
    return repo_root / DIRECTIVES_DIR_REL / f"{session_id}.jsonl"


def _minutes_path(repo_root: Path, brief: BoardBrief) -> Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = _slugify(brief.topic)
    return repo_root / MEETINGS_DIR_REL / f"{date}-{slug}.md"


def _persist_pending(repo_root: Path, brief: BoardBrief) -> Path:
    _ensure_dirs(repo_root)
    p = _pending_path(repo_root, brief.session_id)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "brief": asdict(brief),
        "queued_at": _now_iso(),
    }, indent=2) + "\n", encoding="utf-8")
    import os as _os
    _os.replace(tmp, p)
    return p


def _persist_session(repo_root: Path, session: BoardSession) -> Path:
    _ensure_dirs(repo_root)
    p = _session_path(repo_root, session.session_id)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(session), indent=2,
                               default=str) + "\n",
                    encoding="utf-8")
    import os as _os
    _os.replace(tmp, p)
    return p


def _persist_directives(repo_root: Path, session: BoardSession) -> Path | None:
    if not session.directives:
        return None
    _ensure_dirs(repo_root)
    p = _directives_path(repo_root, session.session_id)
    with p.open("w", encoding="utf-8") as f:
        for d in session.directives:
            f.write(json.dumps(asdict(d), ensure_ascii=False) + "\n")
    return p


def _persist_minutes(repo_root: Path, session: BoardSession) -> Path:
    _ensure_dirs(repo_root)
    p = _minutes_path(repo_root, session.brief)
    body = (
        f"# Board minutes — {session.brief.topic}\n\n"
        f"- **Session:** `{session.session_id}`\n"
        f"- **Triggered by:** {session.brief.triggered_by} "
        f"({session.brief.triggering_actor})\n"
        f"- **Started:** {session.started_at}\n"
        f"- **Ended:** {session.ended_at}\n"
        f"- **Cost:** ${session.cost_usd:.4f}\n"
        f"- **Status:** {'OK' if session.succeeded() else 'FAILED'}\n"
        f"- **HITL required:** {session.hitl_required}\n\n"
        f"## Summary\n\n{session.minutes_summary}\n\n"
        f"## Directives ({len(session.directives)})\n\n"
    )
    for d in session.directives:
        body += (
            f"### → {d.target_role}\n"
            f"- **Action:** {d.action}\n"
            f"- **Rationale:** {d.rationale}\n"
            f"- **Deadline:** {d.deadline or 'n/a'}\n"
            f"- **Success criteria:** {d.success_criteria or 'n/a'}\n\n"
        )
    if session.hitl_required:
        body += (
            f"## HITL request\n\n"
            f"{session.hitl_question or '(no question specified)'}\n\n"
        )
    body += "## Full deliberation\n\n"
    body += session.deliberation_text + "\n"
    p.write_text(body, encoding="utf-8")
    return p


# ── SDK call wrapper ────────────────────────────────────────────────────────


async def _call_ceo_board_sdk(*, prompt: str, timeout_s: int,
                                workspace: str, session_id: str
                                ) -> tuple[int, str, float, str | None]:
    """Call _run_claude_via_sdk with the ceo-board skill prompt.

    Returns (rc, text, cost_usd, error_or_None). Never raises — caller
    inspects rc + error.
    """
    try:
        from app.server.model_policy import (  # noqa: PLC0415
            select_model, resolve_to_id,
        )
        from app.server.session_sdk import _run_claude_via_sdk  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"sdk_import_failed: {exc}"

    # Board uses the orchestrator role's model (allowed Opus per RA-1099)
    short = select_model("orchestrator")
    model_id = resolve_to_id(short)

    try:
        rc, text, cost = await _run_claude_via_sdk(
            prompt=prompt,
            model=model_id,
            workspace=workspace,
            timeout=timeout_s,
            session_id=session_id,
            phase="orchestrator",
            thinking="enabled",  # Board deliberation benefits from thinking
        )
        return int(rc), text or "", float(cost or 0.0), None
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"sdk_call_raised: {exc}"


# ── Public API ──────────────────────────────────────────────────────────────


def request_deliberation(brief: BoardBrief, *,
                          repo_root: Path | None = None) -> str:
    """Queue a deliberation request. Non-blocking; returns session_id."""
    rr = repo_root or Path(__file__).resolve().parents[1]
    _persist_pending(rr, brief)
    _audit(
        "board_deliberation_started",
        session_id=brief.session_id,
        topic=brief.topic[:200],
        triggered_by=brief.triggered_by,
        triggering_actor=brief.triggering_actor,
    )
    log.info("board: queued %s — %s", brief.session_id, brief.topic[:80])
    return brief.session_id


async def deliberate(brief: BoardBrief, *,
                      repo_root: Path | None = None) -> BoardSession:
    """Synchronous helper: run the full request → process → persist flow.

    Useful for tests and direct callers; NOT the production path
    (production uses request_deliberation + process_pending).
    """
    rr = repo_root or Path(__file__).resolve().parents[1]
    request_deliberation(brief, repo_root=rr)
    sessions = await _process_one(brief, repo_root=rr)
    return sessions


async def _process_one(brief: BoardBrief, *,
                        repo_root: Path) -> BoardSession:
    """Run one queued brief end-to-end. Internal helper."""
    import tempfile

    workspace = brief.workspace or tempfile.mkdtemp(prefix="pi-ceo-board-")
    started_at = _now_iso()

    prompt = assemble_brief(brief)
    rc, text, cost, error = await _call_ceo_board_sdk(
        prompt=prompt,
        timeout_s=brief.timeout_s,
        workspace=workspace,
        session_id=brief.session_id,
    )
    ended_at = _now_iso()

    if rc != 0 or error:
        session = BoardSession(
            session_id=brief.session_id, brief=brief,
            deliberation_text=text or "",
            minutes_summary=f"Deliberation failed: {error or f'rc={rc}'}",
            directives=[],
            hitl_required=False, hitl_question=None,
            started_at=started_at, ended_at=ended_at,
            cost_usd=cost, rc=rc, error=error,
        )
    else:
        directives, hitl_required, hitl_question = _parse_directives(
            text, session_id=brief.session_id,
        )
        minutes_summary = _extract_minutes_summary(text)
        session = BoardSession(
            session_id=brief.session_id, brief=brief,
            deliberation_text=text,
            minutes_summary=minutes_summary,
            directives=directives,
            hitl_required=hitl_required,
            hitl_question=hitl_question,
            started_at=started_at, ended_at=ended_at,
            cost_usd=cost, rc=0, error=None,
        )

    # Persist outputs
    _persist_session(repo_root, session)
    _persist_minutes(repo_root, session)
    if session.directives:
        _persist_directives(repo_root, session)
        for d in session.directives:
            _audit("board_directive_emitted",
                    session_id=session.session_id,
                    target_role=d.target_role,
                    action=d.action[:200])

    if session.hitl_required:
        _audit("board_hitl_requested",
                session_id=session.session_id,
                question=(session.hitl_question or "")[:200])

    _audit("board_session_complete",
            session_id=session.session_id,
            cost_usd=session.cost_usd,
            directive_count=len(session.directives),
            hitl_required=session.hitl_required,
            success=session.succeeded())

    # Remove the pending file (session is now in sessions/)
    pp = _pending_path(repo_root, brief.session_id)
    if pp.exists():
        try:
            pp.unlink()
        except OSError as exc:
            log.debug("board: pending unlink suppressed (%s)", exc)

    return session


async def process_pending(*, repo_root: Path | None = None,
                           limit: int = 1) -> list[BoardSession]:
    """Pull up to ``limit`` pending sessions and run them. Production path.

    Called by the orchestrator per cycle (separate ticket). Default
    limit=1 keeps the per-cycle latency bounded.
    """
    rr = repo_root or Path(__file__).resolve().parents[1]
    pending_dir = rr / PENDING_DIR_REL
    if not pending_dir.exists():
        return []

    files = sorted(pending_dir.glob("*.json"))[:max(1, limit)]
    out: list[BoardSession] = []
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            brief = BoardBrief(**data["brief"])
        except Exception as exc:  # noqa: BLE001
            log.warning("board: pending %s unreadable (%s)", p.name, exc)
            continue
        try:
            session = await _process_one(brief, repo_root=rr)
            out.append(session)
        except Exception as exc:  # noqa: BLE001
            log.warning("board: process_pending %s raised (%s)",
                        brief.session_id, exc)
    return out


def get_pending(*, repo_root: Path | None = None) -> list[str]:
    """Return session_ids currently queued."""
    rr = repo_root or Path(__file__).resolve().parents[1]
    pending_dir = rr / PENDING_DIR_REL
    if not pending_dir.exists():
        return []
    return sorted(p.stem for p in pending_dir.glob("*.json"))


def get_completed(session_id: str, *,
                   repo_root: Path | None = None
                   ) -> BoardSession | None:
    """Read a completed session from disk."""
    rr = repo_root or Path(__file__).resolve().parents[1]
    p = _session_path(rr, session_id)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        brief = BoardBrief(**data["brief"])
        directives = [Directive(**d) for d in data.get("directives") or []]
        return BoardSession(
            session_id=data["session_id"], brief=brief,
            deliberation_text=data.get("deliberation_text", ""),
            minutes_summary=data.get("minutes_summary", ""),
            directives=directives,
            hitl_required=data.get("hitl_required", False),
            hitl_question=data.get("hitl_question"),
            started_at=data.get("started_at", ""),
            ended_at=data.get("ended_at", ""),
            cost_usd=data.get("cost_usd", 0.0),
            rc=data.get("rc", 0),
            error=data.get("error"),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("board: get_completed %s parse failed (%s)",
                    session_id, exc)
        return None


def get_directives_for_role(role: str, *,
                              repo_root: Path | None = None,
                              limit: int = 50
                              ) -> list[Directive]:
    """Tail directives for one target_role across all completed sessions.

    Senior bot consumers call this on cycle to pick up new directives.
    Returns directives in chronological order (oldest first); caller is
    expected to track which session_ids it has already consumed.
    """
    rr = repo_root or Path(__file__).resolve().parents[1]
    dir_path = rr / DIRECTIVES_DIR_REL
    if not dir_path.exists():
        return []
    out: list[Directive] = []
    for jsonl in sorted(dir_path.glob("*.jsonl")):
        try:
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("target_role") == role:
                    out.append(Directive(**obj))
        except Exception:  # noqa: BLE001
            continue
    return out[-limit:]


__all__ = [
    "BoardBrief", "Directive", "BoardSession",
    "request_deliberation", "process_pending", "deliberate",
    "get_pending", "get_completed", "get_directives_for_role",
    "assemble_brief",
]
