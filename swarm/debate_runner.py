"""swarm/debate_runner.py — RA-1867 (Wave 4 B4): Multi-agent debate scaffold.

Runs a drafter agent and an adversarial red-team agent in parallel against
the same topic. Both produce independent artifacts; the caller (typically
CoS) summarises. This breaks LLM sycophancy: the red-team is prompted as a
short-seller / forensic auditor and surfaces blind spots that a drafter
biased toward producing the requested artifact will miss.

Architecture (corrected from initial Wave 4 plan, 2026-05-02):
* Hermes is a separate runtime, NOT a Python pip package, so this module
  is Pi-CEO-native — `asyncio.gather()` over the existing Claude Agent SDK
  wired in ``app/server/session_sdk.py``. No Hermes dependency.
* Both drafter and red-team go through ``model_policy.select_model``, which
  guarantees neither leaks into Opus (Opus is reserved for planner +
  orchestrator only — RA-1099). The `phase=` parameter passed to the SDK
  becomes the role for the policy gate.
* Wall-clock acceptance: drafter + red-team complete in <50% of sequential
  thanks to `asyncio.gather`.

Public API:
* ``run_debate(input)``           — one debate, parallel drafter + red-team
* ``run_debates_parallel(inputs)`` — many debates in flight at once
* ``DebateInput``, ``DebateResult`` dataclasses

Persistence:
* Every debate appends one row to ``.harness/swarm/debate_state.jsonl``
* Every step audit-emits via ``swarm.audit_emit.row``
  (debate_started / debate_drafter_done / debate_redteam_done / debate_aborted)
* Kill-switch (``swarm.kill_switch.is_active()``) is honoured before
  spawning subagents; mid-flight `/panic` cancels in-flight tasks and
  records `debate_aborted`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.debate_runner")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEBATE_STATE_FILE_REL = ".harness/swarm/debate_state.jsonl"

# ── Prompt templates ────────────────────────────────────────────────────────
# Both agents receive the same topic + context. Drafter produces a decisive
# artifact; red-team produces an independent skeptical analysis. Neither sees
# the other's output — the synthesis happens upstream (CoS / 6-pager).
_DRAFTER_TEMPLATE = """You are a senior {role} agent for the {business_id} business.

Topic to address:
{topic}

{context_block}

Produce a clear, decisive draft on the topic. Be specific — name numbers,
dates, owners. Do not hedge. Output the draft only — no preamble, no
explanation of what you're about to do, no closing remarks. The reader is a
busy founder who will react with 👍 or ❌ in Telegram.
"""

_REDTEAM_TEMPLATE = """You are an adversarial red-team analyst — short-seller,
forensic auditor, counter-strategist. You are reviewing the topic below for
the {business_id} business. Your job: find blind spots, weak assumptions,
hidden risks, and the angle a sceptic would attack first.

Topic under review:
{topic}

{context_block}

