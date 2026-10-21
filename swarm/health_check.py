"""
swarm/health_check.py — RA-650: Pre-flight health check for the swarm.

Run this before starting the orchestrator to confirm Telegram alerts can
reach the operator. The Ollama connectivity and per-bot model probes were
removed with Ollama (founder ruling 21/10/2026).

Usage:
    python -m swarm.health_check          # from Pi-Dev-Ops root
    python swarm/health_check.py          # direct
"""
from __future__ import annotations

import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("swarm.health_check")


def run() -> bool:
    """Execute all pre-flight checks.

    Returns:
        True if all checks pass, False if any critical check fails.
    """
    from . import config
    from .telegram_alerts import send

    print("\n── Pi-CEO Swarm Pre-flight Health Check ──────────────────────────")
    print(f"  SWARM_ENABLED  : {config.SWARM_ENABLED}")
    print(f"  SHADOW_MODE    : {config.SHADOW_MODE}")
    print(f"  TELEGRAM       : {'configured' if config.TELEGRAM_BOT_TOKEN else 'NOT SET'}")
    print()

    all_pass = True

    # 1 — Telegram (non-fatal warning only)
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("  ⚠   Telegram not configured — alerts will be logged only")
        print("      → Set TELEGRAM_BOT_TOKEN and TELEGRAM_ALERT_CHAT_ID in .env.local")
    else:
        ok = send(
            "Pre-flight check: Swarm health check running. If you see this, "
            "Telegram alerts are working correctly. ✓",
            severity="info",
            bot_name="HealthCheck",
        )
        status = "✓" if ok else "✗"
        label  = "test alert sent" if ok else "FAILED to send"
        print(f"  {status}  Telegram: {label}")

    print()
    if all_pass:
        print("  ✅  All checks passed — swarm is ready to start")
        print("      Run: python -m swarm.orchestrator")
    else:
        print("  ❌  One or more checks failed — resolve above before starting the swarm")

    print("──────────────────────────────────────────────────────────────────\n")
    return all_pass


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
