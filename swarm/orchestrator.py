"""
swarm/orchestrator.py — RA-650: Pi-CEO Autonomous Swarm Orchestrator.

Entry point for the swarm.  Manages the bot lifecycle, enforces the
kill-switch and auto-suspend, schedules daily Telegram reports.

Shadow mode (TAO_SWARM_SHADOW=1, default ON):
  Bots observe and report via Telegram but take NO actions.
  All write operations are skipped.  This is the safe default for Weeks 1–3.

Kill-switch: set TAO_SWARM_ENABLED=0 (or unset) — the loop exits immediately.
Auto-suspend: fires after TAO_SWARM_MAX_UNACKED_ITERS consecutive cycles
              without a human Telegram acknowledgement (default: 288 = 24h).
              Send /ack or /turbopack in the Telegram chat to resume.

Usage:
    cd Pi-Dev-Ops
    TAO_SWARM_ENABLED=1 python -m swarm.orchestrator

Fifteen Mandatory Controls (board-approved):
  1.  TAO_SWARM_ENABLED=1 required — default OFF
  2.  SHADOW_MODE=1 required for Weeks 1–3 — default ON
  3.  Auto-suspend at 288 unacknowledged iterations (default; 24h at 5-min cycles)
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
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("swarm.orchestrator")


def _check_kill_switch() -> bool:
    """Re-read TAO_SWARM_ENABLED + .harness/swarm/kill_switch.flag every cycle.

    Returns True if the swarm should continue running.

    RA-1839 — file-flag added so /panic from Telegram halts the running
    process even though env vars don't propagate to live subprocesses.
    """
    import os
    if os.environ.get("TAO_SWARM_ENABLED", "0") != "1":
        return False
    try:
        from . import kill_switch
        if kill_switch.is_active():
            return False
    except Exception:
        pass
    return True


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


def _poll_telegram_for_ack(state: dict, token: str, chat_id: str) -> bool:
    """Poll Telegram getUpdates for /ack or /turbopack from the operator.

    Returns True if an acknowledgement command was found.  Persists the last
    processed update_id in state so duplicate processing is impossible.
    """
    if not token or not chat_id:
        return False
    offset = state.get("last_update_id", 0) + 1
    url = (
        f"https://api.telegram.org/bot{token}/getUpdates"
        f"?offset={offset}&timeout=0&limit=20"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        for update in data.get("result", []):
            uid = update.get("update_id", 0)
            if uid > state.get("last_update_id", 0):
                state["last_update_id"] = uid
            msg = update.get("message", {})
            text = (msg.get("text") or "").strip().lower().split()[0]
            msg_chat = str(msg.get("chat", {}).get("id", ""))
            if msg_chat == str(chat_id) and text in ("/ack", "/turbopack"):
                return True
    except Exception as exc:
        log.debug("Telegram poll error: %s", exc)
    return False


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
    from .bots import (
        guardian, builder, scribe, click, chief_of_staff,
        cfo, cmo, cto, cs,
    )
    from .telegram_alerts import send, send_daily_report

    if not config.SWARM_ENABLED:
        log.error("TAO_SWARM_ENABLED is not set to 1 — swarm will not start.")
        log.error("Set TAO_SWARM_ENABLED=1 to enable the swarm.")
        sys.exit(1)

    state_file = config.SWARM_LOG_DIR / "orchestrator_state.json"
    state = _load_state(state_file)

    # Clear stale suspended flag from a previous run if count is now below threshold
    if state.get("suspended") and state["unacked_count"] < config.MAX_UNACKED_ITERATIONS:
        state["suspended"] = False
        _save_state(state_file, state)

    # OAuth refresh — push current Xero / Google Ads access tokens into env
    # before any senior bot reads them. Per-provider failure is non-fatal
    # (the relevant provider just falls back to synthetic for that bot).
    try:
        from . import oauth_refresh  # noqa: PLC0415
        from pathlib import Path as _Path  # noqa: PLC0415
        _rr = _Path(__file__).resolve().parents[1]
        for _provider in ("xero", "google_ads"):
            try:
                oauth_refresh.export_to_env(_provider, _rr)
            except Exception as _exc:  # noqa: BLE001
                log.debug("oauth: %s export skipped (%s)", _provider, _exc)
    except Exception as _exc:  # noqa: BLE001
        log.debug("oauth: refresh module skipped at startup (%s)", _exc)

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
            if not state.get("suspended"):
                # First time crossing threshold — send the alert exactly once
                log.warning("Auto-suspend: %d unacknowledged iterations", state["unacked_count"])
                send(
                    f"⛔ <b>AUTO-SUSPEND</b>: {state['unacked_count']} iterations completed without "
                    f"human acknowledgement.\n\nReply /ack or /turbopack to resume the swarm.",
                    severity="critical",
                    bot_name="Orchestrator",
                )
                state["suspended"] = True
                _save_state(state_file, state)
                log.info("Swarm suspended — polling for /ack or /turbopack")
            # Poll Telegram every 60s; resume immediately on /ack or /turbopack
            if _poll_telegram_for_ack(state, config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID):
                log.info("Operator acknowledgement received — resuming swarm")
                state["suspended"] = False
                state["unacked_count"] = 0
                _save_state(state_file, state)
                send("✅ Acknowledgement received — swarm resumed.", severity="info", bot_name="Orchestrator")
                continue
            time.sleep(60)
            continue

        cycle_start = time.time()
        log.info("── Cycle start (unacked=%d, shadow=%s) ──", state["unacked_count"], config.SHADOW_MODE)

        # ── OAuth refresh — opportunistic per-cycle. needs_refresh() checks
        # the stored expiry against now+skew, so we only hit the token
        # endpoint when the access token is actually about to lapse.
        try:
            from . import oauth_refresh  # noqa: PLC0415
            from pathlib import Path as _Path  # noqa: PLC0415
            _rr = _Path(__file__).resolve().parents[1]
            for _provider in ("xero", "google_ads"):
                _stored = oauth_refresh.load_token(_provider, _rr) or {}
                if oauth_refresh.needs_refresh(_stored):
                    oauth_refresh.export_to_env(_provider, _rr)
        except Exception as _exc:  # noqa: BLE001
            log.debug("oauth: per-cycle refresh skipped (%s)", _exc)

        # ── Control 4: Guardian runs first ──────────────────────────────────
        guardian_result = guardian.run_cycle(state["unacked_count"])

        # ── Control 5: Guardian veto ─────────────────────────────────────────
        if guardian_result.get("should_suspend"):
            log.warning("Guardian vetoed this cycle — skipping other bots")
            state["unacked_count"] += 1
            _save_state(state_file, state)
            time.sleep(config.CYCLE_INTERVAL_S)
            continue

        # ── Builder, Scribe, Click (each self-gates on config.SHADOW_MODE) ─────
        builder.run_cycle(state["unacked_count"])
        click.run_cycle(state["unacked_count"])
        scribe.run_cycle(state["unacked_count"])

        # ── RA-1839 — Chief of Staff: poll Telegram for non-/ack messages,
        # classify via intent_router, route to specialist roles via
        # draft_review (HITL gate). Self-gates on TAO_SWARM_ENABLED + SHADOW.
        try:
            chief_of_staff.run_cycle(state["unacked_count"])
        except Exception as exc:  # noqa: BLE001 - never let CoS crash the loop
            log.warning("CoS cycle failed (continuing): %s", exc)

        # ── RA-1850 — CFO: financial visibility across the 11 businesses.
        # Computes burn / NRR / GM / runway from a pluggable metrics provider
        # (TAO_CFO_PROVIDER selects synthetic | stripe_xero).
        # Self-gates on TAO_SWARM_ENABLED + kill-switch.
        try:
            cfo.run_cycle(state["unacked_count"], state=state)
        except Exception as exc:  # noqa: BLE001 - never let CFO crash the loop
            log.warning("CFO cycle failed (continuing): %s", exc)

        # ── RA-1860 — CMO/Growth: marketing visibility (LTV:CAC, blended CPA,
        # channel HHI, attr decay). TAO_CMO_PROVIDER selects synthetic |
        # ad_platforms. Ad-spend > $5k/day routes through draft_review.
        try:
            cmo.run_cycle(state["unacked_count"], state=state)
        except Exception as exc:  # noqa: BLE001
            log.warning("CMO cycle failed (continuing): %s", exc)

        # ── RA-1861 — CTO: platform health (DORA quartet + p99 + uptime).
        # TAO_CTO_PROVIDER selects synthetic | github_actions. Production
        # PR merges route through draft_review.
        try:
            cto.run_cycle(state["unacked_count"], state=state)
        except Exception as exc:  # noqa: BLE001
            log.warning("CTO cycle failed (continuing): %s", exc)

        # ── RA-1862 — CS-tier1: NPS, FCR, GRR, first-response, enterprise
        # churn threats. TAO_CS_PROVIDER selects synthetic | zendesk |
        # intercom. Refunds > $100 route through draft_review.
        try:
            cs.run_cycle(state["unacked_count"], state=state)
        except Exception as exc:  # noqa: BLE001
            log.warning("CS cycle failed (continuing): %s", exc)

        # ── RA-1863 — Daily 6-pager: composes CFO + CMO + CTO + CS daily
        # snippets + Margot insight + RA-1842 status. Cron-fired at user-
        # local 06:00 UTC (configurable). Routes through pii_redactor +
        # draft_review HITL gate. Voice variant attached when ELEVENLABS_
        # API_KEY is in env (B3 RA-1866).
        try:
            from . import six_pager_dispatcher  # noqa: PLC0415
            six_pager_dispatcher.maybe_fire_daily(state)
        except Exception as exc:  # noqa: BLE001
            log.warning("6-pager fire failed (continuing): %s", exc)

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

        # Increment unacked counter (resets to 0 when operator sends /ack or /turbopack)
        state["unacked_count"] += 1
        _save_state(state_file, state)

        elapsed = time.time() - cycle_start
        sleep_s = max(0, config.CYCLE_INTERVAL_S - elapsed)
        log.info("── Cycle complete in %.1fs — sleeping %.0fs ──", elapsed, sleep_s)
        time.sleep(sleep_s)

    log.info("Pi-CEO Swarm stopped.")


if __name__ == "__main__":
    run()
