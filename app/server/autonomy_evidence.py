"""Observed poll/launch metrics and non-mutating generation admission."""
import logging
from collections import Counter

# Named for the operational stream an operator greps, not for this module, so the
# admission drop lands beside the rest of the poller's output (cf. the same
# convention in conversation_redaction.py).
log = logging.getLogger("pi-ceo.autonomy")


def calc_effective_autonomy(events: list[dict]) -> dict:
    """A successful launch is not proof of delivery; absent evidence stays null."""
    counts = Counter(event.get("action") for event in events)
    polls, poll_errors = counts["poll"], counts["poll_error"]
    started, errors, blocked = (counts[key] for key in
                               ("session_started", "session_error", "session_blocked"))
    found = sum(event.get("found", 0) for event in events if event.get("action") == "poll")
    total_polls, total_sessions = polls + poll_errors, started + errors + blocked
    poll_rate = polls / total_polls if total_polls else None
    session_rate = started / total_sessions if total_sessions else None
    pickup_rate = started / found if found else None
    effective = (round(poll_rate * session_rate * 100, 1)
                 if poll_rate is not None and session_rate is not None else None)
    return {
        "effective_autonomy_pct": effective, "metric_scope": "poll_and_launch_only",
        "poll_success_rate_pct": round(poll_rate * 100, 1) if poll_rate is not None else None,
        "session_success_rate_pct": round(session_rate * 100, 1) if session_rate is not None else None,
        "pickup_rate_pct": round(pickup_rate * 100, 1) if pickup_rate is not None else None,
        "sessions_started": started, "session_errors": errors, "sessions_blocked": blocked,
        "transition_errors": counts["transition_error"], "issues_found_window": found,
        "window_size": len(events),
    }


def generation_blocked(identifier: str, emit) -> bool:
    """Known host blockers stop admission before any issue is claimed."""
    from .session_sdk import generation_readiness

    generation = generation_readiness()
    if generation["status"] != "blocked":
        return False
    # `emit` reaches only the JSONL event log and an in-memory ring, so without
    # this line a dropped ticket is indistinguishable from a quiet healthy poll
    # in the deployment logs -- the condition that hid UNI-2742 for four sessions.
    log.warning("Autonomy: %s dropped at admission - generation blocked: %s",
                identifier, "; ".join(generation["blockers"]))
    emit({"action": "session_blocked", "ticket": identifier,
          "blockers": generation["blockers"]})
    return True
