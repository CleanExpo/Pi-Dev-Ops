"""
swarm/config.py — RA-650: Autonomous AI Swarm configuration.

All behaviour is controlled by environment variables.  The swarm never
starts unless TAO_SWARM_ENABLED=1 is explicitly set.  Every other
setting has a safe default.

Kill-switch: set TAO_SWARM_ENABLED=0 (or unset) to halt the entire swarm.
Auto-suspend fires after TAO_SWARM_MAX_UNACKED_ITERS consecutive iterations
complete without a human Telegram acknowledgement.
"""
from __future__ import annotations
import os

# ── Master kill-switch ────────────────────────────────────────────────────────
# Must be explicitly set to "1" to enable the swarm.  Default is OFF.
SWARM_ENABLED: bool = os.environ.get("TAO_SWARM_ENABLED", "0") == "1"

# ── Shadow mode ───────────────────────────────────────────────────────────────
# When True, bots observe and report but take no actions (Weeks 1–3).
# Set TAO_SWARM_SHADOW=0 only after board sign-off on Phase 2 activation.
SHADOW_MODE: bool = os.environ.get("TAO_SWARM_SHADOW", "1") == "1"

# ── Safety limits ─────────────────────────────────────────────────────────────
# Swarm auto-suspends after this many iterations without human acknowledgement.
MAX_UNACKED_ITERATIONS: int = int(os.environ.get("TAO_SWARM_MAX_UNACKED_ITERS", "15"))

# Seconds between each bot's observation cycle (default: 5 minutes).
CYCLE_INTERVAL_S: int = int(os.environ.get("TAO_SWARM_CYCLE_S", "300"))

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT_S: int = int(os.environ.get("OLLAMA_TIMEOUT_S", "120"))

# Bot → model assignments (board-approved, hardware-validated for 24GB M4)
BOT_MODELS: dict[str, str] = {
    "guardian": os.environ.get("TAO_GUARDIAN_MODEL", "qwen3.5:latest"),
    "builder":  os.environ.get("TAO_BUILDER_MODEL",  "qwen2.5-coder:7b-instruct"),
    "scribe":   os.environ.get("TAO_SCRIBE_MODEL",   "qwen3.5:latest"),
    "click":    os.environ.get("TAO_CLICK_MODEL",    "qwen3.5:latest"),
}

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str  = os.environ.get("TELEGRAM_BOT_TOKEN",   "")
TELEGRAM_CHAT_ID: str    = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")

# Daily status report time (HH:MM AEST = UTC+10)
DAILY_REPORT_TIME_AEST: str = os.environ.get("TAO_SWARM_DAILY_REPORT", "08:00")

# ── Pi-Dev-Ops integration ────────────────────────────────────────────────────
PIDEVOPS_BASE_URL: str = os.environ.get("PIDEVOPS_URL", "http://localhost:7777")
PIDEVOPS_PASSWORD: str = os.environ.get("TAO_PASSWORD", "")

# ── Logging ───────────────────────────────────────────────────────────────────
import pathlib
_ROOT = pathlib.Path(__file__).resolve().parents[1]
SWARM_LOG_DIR = pathlib.Path(os.environ.get("TAO_SWARM_LOG_DIR",
                             str(_ROOT / ".harness" / "swarm")))
SWARM_LOG_DIR.mkdir(parents=True, exist_ok=True)

LESSONS_FILE = str(_ROOT / ".harness" / "lessons.jsonl")
