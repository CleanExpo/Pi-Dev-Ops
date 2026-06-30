"""swarm/intake_producers.py — UNI-2214 items 1 & 7.

Additional always-on intake producers that feed the closed-loop trigger queue
(``swarm.closed_loop.enqueue_trigger``) WITHOUT Phill driving. The spine drains
the queue every orchestrator cycle; slice 2 (#401) wired the first producer (the
CoS ``flow`` intent). This adds two more:

  * **cron_heartbeat (item 7 — the scheduler):** once per day, enqueue a
    maintenance self-trigger so the loop runs even with zero human or ticket
    input. The always-on CLOUD host already exists — ``app/server/app_factory``
    runs ``orchestrator.run()`` in the Railway FastAPI process under
    ``TAO_SWARM_ENABLED=1`` (resilient restart, survives the Mac sleeping) — so
    this daily heartbeat is the missing cadence that makes that host
    *self-feeding* rather than waiting on an external trigger.

  * **linear_intake (item 1 — the Linear queue):** pull ``agent-ready`` tickets
    and enqueue each NEW one (deduped by identifier), so scoped work flows into
    the loop without a human handing it over.

Both self-gate on ``config.CLOSED_LOOP_ENABLED`` and time-gate internally
(heartbeat daily, Linear hourly), mirroring ``gap_detector``. enqueue failures
are caught so a producer never crashes the orchestrator cycle.

Wire point: a per-cycle block in ``swarm/orchestrator.py`` (template:
``gap_detector``), placed just before the closed-loop drain so freshly-enqueued
triggers can begin draining the same cycle.

email-listener / calendar-watcher are deliberately NOT producers here: they are
LLM-only specs (SKILL.md, no runnable code) requiring a Composio webhook
substrate that does not yet exist — building them now would be speculative.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger("swarm.intake_producers")

HEARTBEAT_STATE_KEY = "last_intake_heartbeat"
LINEAR_STATE_KEY = "last_intake_linear"
SEEN_IDS_KEY = "intake_seen_ticket_ids"

AGENT_READY_LABEL = "agent-ready"
_SEEN_CAP = 500            # bound the dedup memory carried in orchestrator state
_LINEAR_INTERVAL_S = 3600  # poll Linear at most hourly; heartbeat is daily

_HEARTBEAT_TRIGGER = (
    "Daily autonomous maintenance sweep: review portfolio health, pick up "
    "agent-ready work, and surface anything blocking ship."
)


@dataclass
class IntakeResult:
    """What the producers enqueued this run."""
    enqueued: list[str] = field(default_factory=list)   # trigger texts
    sources: list[str] = field(default_factory=list)    # "heartbeat" | "linear:UNI-123"


# ── Cadence gates (mirror gap_detector.should_run) ───────────────────────────


def _heartbeat_due(state: dict) -> bool:
    """True once per calendar day (UTC)."""
    last = state.get(HEARTBEAT_STATE_KEY)
    if not last:
        return True
    try:
        return date.fromisoformat(str(last)[:10]) < datetime.now(timezone.utc).date()
    except (ValueError, TypeError):
        return True


def _linear_due(state: dict) -> bool:
    """True at most once per ``_LINEAR_INTERVAL_S`` (hourly)."""
    last = state.get(LINEAR_STATE_KEY)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last))
    except (ValueError, TypeError):
        return True
    return (datetime.now(timezone.utc) - last_dt).total_seconds() >= _LINEAR_INTERVAL_S


def should_run(state: dict) -> bool:
    """True when the loop is enabled and at least one producer is due."""
    from . import config  # noqa: PLC0415
    if not config.CLOSED_LOOP_ENABLED:
        return False
    return _heartbeat_due(state) or _linear_due(state)


# ── Linear agent-ready pull (reuses linear_tools' auth/client) ───────────────


def _agent_ready_tickets() -> list[tuple[str, str]]:
    """Return ``(identifier, title)`` for unstarted ``agent-ready`` tickets.

    Reuses ``linear_tools._gql`` (shared LINEAR_API_KEY auth + fail-soft); an
    empty list on any error keeps the producer a safe no-op.
    """
    from . import config, linear_tools  # noqa: PLC0415
    t = linear_tools._resolve_team(config.INTAKE_LINEAR_TEAM)
    if not t:
        return []
    res = linear_tools._gql(
        """
        query($teamId: String!, $label: String!) {
          team(id: $teamId) {
            issues(
              first: 25,
              orderBy: updatedAt,
              filter: {
                labels: { name: { eq: $label } },
                state: { type: { eq: "unstarted" } }
              }
            ) { nodes { identifier title } }
          }
        }
        """,
        {"teamId": t["id"], "label": AGENT_READY_LABEL},
    )
    if "error" in res:
        return []
    nodes = (
        res.get("data", {}).get("team", {}).get("issues", {}).get("nodes", [])
    )
    return [(n["identifier"], n.get("title", "")) for n in nodes if n.get("identifier")]


# ── Enqueue helper (never let a write failure crash the cycle) ───────────────


def _safe_enqueue(trigger_text: str, *, repo_root: Path | None = None) -> bool:
    from . import closed_loop  # noqa: PLC0415
    try:
        closed_loop.enqueue_trigger(trigger_text, repo_root=repo_root)
        return True
    except Exception:  # noqa: BLE001
        log.exception("intake producer: enqueue_trigger failed (continuing)")
        return False


# ── The producer cycle ───────────────────────────────────────────────────────


def run_cycle(state: dict, *, repo_root: Path | None = None) -> IntakeResult:
    """Run the due producers, enqueue new triggers, advance the cadence state.

    Mutates ``state`` in place (the orchestrator persists it). Safe to call every
    cycle: each producer no-ops until its cadence is due, and the whole thing is
    a no-op while ``CLOSED_LOOP_ENABLED`` is off.
    """
    from . import config  # noqa: PLC0415
    result = IntakeResult()
    if not config.CLOSED_LOOP_ENABLED:
        return result

    # 1. cron heartbeat — daily self-trigger (item 7 cadence).
    if _heartbeat_due(state):
        if _safe_enqueue(_HEARTBEAT_TRIGGER, repo_root=repo_root):
            result.enqueued.append(_HEARTBEAT_TRIGGER)
            result.sources.append("heartbeat")
        state[HEARTBEAT_STATE_KEY] = datetime.now(timezone.utc).date().isoformat()

    # 2. Linear agent-ready intake — enqueue each NEW ticket (item 1).
    if _linear_due(state):
        seen_list = list(state.get(SEEN_IDS_KEY, []))
        seen = set(seen_list)
        for ident, title in _agent_ready_tickets():
            if ident in seen:
                continue
            trigger = f"Linear {ident}: {title}".strip()
            if _safe_enqueue(trigger, repo_root=repo_root):
                result.enqueued.append(trigger)
                result.sources.append(f"linear:{ident}")
            # Mark seen regardless of enqueue success so a hard-failing write
            # doesn't spin on the same ticket every hour.
            seen.add(ident)
            seen_list.append(ident)
        state[SEEN_IDS_KEY] = seen_list[-_SEEN_CAP:]
        state[LINEAR_STATE_KEY] = datetime.now(timezone.utc).isoformat()

    return result


__all__ = [
    "IntakeResult", "should_run", "run_cycle",
    "HEARTBEAT_STATE_KEY", "LINEAR_STATE_KEY", "SEEN_IDS_KEY", "AGENT_READY_LABEL",
]