Output the critique only. Be sharp, specific, and brief. Three to five
bullet points maximum. Do not propose solutions — your role is to expose
flaws so the founder can react with eyes open. No preamble or sign-off.
"""


# ── Data shapes ─────────────────────────────────────────────────────────────


@dataclass
class DebateInput:
    """One debate request."""
    topic: str
    role: str = "drafter"             # senior-agent role label (CFO, CMO, …)
    business_id: str = "portfolio"
    context: str | None = None        # extra grounding for both sides
    timeout_s: int = 180
    workspace: str | None = None      # directory for SDK; tempdir if None
    debate_id: str = field(default_factory=lambda: f"deb-{uuid.uuid4().hex[:10]}")


@dataclass
class _SideResult:
    """One side (drafter or red-team) of a debate."""
    artifact: str = ""
    cost_usd: float = 0.0
    rc: int = 1
    seconds: float = 0.0
    error: str | None = None


@dataclass
class DebateResult:
    """Outcome of one debate."""
    debate_id: str
    topic: str
    role: str
    business_id: str
    drafter: _SideResult
    redteam: _SideResult
    started_at: str
    ended_at: str
    total_cost_usd: float
    aborted: bool = False
    abort_reason: str | None = None

    def both_succeeded(self) -> bool:
        return (self.drafter.rc == 0 and self.redteam.rc == 0
                and not self.aborted)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_prompt(template: str, *, topic: str, role: str, business_id: str,
                  context: str | None) -> str:
    context_block = ""
    if context and context.strip():
        context_block = f"Context:\n{context.strip()}\n"
    return template.format(
        topic=topic.strip(),
        role=role,
        business_id=business_id,
        context_block=context_block,
    )


def _kill_switch_active() -> bool:
    """Best-effort kill-switch check — never raises."""
    try:
        from . import kill_switch  # noqa: PLC0415
        return kill_switch.is_active()
    except Exception as exc:  # noqa: BLE001
        log.debug("debate: kill_switch import suppressed (%s)", exc)
        return False


def _audit(type_: str, **fields: Any) -> None:
    """Best-effort audit emit — never raises."""
    try:
        from . import audit_emit  # noqa: PLC0415
        audit_emit.row(type_, "DebateRunner", **fields)
    except Exception as exc:  # noqa: BLE001
        log.debug("debate: audit_emit suppressed (%s): %s", type_, exc)


def _persist(record: dict[str, Any]) -> None:
    """Append a debate record to the jsonl ledger."""
    p = REPO_ROOT / DEBATE_STATE_FILE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("debate: persist failed (%s): %s",
                    DEBATE_STATE_FILE_REL, exc)


# ── SDK call wrapper ────────────────────────────────────────────────────────


async def _call_one_side(
    *,
    prompt: str,
    side_role: str,         # "drafter" or "redteam" — used as SDK phase
    business_id: str,
    timeout_s: int,
    workspace: str,
    debate_id: str,
) -> _SideResult:
    """Call _run_claude_via_sdk for one side. Wraps errors so the other side
    can still complete. Honours model_policy: opus is rejected by
    assert_model_allowed at the SDK boundary for these non-opus roles.
    """
    t0 = time.monotonic()
    try:
        from app.server.model_policy import (  # noqa: PLC0415
            select_model, resolve_to_id,
        )
        from app.server.session_sdk import _run_claude_via_sdk  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("debate %s %s: SDK import failed (%s)",
                    debate_id, side_role, exc)
        return _SideResult(rc=1, error=f"sdk_import_failed: {exc}",
                           seconds=time.monotonic() - t0)

    short = select_model(side_role)              # "drafter"/"redteam" → sonnet
    model_id = resolve_to_id(short)
    log.debug("debate %s %s: model=%s (short=%s)",
              debate_id, side_role, model_id, short)

    try:
        rc, text, cost = await _run_claude_via_sdk(
            prompt=prompt,
            model=model_id,
            workspace=workspace,
            timeout=timeout_s,
            session_id=debate_id,
            phase=side_role,
            thinking="adaptive",
        )
        return _SideResult(
            artifact=text or "",
            cost_usd=float(cost or 0.0),
            rc=int(rc),
            seconds=time.monotonic() - t0,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("debate %s %s: SDK call raised (%s)",
                    debate_id, side_role, exc)
        return _SideResult(
            rc=1, error=f"sdk_call_raised: {exc}",
            seconds=time.monotonic() - t0,
        )


# ── Public API ──────────────────────────────────────────────────────────────


async def run_debate(inp: DebateInput) -> DebateResult:
    """Run one debate (drafter ∥ red-team) and return both artifacts.

    On kill-switch active at start: returns DebateResult with aborted=True,
    no SDK calls made.
    On kill-switch firing mid-flight: cancels both tasks; partial state
    persisted.
    On one side raising: that side's _SideResult.rc=1, error set; the other
    side completes normally. Caller decides what to do with a half-debate.
    """
    started_at = _now_iso()
    workspace = inp.workspace or tempfile.mkdtemp(prefix="pi-ceo-debate-")

    # Kill-switch gate at start
    if _kill_switch_active():
        log.info("debate %s: kill-switch active at start — skipping",
                 inp.debate_id)
        result = DebateResult(
            debate_id=inp.debate_id,
            topic=inp.topic, role=inp.role, business_id=inp.business_id,
            drafter=_SideResult(error="aborted_kill_switch_pre"),
            redteam=_SideResult(error="aborted_kill_switch_pre"),
            started_at=started_at, ended_at=_now_iso(),
            total_cost_usd=0.0, aborted=True,
            abort_reason="kill_switch_active_at_start",
        )
        _audit("debate_aborted", debate_id=inp.debate_id,
               business_id=inp.business_id, reason="kill_switch_pre")
        _persist(_result_to_record(result))
        return result

    _audit("debate_started", debate_id=inp.debate_id,
           role=inp.role, business_id=inp.business_id, topic=inp.topic[:200])

    drafter_prompt = _build_prompt(
        _DRAFTER_TEMPLATE,
        topic=inp.topic, role=inp.role,
        business_id=inp.business_id, context=inp.context,
    )
    redteam_prompt = _build_prompt(
        _REDTEAM_TEMPLATE,
        topic=inp.topic, role=inp.role,
        business_id=inp.business_id, context=inp.context,
    )

    drafter_task = asyncio.create_task(_call_one_side(
        prompt=drafter_prompt,
        side_role="drafter",
        business_id=inp.business_id,
        timeout_s=inp.timeout_s,
        workspace=workspace,
        debate_id=inp.debate_id,
    ))
    redteam_task = asyncio.create_task(_call_one_side(
        prompt=redteam_prompt,
        side_role="redteam",
        business_id=inp.business_id,
        timeout_s=inp.timeout_s,
        workspace=workspace,
        debate_id=inp.debate_id,
    ))

    # Race the kill-switch against the gather.
    kill_task = asyncio.create_task(_kill_switch_watch())
    gather_task = asyncio.gather(drafter_task, redteam_task,
                                  return_exceptions=False)

    try:
        done, pending = await asyncio.wait(
            [gather_task, kill_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        # Always cancel the watcher if it's still alive.
        kill_task.cancel()
        try:
            await kill_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    if gather_task in done:
        drafter_res, redteam_res = await gather_task
        aborted = False
        abort_reason = None
    else:
        # Kill-switch fired first.
        log.info("debate %s: kill-switch fired mid-debate — cancelling tasks",
                 inp.debate_id)
        drafter_task.cancel()
        redteam_task.cancel()
        try:
            await drafter_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        try:
            await redteam_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        drafter_res = _SideResult(rc=1, error="aborted_kill_switch_mid")
        redteam_res = _SideResult(rc=1, error="aborted_kill_switch_mid")
        aborted = True
        abort_reason = "kill_switch_fired_mid_debate"

    ended_at = _now_iso()

    if drafter_res.rc == 0 and not aborted:
        _audit("debate_drafter_done", debate_id=inp.debate_id,
               business_id=inp.business_id, cost_usd=drafter_res.cost_usd,
               seconds=round(drafter_res.seconds, 2))
    if redteam_res.rc == 0 and not aborted:
        _audit("debate_redteam_done", debate_id=inp.debate_id,
               business_id=inp.business_id, cost_usd=redteam_res.cost_usd,
               seconds=round(redteam_res.seconds, 2))
    if aborted:
        _audit("debate_aborted", debate_id=inp.debate_id,
               business_id=inp.business_id, reason=abort_reason or "unknown")

    result = DebateResult(
        debate_id=inp.debate_id,
        topic=inp.topic, role=inp.role, business_id=inp.business_id,
        drafter=drafter_res, redteam=redteam_res,
        started_at=started_at, ended_at=ended_at,
        total_cost_usd=round(drafter_res.cost_usd + redteam_res.cost_usd, 6),
        aborted=aborted, abort_reason=abort_reason,
    )
    _persist(_result_to_record(result))

    # Surface successful debates on the Hermes Kanban board so the founder
    # can read them without flooding Telegram. Idempotent on debate_id.
    # Failures are non-fatal — the debate result is still returned.
    if result.both_succeeded():
        try:
            from . import kanban_adapter  # noqa: PLC0415
            card_id = kanban_adapter.emit_debate_card(
                role=inp.role,
                business_id=inp.business_id,
                topic=inp.topic,
                drafter_artifact=drafter_res.artifact,
                redteam_artifact=redteam_res.artifact,
                debate_id=inp.debate_id,
            )
            if card_id:
                log.info("debate %s: kanban card %s emitted",
                         inp.debate_id, card_id)
        except Exception as exc:  # noqa: BLE001
            log.debug("debate %s: kanban emit suppressed: %s",
                      inp.debate_id, exc)

    return result


async def _kill_switch_watch(poll_s: float = 1.0) -> None:
    """Wake periodically to check the kill-switch. Returns when active."""
    while True:
        if _kill_switch_active():
            return
        await asyncio.sleep(poll_s)


async def run_debates_parallel(inputs: list[DebateInput]) -> list[DebateResult]:
    """Run many debates in parallel — one per senior-agent topic per cycle.

    Within each debate, drafter ∥ red-team also runs in parallel. So an N-way
    daily-brief assembly fans out to 2N concurrent SDK calls, all bounded by
    each input's ``timeout_s``.
    """
    if not inputs:
        return []
    return await asyncio.gather(*(run_debate(i) for i in inputs))


# ── Persistence helpers ─────────────────────────────────────────────────────


def _result_to_record(r: DebateResult) -> dict[str, Any]:
    rec = asdict(r)
    # Trim long artifacts in the persisted record to keep the jsonl manageable;
    # full artifacts are returned to the caller in-memory.
    for side in ("drafter", "redteam"):
        art = rec[side].get("artifact") or ""
        if len(art) > 4000:
            rec[side]["artifact_full_length"] = len(art)
            rec[side]["artifact"] = art[:4000] + "…[truncated]"
    return rec


def load_recent(*, limit: int = 50) -> list[dict[str, Any]]:
    """Read the last ``limit`` debate records from the jsonl ledger."""
    p = REPO_ROOT / DEBATE_STATE_FILE_REL
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


__all__ = [
    "DebateInput", "DebateResult",
    "run_debate", "run_debates_parallel",
    "load_recent",
]
