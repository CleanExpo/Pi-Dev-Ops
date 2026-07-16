"""swarm/persistent_goals.py — Ralph-loop substrate for long-running goals.

A persistent goal is a topic the senior bots revisit every N cycles,
accumulating reasoning across runs instead of starting fresh. The pattern
came from Hermes' Persistent Goals feature; this module is the Pi-CEO-
native equivalent — pure-Python, JSONL-backed, no external runtime.

Use cases (Wave 5 candidates):
* CFO long-running goal: "drive runway above 18 months by Q3 2026"
  — every cycle, debate_runner produces an updated draft against the
  prior turn's output, advancing the plan. Resolved when CFO snapshot
  shows runway_months >= 18.
* CMO long-running goal: "diversify channel mix below 70% top-share"
  — runs until the CMO snapshot's top_channel_share falls below 0.70.
* CTO long-running goal: "raise DORA band from medium to high"
  — runs until DORA classifier returns "high" or "elite".

Storage: ``.harness/swarm/goals/<goal_id>.jsonl`` (one file per goal).
Each row is one turn. Index: ``.harness/swarm/goals/_index.json`` maps
goal_id → status.

Public API:
  create_goal(...) -> Goal
  list_goals(status=None) -> list[Goal]
  get_goal(goal_id) -> Goal | None
  advance_goal(goal_id, *, drafter_text, redteam_text) -> GoalTurn
  resolve_goal(goal_id, summary) -> bool
  abort_goal(goal_id, reason) -> bool

A goal's ``resolution_predicate`` is a callable name (looked up by
import string) that receives the current snapshots dict and returns
True/False. Default predicate names are wired below; custom ones can be
registered via ``register_predicate``.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("swarm.persistent_goals")

GOALS_DIR_REL = ".harness/swarm/goals"
INDEX_FILE_NAME = "_index.json"

# Stall circuit-breaker tunables (used as advance_goal defaults, so defined
# here at module top; the detector functions live near the bottom).
DEFAULT_STALL_WINDOW = 3          # consecutive unproductive turns before halting
DEFAULT_STALL_SIMILARITY = 0.82   # mean pairwise Jaccard over the window

GoalStatus = str  # "active" | "resolved" | "aborted"


# ── Data shapes ─────────────────────────────────────────────────────────────


@dataclass
class GoalTurn:
    ts: str
    drafter_text: str
    redteam_text: str


@dataclass
class Goal:
    goal_id: str
    role: str                                # CFO / CMO / CTO / CS / CoS
    business_id: str                         # may be "portfolio"
    topic: str
    cadence_cycles: int                      # advance every N cycles
    resolution_predicate: str | None         # registry key; None = manual
    status: GoalStatus = "active"
    created_at: str = ""
    last_advanced_at: str | None = None
    last_advance_cycle: int = 0
    turns_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _goals_dir(repo_root: Path) -> Path:
    p = repo_root / GOALS_DIR_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.mkdir(exist_ok=True)
    return p


def _index_path(repo_root: Path) -> Path:
    return _goals_dir(repo_root) / INDEX_FILE_NAME


def _load_index(repo_root: Path) -> dict[str, Any]:
    p = _index_path(repo_root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("goals: index unreadable (%s)", exc)
        return {}


def _save_index(repo_root: Path, index: dict[str, Any]) -> None:
    p = _index_path(repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    import os as _os
    _os.replace(tmp, p)


def _goal_file(repo_root: Path, goal_id: str) -> Path:
    return _goals_dir(repo_root) / f"{goal_id}.jsonl"


def _goal_meta_file(repo_root: Path, goal_id: str) -> Path:
    return _goals_dir(repo_root) / f"{goal_id}.meta.json"


def _save_goal_meta(repo_root: Path, goal: Goal) -> None:
    p = _goal_meta_file(repo_root, goal.goal_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(goal), indent=2) + "\n",
                    encoding="utf-8")
    import os as _os
    _os.replace(tmp, p)


def _load_goal_meta(repo_root: Path, goal_id: str) -> Goal | None:
    p = _goal_meta_file(repo_root, goal_id)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return Goal(**data)
    except Exception as exc:  # noqa: BLE001
        log.warning("goals: meta %s unreadable (%s)", goal_id, exc)
        return None


def _audit(type_: str, **fields: Any) -> None:
    try:
        from . import audit_emit  # noqa: PLC0415
        audit_emit.row(type_, "PersistentGoals", **fields)
    except Exception as exc:  # noqa: BLE001
        log.debug("goals: audit_emit suppressed (%s): %s", type_, exc)


# ── Predicate registry ──────────────────────────────────────────────────────


_PREDICATES: dict[str, Callable[[dict[str, Any], Goal], bool]] = {}


def register_predicate(name: str,
                        fn: Callable[[dict[str, Any], Goal], bool]) -> None:
    _PREDICATES[name] = fn


def get_predicate(name: str
                   ) -> Callable[[dict[str, Any], Goal], bool] | None:
    return _PREDICATES.get(name)


def _runway_at_least_18(snapshots: dict[str, Any], goal: Goal) -> bool:
    """CFO predicate: portfolio runway_months >= 18."""
    cfo_rows = snapshots.get("cfo") or []
    runways = [r.get("runway_months") for r in cfo_rows
               if r.get("runway_months") is not None]
    if not runways:
        return False
    target = float(goal.metadata.get("min_runway_months", 18.0))
    return min(runways) >= target


def _channel_top_share_below_70(snapshots: dict[str, Any], goal: Goal) -> bool:
    """CMO predicate: every business top_channel_share < 0.70."""
    cmo_rows = snapshots.get("cmo") or []
    if not cmo_rows:
        return False
    threshold = float(goal.metadata.get("max_top_share", 0.70))
    return all(r.get("top_channel_share", 1.0) < threshold for r in cmo_rows)


def _dora_band_at_least_high(snapshots: dict[str, Any],
                                goal: Goal) -> bool:
    """CTO predicate: every repo DORA band is high or elite."""
    cto_rows = snapshots.get("cto") or []
    if not cto_rows:
        return False
    return all(r.get("dora_band") in ("high", "elite") for r in cto_rows)


register_predicate("cfo.runway_at_least_18", _runway_at_least_18)
register_predicate("cmo.channel_top_share_below_70",
                    _channel_top_share_below_70)
register_predicate("cto.dora_band_at_least_high", _dora_band_at_least_high)


# ── Public API ──────────────────────────────────────────────────────────────


def create_goal(*, role: str, business_id: str, topic: str,
                 cadence_cycles: int = 12,
                 resolution_predicate: str | None = None,
                 metadata: dict[str, Any] | None = None,
                 repo_root: Path | None = None) -> Goal:
    """Create a new persistent goal. Persists meta + indexes immediately."""
    rr = repo_root or Path(__file__).resolve().parents[1]
    goal_id = f"goal-{uuid.uuid4().hex[:10]}"
    goal = Goal(
        goal_id=goal_id, role=role, business_id=business_id, topic=topic,
        cadence_cycles=max(1, int(cadence_cycles)),
        resolution_predicate=resolution_predicate,
        status="active", created_at=_now_iso(),
        metadata=dict(metadata or {}),
    )
    _save_goal_meta(rr, goal)
    index = _load_index(rr)
    index[goal_id] = {"status": "active", "role": role,
                       "topic": topic[:100],
                       "created_at": goal.created_at}
    _save_index(rr, index)
    _audit("goal_created", goal_id=goal_id, role=role,
            business_id=business_id, cadence_cycles=goal.cadence_cycles)
    return goal


def list_goals(*, status: GoalStatus | None = None,
                repo_root: Path | None = None) -> list[Goal]:
    rr = repo_root or Path(__file__).resolve().parents[1]
    index = _load_index(rr)
    out: list[Goal] = []
    for gid in index:
        meta = _load_goal_meta(rr, gid)
        if meta is None:
            continue
        if status is not None and meta.status != status:
            continue
        out.append(meta)
    return sorted(out, key=lambda g: g.created_at)


def get_goal(goal_id: str, *,
              repo_root: Path | None = None) -> Goal | None:
    rr = repo_root or Path(__file__).resolve().parents[1]
    return _load_goal_meta(rr, goal_id)


def advance_goal(goal_id: str, *, drafter_text: str, redteam_text: str,
                  cycle_count: int = 0, auto_abort_on_stall: bool = True,
                  stall_window: int = DEFAULT_STALL_WINDOW,
                  repo_root: Path | None = None) -> GoalTurn | None:
    """Append a new turn to a goal's jsonl ledger and bump counters.

    For a freeform goal (no resolution_predicate — which can never auto-resolve
    via check_resolution), the stall circuit-breaker runs after the turn is
    recorded: `stall_window` consecutive turns naming the same residual aborts
    the goal so the driver stops re-firing an unreachable condition. Predicate-
    backed goals are exempt (they resolve on real state, not on judge prose)."""
    rr = repo_root or Path(__file__).resolve().parents[1]
    goal = _load_goal_meta(rr, goal_id)
    if goal is None:
        return None
    if goal.status != "active":
        log.debug("goals: %s not active (%s) — skipping advance",
                  goal_id, goal.status)
        return None

    turn = GoalTurn(ts=_now_iso(),
                     drafter_text=drafter_text or "",
                     redteam_text=redteam_text or "")
    p = _goal_file(rr, goal_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(turn), ensure_ascii=False) + "\n")

    goal.last_advanced_at = turn.ts
    goal.last_advance_cycle = cycle_count
    goal.turns_count += 1
    _save_goal_meta(rr, goal)

    _audit("goal_advanced", goal_id=goal_id, role=goal.role,
            turns_count=goal.turns_count)

    # Freeform goals can't auto-resolve — guard them against infinite re-fire.
    if auto_abort_on_stall and not goal.resolution_predicate:
        auto_abort_if_stalled(goal_id, window=stall_window, repo_root=rr)
    return turn


def resolve_goal(goal_id: str, summary: str = "",
                  *, repo_root: Path | None = None) -> bool:
    rr = repo_root or Path(__file__).resolve().parents[1]
    goal = _load_goal_meta(rr, goal_id)
    if goal is None:
        return False
    goal.status = "resolved"
    goal.metadata["resolution_summary"] = summary
    goal.metadata["resolved_at"] = _now_iso()
    _save_goal_meta(rr, goal)
    index = _load_index(rr)
    if goal_id in index:
        index[goal_id]["status"] = "resolved"
        _save_index(rr, index)
    _audit("goal_resolved", goal_id=goal_id, role=goal.role,
            turns_count=goal.turns_count)
    return True


def abort_goal(goal_id: str, reason: str = "",
                *, repo_root: Path | None = None) -> bool:
    rr = repo_root or Path(__file__).resolve().parents[1]
    goal = _load_goal_meta(rr, goal_id)
    if goal is None:
        return False
    goal.status = "aborted"
    goal.metadata["abort_reason"] = reason
    goal.metadata["aborted_at"] = _now_iso()
    _save_goal_meta(rr, goal)
    index = _load_index(rr)
    if goal_id in index:
        index[goal_id]["status"] = "aborted"
        _save_index(rr, index)
    _audit("goal_aborted", goal_id=goal_id, role=goal.role,
            reason=reason)
    return True


# ── Resolution check ────────────────────────────────────────────────────────


def check_resolution(goal: Goal, snapshots: dict[str, Any],
                      *, repo_root: Path | None = None) -> bool:
    """Run the goal's resolution_predicate against snapshots. Auto-resolves
    on True. Returns True when the goal was just resolved.
    """
    if goal.status != "active":
        return False
    if not goal.resolution_predicate:
        return False
    pred = get_predicate(goal.resolution_predicate)
    if pred is None:
        log.debug("goals: %s unknown predicate %r",
                  goal.goal_id, goal.resolution_predicate)
        return False
    try:
        ok = bool(pred(snapshots, goal))
    except Exception as exc:  # noqa: BLE001
        log.warning("goals: predicate %s raised (%s)",
                    goal.resolution_predicate, exc)
        return False
    if ok:
        resolve_goal(
            goal.goal_id,
            summary=f"predicate {goal.resolution_predicate} → True",
            repo_root=repo_root,
        )
    return ok


def cycle_due(goal: Goal, current_cycle: int) -> bool:
    """True if this cycle should advance the goal."""
    if goal.status != "active":
        return False
    if goal.last_advance_cycle == 0:
        return True  # never advanced — fire on first opportunity
    elapsed = current_cycle - goal.last_advance_cycle
    return elapsed >= goal.cadence_cycles


def read_recent_turns(goal_id: str, *, limit: int = 5,
                       repo_root: Path | None = None
                       ) -> list[GoalTurn]:
    """Read the last ``limit`` turns from a goal's jsonl ledger."""
    rr = repo_root or Path(__file__).resolve().parents[1]
    p = _goal_file(rr, goal_id)
    if not p.exists():
        return []
    out: list[GoalTurn] = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            out.append(GoalTurn(**row))
        except Exception:
            continue
    return out


