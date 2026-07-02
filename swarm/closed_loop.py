"""swarm/closed_loop.py — UNI-2214: compose the autonomous closed loop (spine).

The autonomous primitives already exist as runnable engines under ``swarm/``;
what was missing was the *composition* that chains them into one end-to-end
cycle that pulls its own work, plans, decides, dispatches, gates, and reports
OUT — with a finding written back so the next cycle is richer.

This module is a PURE COMPOSITION. It reuses, in order, engines that already
exist — it reimplements none of them:

  1. INTAKE   swarm.intent_router.classify            (classify a trigger)
  2. PLAN     forward-planner validate_plan.validate  (win condition + moves)
  3. DECIDE   swarm.board.request_deliberation         (queue Board, non-blocking)
  4. DISPATCH swarm.flow_engine.execute_flow           (the call CoS only stubs)
  5. GATE     swarm.draft_review.post_draft            (HITL — live mode only)
  6. REPORT   swarm.six_pager.assemble_six_pager       (the OUT channel)

Then it writes a cycle record to ``.harness/closed_loop/cycles.jsonl`` and
exposes ``recall_recent_cycles`` so a written-back finding is retrievable on the
next cycle (the cost↓/knowledge↑ flywheel, spine-level).

Scope of THIS slice (the spine):
  * The plan is composed deterministically from the intent and gated through the
    forward-planner validator; the LLM-authored 15-move plan is a later slice.
  * The Board request is *queued* (no SDK call / no cost) in the loop by default;
    a later slice (inline Board) can also *process* that queued brief in the same
    cycle — double-gated so it never spends in prod until explicitly enabled.
  * Model-routing sophistication (UNI-2212 slice-2) and the live OUT send are
    deferred; the spine proves the wiring end-to-end in dry-run.

Inline Board deliberation (UNI-2214 slice — live Board SDK inside the loop):
  The DECIDE stage always queues the brief (durable record; the orchestrator's
  separate ``board.process_pending`` step remains a fallback). When *both* gates
  are open it also runs the deliberation inline via ``board.process_session`` so
  the cycle that queued the brief captures its directives in the same pass:
    1. ``not dry_run``  — SHADOW_MODE off (the loop's top-level spend gate); and
    2. ``TAO_CLOSED_LOOP_BOARD_INLINE=1`` — explicit inline opt-in.
  In prod ``SHADOW_MODE=1`` maps to ``dry_run=True``, so the SDK is never called
  and no cost is incurred until an operator flips both gates.

Kill-switch: the orchestrator drain self-gates on ``config.SWARM_ENABLED`` and
``TAO_CLOSED_LOOP_ENABLED``; ``/panic`` halts the whole swarm one cycle up.
"""
from __future__ import annotations

import asyncio
import fcntl
import importlib.util
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.closed_loop")

CYCLES_DIR_REL = ".harness/closed_loop"
CYCLES_FILE = "cycles.jsonl"
TRIGGERS_FILE = "triggers.jsonl"

STAGES = ("intake", "plan", "decide", "dispatch", "gate", "report")


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class StageResult:
    """Outcome of one stage in the cycle."""
    name: str
    status: str                       # "ok" | "skipped" | "error"
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class CycleResult:
    """Outcome of one composed autonomous cycle."""
    cycle_id: str
    trigger: str
    dry_run: bool
    started_at: str
    ended_at: str
    stages: list[StageResult]
    intent: str = "unknown"
    board_session_id: str | None = None
    board_processed_inline: bool = False
    brief_excerpt: str = ""
    written_to: str | None = None

    @property
    def ok(self) -> bool:
        """True when no stage errored (skipped stages are acceptable)."""
        return all(s.status != "error" for s in self.stages)

    def stage(self, name: str) -> StageResult | None:
        for s in self.stages:
            if s.name == name:
                return s
        return None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root(repo_root: Path | None) -> Path:
    return repo_root or Path(__file__).resolve().parents[1]


def _cycles_dir(repo_root: Path) -> Path:
    d = repo_root / CYCLES_DIR_REL
    d.mkdir(parents=True, exist_ok=True)
    return d


_VALIDATE_FN = None


