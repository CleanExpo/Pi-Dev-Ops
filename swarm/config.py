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
import json
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
# Default: 288 = 24 hours at the default 5-min cycle interval.
# Override with TAO_SWARM_MAX_UNACKED_ITERS env var.
MAX_UNACKED_ITERATIONS: int = int(os.environ.get("TAO_SWARM_MAX_UNACKED_ITERS", "288"))

# Seconds between each bot's observation cycle (default: 5 minutes).
CYCLE_INTERVAL_S: int = int(os.environ.get("TAO_SWARM_CYCLE_S", "300"))

# Board-mandated rate limit: max autonomous PRs the Builder may open per calendar day.
# CONTRARIAN's condition — holds until 20 consecutive green supervised merges logged.
# Override with TAO_SWARM_MAX_DAILY_PRS env var.
MAX_AUTONOMOUS_PRS_PER_DAY: int = int(os.environ.get("TAO_SWARM_MAX_DAILY_PRS", "3"))

# Floor cap that always applies regardless of env override, used by
# `effective_max_daily_prs()` as the auto-clamped value when the
# evaluator-pass-rate gate is not satisfied. RA-3019.
SAFE_FALLBACK_MAX_DAILY_PRS: int = 3

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

# ── Local Ollama triage model (zero API cost) ─────────────────────────────────
# Gemma 4 via Ollama — used for triage, routing, and low-stakes decisions.
# Updated 2026-05-08 on Mac Mini. Use 26b for higher quality, latest for speed.
OLLAMA_TRIAGE_MODEL: str = os.environ.get("OLLAMA_TRIAGE_MODEL", "gemma4:latest")
OLLAMA_TRIAGE_MODEL_HEAVY: str = os.environ.get("OLLAMA_TRIAGE_MODEL_HEAVY", "gemma4:26b")

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


def effective_max_daily_prs() -> int:
    """Return the auto-clamped daily-PR cap. RA-3019.

    Reads `.harness/swarm/green_merge_counter.json`. While
    `consecutive_green < target` (default 20), the cap is auto-clamped to
    `min(env_override, SAFE_FALLBACK_MAX_DAILY_PRS)`. Once the threshold
    is met, the env override applies in full.

    Failure modes are deliberately safe: any I/O or schema error returns
    the clamped value rather than the env override, so a missing or
    corrupt counter file can never *raise* the cap above the floor.
    """
    counter_file = SWARM_LOG_DIR / "green_merge_counter.json"
    try:
        with open(counter_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        consecutive_green = int(data.get("consecutive_green", 0))
        target = int(data.get("target", 20))
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        return min(MAX_AUTONOMOUS_PRS_PER_DAY, SAFE_FALLBACK_MAX_DAILY_PRS)
    if consecutive_green < target:
        return min(MAX_AUTONOMOUS_PRS_PER_DAY, SAFE_FALLBACK_MAX_DAILY_PRS)
    return MAX_AUTONOMOUS_PRS_PER_DAY

# ── Brain-1 wiki ──────────────────────────────────────────────────────────────
# Local directory injected into Margot's context on every turn.
BRAIN1_WIKI_DIR: str = os.environ.get(
    "BRAIN1_WIKI_DIR",
    str(pathlib.Path.home() / "2nd Brain" / "2nd Brain" / "Wiki"),
)

# Gemini File Search store name for use_corpus=True deep_research calls.
# Separate from the local wiki — requires uploading wiki pages to Gemini.
# Consumed by ~/.margot/margot-deep-research/server.py, not by this process.
MARGOT_FILE_SEARCH_STORE: str = os.environ.get("MARGOT_FILE_SEARCH_STORE", "")