# ── Stall / unreachable-condition circuit-breaker ───────────────────────────
# A freeform goal (resolution_predicate=None) never auto-resolves via
# check_resolution, so a Stop-hook/judge loop that re-fires it spins forever
# when the residual is structurally unreachable by a solo agent (a prohibited
# action, an off-machine repo, a time-gated fire, an owner-attestation HITL
# gate). The judge keeps returning "unsatisfied" against an unchanging residual
# and the agent keeps re-emitting slightly reworded state. This detects "no
# state change across N consecutive turns" and lets the driver abort + escalate
# instead of looping. See memory goal-hook-unsatisfiable-loops + skill
# goal-circuit-breaker.

import re as _re

_SIG_TOKEN_RE = _re.compile(r"[a-z]{4,}")
_SIG_STOPWORDS = frozenset((
    "transcript", "evidence", "shows", "condition", "demands", "assistant",
    "message", "final", "however", "remain", "remains", "still", "state",
    "operate", "system", "entire", "unexecuted", "unsatisfied", "unfixed",
    "these", "there", "which", "would", "their", "with", "that", "this",
))


def _verdict_signature(text: str) -> frozenset[str]:
    """Content fingerprint of a judge verdict: significant alpha tokens, minus
    the boilerplate scaffolding every verdict repeats. Two verdicts naming the
    same residual gaps produce near-identical signatures even when reworded."""
    toks = {t for t in _SIG_TOKEN_RE.findall((text or "").lower())
            if t not in _SIG_STOPWORDS}
    return frozenset(toks)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    # An empty signature carries no evidence of a repeated residual — treat it
    # as dissimilar so low-content verdicts never trip a false-positive stall.
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class StallReport:
    stalled: bool
    window: int
    turns_seen: int
    mean_similarity: float
    reason: str