def _load_plan_validator(repo_root: Path):
    """Import the forward-planner validator from its (non-package) script path.

    forward-planner is an LLM-executed skill; its only runnable code is the
    standalone ``validate_plan.py``. We load it by file path rather than
    duplicating its rules here.
    """
    global _VALIDATE_FN
    if _VALIDATE_FN is not None:
        return _VALIDATE_FN
    script = (repo_root / "skills" / "forward-planner" / "scripts"
              / "validate_plan.py")
    if not script.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location(
            "forward_planner_validate_plan", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _VALIDATE_FN = getattr(mod, "validate", None)
    except Exception as exc:  # noqa: BLE001
        log.debug("closed_loop: plan validator unavailable (%s)", exc)
        _VALIDATE_FN = None
    return _VALIDATE_FN


def _extract_topic(intent_payload: dict[str, Any]) -> str:
    fields = intent_payload.get("fields", {})
    return str(
        fields.get("topic")
        or fields.get("title_hint")
        or fields.get("what")
        or fields.get("raw_text")
        or intent_payload.get("raw_message", "")
    )


def _deterministic_plan(intent_payload: dict[str, Any]) -> dict[str, Any]:
    """Minimal, always-valid single-move plan — the safe fallback.

    Shape matches validate_plan.validate's required top-level fields:
    project_id, goal, win_condition, moves[].
    """
    intent = intent_payload.get("intent", "unknown")
    topic = _extract_topic(intent_payload)
    return {
        "project_id": "pi-dev-ops",
        "goal": f"Resolve {intent} intent: {topic[:120]}",
        "win_condition": [
            {
                "id": "wc-1",
                "statement": (
                    "Triggered intent is dispatched, gated, and reported OUT "
                    "with a finding written back for the next cycle."
                ),
            }
        ],
        "moves": [
            {
                "id": "move-1",
                "summary": f"Dispatch the {intent} intent via the existing engines",
                "depends_on": [],
                "satisfies": ["wc-1"],
                "linear": {"project_id": "pi-dev-ops"},
                "verify": "closed-loop cycle completes with all stages ok",
            }
        ],
    }


_PLAN_SYSTEM = (
    "You are the forward-planner for an autonomous software-engineering loop. "
    "Given a triggered intent, output a foresight plan as STRICT JSON only — no "
    "prose, no markdown fences. Schema:\n"
    '{"project_id": "pi-dev-ops", "goal": "<one sentence>", '
    '"win_condition": [{"id": "wc-1", "statement": "<measurable outcome>"}], '
    '"moves": [{"id": "move-1", "summary": "<action>", "depends_on": [], '
    '"satisfies": ["wc-1"], "linear": {"project_id": "pi-dev-ops"}, '
    '"verify": "<how to check this move is done>"}]}\n'
    "Rules: aim for 15 moves (foresight horizon). Every move id is unique; every "
    "depends_on references an EARLIER move id; every satisfies references a real "
    "win_condition id; no dependency cycles. Return only the JSON object."
)


def _parse_plan_json(text: str) -> dict[str, Any] | None:
    """Extract a plan dict from an LLM response; None if unparseable/malformed."""
    s = text.strip()
    if s.startswith("```"):
        # Strip a ```json … ``` fence if the model added one despite instructions.
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        plan = json.loads(s[start:end + 1])
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(plan, dict):
        return None
    if not all(k in plan for k in ("project_id", "goal", "win_condition", "moves")):
        return None
    if not isinstance(plan.get("moves"), list) or not plan["moves"]:
        return None
    return plan


def _llm_plan(intent_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Generate a multi-move plan via the WORKING tier. None on any failure.

    Spends — only ever reached from _build_plan when the loop is live AND
    CLOSED_LOOP_LLM_PLAN is on. Fail-soft: any error returns None so the caller
    falls back to the deterministic plan.
    """
    try:
        from .model_router import Tier, get_client  # noqa: PLC0415
        intent = intent_payload.get("intent", "unknown")
        topic = _extract_topic(intent_payload)
        raw = str(intent_payload.get("raw_message", ""))[:500]
        resp = get_client(Tier.WORKING).complete(
            system=_PLAN_SYSTEM,
            user=f"Intent: {intent}\nTopic/request: {topic[:300]}\nRaw trigger: {raw}",
            max_tokens=1800,
            temperature=0.2,
        )
        return _parse_plan_json(resp.text)
    except Exception as exc:  # noqa: BLE001
        log.warning("closed_loop: LLM plan generation failed (%s); using fallback", exc)
        return None


def _build_plan(
    intent_payload: dict[str, Any],
    *,
    dry_run: bool = True,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Return the plan for this cycle.

    Deterministic by default. An LLM-authored multi-move plan is used only when
    CLOSED_LOOP_LLM_PLAN is on AND the cycle is live (not dry_run) — so it never
    spends in production until explicitly enabled — and only if that plan passes
    the forward-planner validator; otherwise it falls back to deterministic.
    """
    from . import config  # noqa: PLC0415
    deterministic = _deterministic_plan(intent_payload)
    if not (config.CLOSED_LOOP_LLM_PLAN and not dry_run):
        return deterministic
    llm = _llm_plan(intent_payload)
    if llm is None:
        return deterministic
    validate = _load_plan_validator(_repo_root(repo_root))
    if validate is not None:
        errors, _warnings = validate(llm)
        if errors:
            log.warning("closed_loop: LLM plan failed validation (%s); using fallback",
                        errors)
            return deterministic
    return llm


def _dispatch_flow(intent_payload: dict[str, Any]) -> dict[str, Any]:
    """Build the dispatcher-core flow for this cycle.

    The first step re-runs the builtin ``skill.intent-parser`` tool over the
    raw trigger — a real dispatcher-core invocation (this is exactly the call
    ``chief_of_staff._route``'s ``flow`` branch currently only describes in a
    Wave-2 stub).
    """
    raw = intent_payload.get("raw_message", "")
    return {
        "name": "closed-loop-dispatch",
        "tool_allowlist": ["skill.intent-parser"],
        "steps": [
            {
                "id": "reclassify",
                "tool": "skill.intent-parser",
                "args": {"message_text": raw},
            }
        ],
    }


# ── The composed cycle ───────────────────────────────────────────────────────


def run_cycle(
    trigger_text: str,
    *,
    repo_root: Path | None = None,
    dry_run: bool = True,
    chat_id: str | None = None,
) -> CycleResult:
    """Run one composed autonomous cycle over a single trigger.

    Pure composition of existing engines. ``dry_run=True`` (default) never
    spends and never sends: the Board request is queued but not processed, the
    dispatch flow runs in dry-run, the gate is recorded not posted, and the
    6-pager is assembled (file-read only) but not transmitted.
    """
    from . import intent_router, board, flow_engine, six_pager, config

    rr = _repo_root(repo_root)
    cycle_id = f"loop-{uuid.uuid4().hex[:10]}"
    started_at = _now_iso()
    stages: list[StageResult] = []
    board_processed_inline = False

    # 1. INTAKE ───────────────────────────────────────────────────────────────
    intent_payload = intent_router.classify(trigger_text, chat_id=chat_id)
    intent = intent_payload.get("intent", "unknown")
    stages.append(StageResult(
        "intake", "ok",
        {"intent": intent, "confidence": intent_payload.get("confidence", 0.0)},
    ))

    # 2. PLAN ───────────────────────────────────────────────────────────────────
    plan = _build_plan(intent_payload, dry_run=dry_run, repo_root=rr)
    validate = _load_plan_validator(rr)
    if validate is None:
        stages.append(StageResult("plan", "skipped",
                                  {"reason": "validator unavailable"}))
    else:
        errors, warnings = validate(plan)
        stages.append(StageResult(
            "plan", "error" if errors else "ok",
            {"errors": errors, "warnings": warnings,
             "win_condition": plan["win_condition"]},
        ))

    # 3. DECIDE (Board) — always queue the brief (durable; orchestrator's
    # process_pending is the fallback). Double-gated inline processing runs the
    # deliberation in THIS cycle only when the loop is live AND the inline flag
    # is on, so it never spends in prod until both are set (mirrors _build_plan).
    board_session_id: str | None = None
    try:
        brief = board.BoardBrief(
            topic=plan["goal"],
            triggered_by="founder",
            triggering_actor="closed-loop",
            material_input=(
                f"Trigger: {trigger_text[:500]}\n"
                f"Intent: {intent}\n"
                f"Win condition: {plan['win_condition']}"
            ),
            requested_decisions=[f"Prioritise the {intent} move?"],
        )
        board_session_id = board.request_deliberation(brief, repo_root=rr)
        decide_detail: dict[str, Any] = {"board_session_id": board_session_id,
                                         "processed_inline": False}
        if config.CLOSED_LOOP_BOARD_INLINE and not dry_run:
            session = asyncio.run(
                board.process_session(board_session_id, repo_root=rr))
            if session is not None:
                board_processed_inline = True
                decide_detail.update({
                    "processed_inline": True,
                    "board_ok": session.succeeded(),
                    "directive_count": len(session.directives),
                    "hitl_required": session.hitl_required,
                    "cost_usd": session.cost_usd,
                })
        stages.append(StageResult("decide", "ok", decide_detail))
    except Exception as exc:  # noqa: BLE001
        stages.append(StageResult("decide", "error", {"error": repr(exc)}))

    # 4. DISPATCH (dispatcher-core — the call CoS only stubs today) ─────────────
    try:
        flow = _dispatch_flow(intent_payload)
        flow_state = flow_engine.execute_flow(
            flow, context={"cycle_id": cycle_id}, dry_run=dry_run)
        stages.append(StageResult(
            "dispatch",
            "ok" if flow_state.get("status") in ("completed", "running") else "error",
            {"flow_id": flow_state.get("flow_id"),
             "flow_status": flow_state.get("status")},
        ))
    except Exception as exc:  # noqa: BLE001
        stages.append(StageResult("dispatch", "error", {"error": repr(exc)}))

    # 5. GATE (HITL — live mode only; dry-run records intent, never posts) ──────
    if dry_run:
        stages.append(StageResult("gate", "skipped",
                                  {"reason": "dry_run — no HITL post"}))
    else:
        try:
            from . import draft_review
            gate = draft_review.post_draft(
                draft_text=(
                    f"🔁 Closed-loop cycle {cycle_id}\n"
                    f"Intent: {intent}\nGoal: {plan['goal']}"
                ),
                destination_chat_id=str(chat_id or ""),
                drafted_by_role="ClosedLoop",
                originating_intent_id=intent_payload.get("originating_message_id"),
            )
            stages.append(StageResult(
                "gate", "ok" if gate.get("status") != "aborted_pii" else "error",
                {"draft_id": gate.get("draft_id"), "status": gate.get("status")},
            ))
        except Exception as exc:  # noqa: BLE001
            stages.append(StageResult("gate", "error", {"error": repr(exc)}))

    # 6. REPORT OUT (6-pager — assembled file-read; transmitted in live mode) ───
    brief_excerpt = ""
    try:
        brief_text = six_pager.assemble_six_pager(repo_root=rr)
        brief_excerpt = brief_text[:280]
        report_detail: dict[str, Any] = {"brief_chars": len(brief_text)}
        if not dry_run:
            from . import telegram_alerts
            telegram_alerts.send_daily_report(brief_text)
            report_detail["transmitted"] = True
        stages.append(StageResult("report", "ok", report_detail))
    except Exception as exc:  # noqa: BLE001
        stages.append(StageResult("report", "error", {"error": repr(exc)}))

    result = CycleResult(
        cycle_id=cycle_id,
        trigger=trigger_text[:500],
        dry_run=dry_run,
        started_at=started_at,
        ended_at=_now_iso(),
        stages=stages,
        intent=intent,
        board_session_id=board_session_id,
        board_processed_inline=board_processed_inline,
        brief_excerpt=brief_excerpt,
    )

    # Write-back — the cycle record becomes retrievable next cycle (flywheel).
    result.written_to = _write_back(result, repo_root=rr)
    log.info("closed_loop: cycle %s intent=%s ok=%s dry_run=%s",
             cycle_id, intent, result.ok, dry_run)
    return result


# ── Write-back + retrieval (the flywheel) ────────────────────────────────────


def _write_back(result: CycleResult, *, repo_root: Path | None = None) -> str:
    """Append the cycle record to the corpus so it's retrievable next cycle."""
    rr = _repo_root(repo_root)
    path = _cycles_dir(rr) / CYCLES_FILE
    row = asdict(result)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return str(path)


def recall_recent_cycles(*, repo_root: Path | None = None,
                          limit: int = 10) -> list[dict[str, Any]]:
    """Read back the most recent written cycle records (retrieval arm)."""
    rr = _repo_root(repo_root)
    path = rr / CYCLES_DIR_REL / CYCLES_FILE
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out[-max(1, limit):]


# ── Trigger queue + orchestrator drain ───────────────────────────────────────


def enqueue_trigger(trigger_text: str, *,
                    repo_root: Path | None = None,
                    chat_id: str | None = None) -> None:
    """Append a trigger for the orchestrator to drain on its next cycle.

    Intake skills (email-listener / calendar-watcher / CoS ``flow`` branch /
    cron) call this to feed work into the loop without Phill driving.
    """
    rr = _repo_root(repo_root)
    path = _cycles_dir(rr) / TRIGGERS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    row = json.dumps(
        {"trigger": trigger_text, "chat_id": chat_id, "queued_at": _now_iso()},
        ensure_ascii=False,
    ) + "\n"
    with path.open("a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0, os.SEEK_END)
            f.write(row)
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def run_pending_triggers(*, repo_root: Path | None = None,
                         dry_run: bool = True,
                         limit: int = 1) -> list[CycleResult]:
    """Drain up to ``limit`` queued triggers through ``run_cycle``.

    The orchestrator calls this once per cycle. An empty queue is a no-op, so
    wiring this into the live loop carries zero behavioural risk until a
    trigger is explicitly enqueued.
    """
    rr = _repo_root(repo_root)
    path = rr / CYCLES_DIR_REL / TRIGGERS_FILE
    if not path.exists():
        return []

    with path.open("r+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
            if not lines:
                return []

            take, rest = lines[:max(1, limit)], lines[max(1, limit):]
            f.seek(0)
            f.truncate()
            if rest:
                f.write("\n".join(rest) + "\n")
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    results: list[CycleResult] = []
    for line in take:
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        results.append(run_cycle(
            row.get("trigger", ""),
            repo_root=rr,
            dry_run=dry_run,
            chat_id=row.get("chat_id"),
        ))
    return results


__all__ = [
    "StageResult", "CycleResult",
    "run_cycle", "recall_recent_cycles",
    "enqueue_trigger", "run_pending_triggers",
    "STAGES",
]
