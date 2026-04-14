"""
swarm/bots/guardian.py — RA-650: Guardian Bot.

Responsibilities:
  - Monitor swarm health (Ollama liveness, bot cycle times, error rates)
  - Enforce the kill-switch (TAO_SWARM_ENABLED) and auto-suspend logic
  - Escalate to Telegram on CRITICAL/HIGH events
  - Log all observations to .harness/swarm/guardian.jsonl

Shadow mode: observes and reports, does NOT take any remediation actions.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import config
from ..ollama_client import chat, health_check, list_models
from ..telegram_alerts import send

log = logging.getLogger("swarm.guardian")


SYSTEM_PROMPT = """You are Guardian — the safety and monitoring bot for the Pi-CEO autonomous swarm.

Your role:
1. Assess swarm health observations and classify issues by severity
2. Identify whether any action is needed or if this is routine
3. Produce a concise structured report

Always respond in JSON with this exact structure:
{
  "severity": "critical|high|medium|info",
  "summary": "one sentence",
  "action_required": true|false,
  "details": "2-3 sentences of analysis"
}"""


def _log_observation(entry: dict) -> None:
    """Append a structured observation to the Guardian JSONL log."""
    log_file = config.SWARM_LOG_DIR / "guardian.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run_cycle(unacked_count: int) -> dict:
    """Execute one Guardian observation cycle.

    Checks:
      1. Ollama service liveness
      2. All required bot models are available
      3. Unacknowledged iteration count vs MAX_UNACKED_ITERATIONS
      4. .harness/ log file recency (builder/scribe activity)

    Args:
        unacked_count: Current count of consecutive unacknowledged iterations.

    Returns:
        Dict with keys: severity, summary, action_required, should_suspend.
    """
    observations: list[str] = []
    critical_flags: list[str] = []
    high_flags: list[str] = []

    # 1 — Ollama liveness
    available_models = list_models()
    if not available_models:
        critical_flags.append("Ollama not responding — swarm LLM backend is DOWN")
    else:
        observations.append(f"Ollama live — {len(available_models)} model(s) available")

    # 2 — Required models present
    for bot, model in config.BOT_MODELS.items():
        if available_models and model not in available_models:
            high_flags.append(f"Model for {bot} bot missing: {model}")
        elif available_models:
            observations.append(f"{bot.capitalize()} model OK: {model}")

    # 3 — Unacknowledged iteration count
    if unacked_count >= config.MAX_UNACKED_ITERATIONS:
        critical_flags.append(
            f"Auto-suspend threshold reached: {unacked_count}/{config.MAX_UNACKED_ITERATIONS} "
            "iterations without human acknowledgement"
        )
    elif unacked_count >= config.MAX_UNACKED_ITERATIONS * 0.7:
        high_flags.append(
            f"Approaching auto-suspend: {unacked_count}/{config.MAX_UNACKED_ITERATIONS} "
            "unacknowledged iterations"
        )

    # 4 — .harness/ recency check (are Pi-CEO logs being written?)
    latest_md = Path(config.SWARM_LOG_DIR).parent / "LATEST.md"
    if latest_md.exists():
        age_s = time.time() - latest_md.stat().st_mtime
        if age_s > 3600:
            high_flags.append(f"Pi-CEO .harness/LATEST.md is {age_s/3600:.1f}h old — pipeline may be stalled")
        else:
            observations.append(f"Pi-CEO logs fresh ({age_s/60:.0f}m ago)")

    # Determine overall severity
    if critical_flags:
        severity = "critical"
        summary_items = critical_flags
    elif high_flags:
        severity = "high"
        summary_items = high_flags
    else:
        severity = "info"
        summary_items = observations[:2]

    obs_text = "\n".join(f"- {o}" for o in observations)
    flag_text = "\n".join(f"- {f}" for f in (critical_flags + high_flags))
    assessment_prompt = (
        f"Swarm cycle observations:\n{obs_text}\n"
        f"{'Issues flagged:\\n' + flag_text if (critical_flags or high_flags) else ''}\n"
        f"Unacknowledged iteration count: {unacked_count}/{config.MAX_UNACKED_ITERATIONS}\n"
        f"Shadow mode: {config.SHADOW_MODE}"
    )

    # Ask Guardian LLM to assess (shadow mode — no action taken)
    llm_response = chat(
        model=config.BOT_MODELS["guardian"],
        system=SYSTEM_PROMPT,
        user_message=assessment_prompt,
        temperature=0.1,
    )

    result: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "summary": "; ".join(summary_items[:2]) or "All systems nominal",
        "action_required": bool(critical_flags or high_flags),
        "should_suspend": unacked_count >= config.MAX_UNACKED_ITERATIONS,
        "unacked_count": unacked_count,
        "shadow_mode": config.SHADOW_MODE,
        "raw_llm": llm_response,
    }

    # Parse LLM structured output (best-effort)
    if llm_response:
        try:
            llm_data = json.loads(llm_response.strip().lstrip("```json").rstrip("```"))
            result["llm_severity"] = llm_data.get("severity", severity)
            result["llm_summary"] = llm_data.get("summary", "")
            result["llm_action"] = llm_data.get("action_required", False)
        except Exception:
            pass

    _log_observation(result)

    # Escalate via Telegram for high/critical
    if severity in ("critical", "high") or result["should_suspend"]:
        send(
            message=(
                f"<b>Guardian Report</b>\n\n"
                f"{result['summary']}\n\n"
                f"{'⛔ AUTO-SUSPEND TRIGGERED' if result['should_suspend'] else ''}"
                f"\nUnacked iterations: {unacked_count}/{config.MAX_UNACKED_ITERATIONS}"
            ),
            severity=severity,
            bot_name="Guardian",
        )

    log.info("Guardian cycle complete: severity=%s unacked=%d suspend=%s",
             severity, unacked_count, result["should_suspend"])
    return result
