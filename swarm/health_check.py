"""
swarm/health_check.py — RA-650: Pre-flight health check for the swarm.

Run this before starting the orchestrator to confirm all models load
and Telegram alerts can reach the operator.

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
    from .ollama_client import health_check as ollama_health, list_models
    from .telegram_alerts import send

    print("\n── Pi-CEO Swarm Pre-flight Health Check ──────────────────────────")
    print(f"  SWARM_ENABLED  : {config.SWARM_ENABLED}")
    print(f"  SHADOW_MODE    : {config.SHADOW_MODE}")
    print(f"  OLLAMA_URL     : {config.OLLAMA_BASE_URL}")
    print(f"  TELEGRAM       : {'configured' if config.TELEGRAM_BOT_TOKEN else 'NOT SET'}")
    print()

    all_pass = True

    # 1 — Ollama connectivity
    available = list_models()
    if not available:
        print("  ✗  Ollama not reachable at", config.OLLAMA_BASE_URL)
        print("     → Start Ollama: open /Applications/Ollama.app or run: ollama serve")
        all_pass = False
    else:
        print(f"  ✓  Ollama reachable — {len(available)} model(s) available")

    # 2 — Each bot's model
    for bot, model in config.BOT_MODELS.items():
        if model not in available:
            print(f"  ✗  {bot.capitalize()} model NOT found: {model}")
            print(f"     → Pull it: ollama pull {model}")
            all_pass = False
        else:
            ok = ollama_health(model)
            status = "✓" if ok else "✗"
            label  = "responds correctly" if ok else "FAILED health check"
            print(f"  {status}  {bot.capitalize()} ({model}): {label}")
            if not ok:
                all_pass = False

    # 3 — Telegram (non-fatal warning only)
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