def detect_stall(goal_id: str, *, window: int = DEFAULT_STALL_WINDOW,
                  threshold: float = DEFAULT_STALL_SIMILARITY,
                  repo_root: Path | None = None) -> StallReport:
    """Return a StallReport: True when the last `window` turns name the same
    residual (mean pairwise verdict-signature similarity >= threshold), i.e.
    the loop is re-firing without changing state."""
    turns = read_recent_turns(goal_id, limit=window, repo_root=repo_root)
    if len(turns) < window:
        return StallReport(False, window, len(turns), 0.0,
                            "insufficient turns to judge stall")
    sigs = [_verdict_signature(t.redteam_text or t.drafter_text)
            for t in turns]
    pairs = [(_jaccard(sigs[i], sigs[j]))
             for i in range(len(sigs)) for j in range(i + 1, len(sigs))]
    mean_sim = sum(pairs) / len(pairs) if pairs else 0.0
    stalled = mean_sim >= threshold
    return StallReport(
        stalled, window, len(turns), round(mean_sim, 3),
        (f"{window} consecutive turns naming the same residual "
         f"(mean sim {mean_sim:.2f} >= {threshold})") if stalled
        else f"progressing (mean sim {mean_sim:.2f} < {threshold})")


def auto_abort_if_stalled(goal_id: str, *, window: int = DEFAULT_STALL_WINDOW,
                           threshold: float = DEFAULT_STALL_SIMILARITY,
                           repo_root: Path | None = None) -> StallReport:
    """Abort a goal that has stalled on an unreachable residual. Idempotent:
    a non-active goal returns a non-stalled report. The driver calls this each
    cycle and, on `stalled`, stops re-firing and escalates to the founder
    instead of looping."""
    goal = _load_goal_meta(repo_root or Path(__file__).resolve().parents[1],
                            goal_id)
    if goal is None or goal.status != "active":
        return StallReport(False, window, 0, 0.0, "goal not active")
    rep = detect_stall(goal_id, window=window, threshold=threshold,
                        repo_root=repo_root)
    if rep.stalled:
        abort_goal(goal_id,
                    reason=f"unreachable-condition: {rep.reason}",
                    repo_root=repo_root)
        _audit("goal_stalled_aborted", goal_id=goal_id,
               window=window, mean_similarity=rep.mean_similarity)
    return rep


__all__ = [
    "Goal", "GoalTurn", "StallReport",
    "create_goal", "list_goals", "get_goal",
    "advance_goal", "resolve_goal", "abort_goal",
    "check_resolution", "cycle_due", "read_recent_turns",
    "detect_stall", "auto_abort_if_stalled",
    "register_predicate", "get_predicate",
]
