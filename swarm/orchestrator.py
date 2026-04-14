"""
swarm/orchestrator.py — RA-650: Pi-CEO Autonomous Swarm Orchestrator.

Entry point for the swarm.  Manages the bot lifecycle, enforces the
kill-switch and auto-suspend, schedules daily Telegram reports.

Shadow mode (TAO_SWARM_SHADOW=1, default ON):
  Bots observe and report via Telegram but take NO actions.
  All write operations are skipped.  This is the safe default for Weeks 1–3.

Kill-switch: set TAO_SWARM_ENABLED=0 (or unset) — the loop exits immediately.
Auto-suspend: fires after TAO_SWARM_MAX_UNACKED_ITERS consecutive cycles
              without a human Telegram acknowledgement (default: 15).

Usage:
    cd Pi-Dev-Ops
    TAO_SWARM_ENABLED=1 python -m swarm.orchestrator

Fifteen Mandatory Controls (board-approved):
  1.  TAO_SWARM_ENABLED=1 required — default OFF
  2.  SHADOW_MODE=1 required for Weeks 1–3 — default ON
  3.  Auto-suspend at 15 unacknowledged iterations
  4.  Guardian cycle runs first every iteration
  5.  Guardian veto can halt remaining bots in an iteration
  6.  All Telegram messages prefixed [AGENT OUTPUT]
  7.  All actions logged to .harness/swarm/ before execution
  8.  No secrets written to logs (PII-filtered)
  9.  No mutations to Pi-Dev-Ops codebase in shadow mode
  10. No network calls to external APIs except Ollama + Telegram
  11. Kill-switch token revocation after auto-suspend fires
  12. Daily 08:00 AEST status report to Telegram
  13. HITL: operator must reply /ack to resume after high/critical event
  14. Max 1 concurrent bot active (sequential execution, no race conditions)
  15. All bot responses stored locally; none forwarded to third-party services
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("swarm.orchestrator")


def _check_kill_switch() -> bool:
    """Re-read TAO_SWARM_ENABLED from environment on every cycle.

    Returns True if the swarm should continue running.
    """
    import os
    return os.environ.get("TAO_SWARM_ENABLED", "0") == "1"


def _load_state(state_file: Path) -> dict:
    """Load persistent orchestrator state (unacked count, last report ts)."""
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception:
            pass
    return {"unacked_count": 0, "last_daily_report": None, "suspended": False}


def _save_state(state_file: Path, state: dict) -> None:
    """Persist orchestrator state atomically."""
    tmp = state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(state_file)


def _should_send_daily_report(last_report_ts: str | None) -> bool:
    """Return True if the daily 08:00 AEST report is due."""
    from . import config
    now_aest = datetime.now(timezone(timedelta(hours=10)))
    target_h, target_m = (int(x) for x in config.DAILY_REPORT_TIME_AEST.split(":"))
    if last_report_ts:
        last_dt = datetime.fromisoformat(last_report_ts)
        if (now_aest - last_dt).total_seconds() < 23 * 3600:
            return False
    return now_aest.hour == target_h and now_aest.minute <= target_m + 5


def run() -> None:
    """Main orchestrator loop — runs until killed or kill-switch fires."""
    from . import config
    from .bots import guardian
    from .telegram_alerts import send, send_daily_report

    if not config.SWARM_ENABLED:
        log.error("TAO_SWARM_ENABLED is not set to 1 — swarm will not start.")
        log.error("Set TAO_SWARM_ENABLED=1 to enable the swarm.")
        sys.exit(1)

    state_file = config.SWARM_LOG_DIR / "orchestrator_state.json"
    state = _load_state(state_file)

    mode_label = "SHADOW MODE" if config.SHADOW_MODE else "ACTIVE MODE"
    log.info("Pi-CEO Swarm starting — %s (unacked=%d)", mode_label, state["unacked_count"])
    send(
        f"Pi-CEO Swarm started in <b>{mode_label}</b>.\n"
        f"Bots: Guardian · Builder · Scribe · Click\n"
        f"Cycle: every {config.CYCLE_INTERVAL_S}s | "
        f"Auto-suspend at {config.MAX_UNACKED_ITERATIONS} unacked iterations",
        severity="info",
        bot_name="Orchestrator",
    )

    # Graceful shutdown on SIGTERM/SIGINT
    _running = [True]
    def _handle_signal(sig, frame):
        log.info("Shutdown signal received — stopping swarm cleanly")
        _running[0] = False
        send("Swarm received shutdown signal — stopping cleanly.", severity="info", bot_name="Orchestrator")
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT,  _handle_signal)

    while _running[0]:
        # Re-read kill-switch every cycle
        if not _check_kill_switch():
            log.info("Kill-switch fired (TAO_SWARM_ENABLED != 1) — stopping")
            send("Kill-switch activated. Swarm stopped.", severity="critical", bot_name="Orchestrator")
            break

        # Check auto-suspend
        if state["unacked_count"] >= config.MAX_UNACKED_ITERATIONS:
            log.warning("Auto-suspend: %d unacknowledged iterations", state["unacked_count"])
            send(
                f"⛔ <b>AUTO-SUSPEND</b>: {state['unacked_count']} iterations completed without "
                f"human acknowledgement.\n\nReply /ack to resume the swarm.",
                severity="critical",
                bot_name="Orchestrator",
            )
            state["suspended"] = True
            _save_state(state_file, state)
            # Wait for /ack (check every 60s) — placeholder until Telegram webhook is wired
            log.info("Swarm suspended — waiting for operator /ack")
            time.sleep(60)
            continue

        cycle_start = time.time()
        log.info("── Cycle start (unacked=%d, shadow=%s) ──", state["unacked_count"], config.SHADOW_MODE)

        # ── Control 4: Guardian runs first ──────────────────────────────────
        guardian_result = guardian.run_cycle(state["unacked_count"])

        # ── Control 5: Guardian veto ─────────────────────────────────────────
        if guardian_result.get("should_suspend"):
            log.warning("Guardian vetoed this cycle — skipping other bots")
            state["unacked_count"] += 1
            _save_state(state_file, state)
            time.sleep(config.CYCLE_INTERVAL_S)
            continue

        # ── Other bots (shadow mode: observe only) ───────────────────────────
        # Builder, Scribe, Click activated in Phase 2 (Week 3+, board sign-off)
        if config.SHADOW_MODE:
            log.info("Shadow mode: Builder/Scribe/Click observing only (no actions)")
        else:
            # Phase 2+ activation (not yet implemented — board sign-off required)
            log.info("Active mode: Builder/Scribe/Click activation pending Phase 2 ticket")

        # ── Daily report ─────────────────────────────────────────────────────
        if _should_send_daily_report(state.get("last_daily_report")):
            report_lines = [
                f"Swarm mode: {mode_label}",
                f"Cycles completed (unacked): {state['unacked_count']}",
                f"Guardian severity this cycle: {guardian_result.get('severity', '?')}",
                f"Ollama models: {len(config.BOT_MODELS)} bots configured",
                f"Kill-switch status: {'ARMED' if config.SWARM_ENABLED else 'TRIGGERED'}",
            ]
            send_daily_report(report_lines)
            state["last_daily_report"] = datetime.now(timezone.utc).isoformat()

        # Increment unacked counter (will reset to 0 when operator sends /ack)
        state["unacked_count"] += 1
        _save_state(state_file, state)

        elapsed = time.time() - cycle_start
        sleep_s = max(0, config.CYCLE_INTERVAL_S - elapsed)
        log.info("── Cycle complete in %.1fs — sleeping %.0fs ──", elapsed, sleep_s)
        time.sleep(sleep_s)

    log.info("Pi-CEO Swarm stopped.")


if __name__ == "__main__":
    run()
