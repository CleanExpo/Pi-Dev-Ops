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

# ── Closed-loop composer (UNI-2214) ───────────────────────────────────────────
# When True, the orchestrator drains the closed-loop trigger queue each cycle
# and runs the composed intake→plan→Board→dispatch→gate→report cycle. Default
# OFF; an empty trigger queue is a no-op even when enabled. Live sends require
# SHADOW_MODE off as well.
CLOSED_LOOP_ENABLED: bool = os.environ.get("TAO_CLOSED_LOOP_ENABLED", "0") == "1"

# UNI-2214 — LLM-authored multi-move plan in the closed loop. Double-gated: the
# LLM plan is generated ONLY when this flag is on AND the cycle is live
# (not dry_run / not SHADOW_MODE), so it never spends in production until both
# are explicitly set. Any generation/validation failure falls back to the
# deterministic single-move plan.
CLOSED_LOOP_LLM_PLAN: bool = os.environ.get("TAO_CLOSED_LOOP_LLM_PLAN", "0") == "1"

# UNI-2214 — live Board SDK inside the loop. Double-gated like CLOSED_LOOP_LLM_PLAN:
# the DECIDE stage processes the queued Board brief inline (SDK spend) ONLY when
# this flag is on AND the cycle is live (not dry_run / not SHADOW_MODE). Default
# OFF, so the loop only *queues* the brief until both are explicitly set; the
# orchestrator's separate board.process_pending step remains the fallback.
CLOSED_LOOP_BOARD_INLINE: bool = os.environ.get("TAO_CLOSED_LOOP_BOARD_INLINE", "0") == "1"

# ── Safety limits ─────────────────────────────────────────────────────────────
# Swarm auto-suspends after this many iterations without human acknowledgement.
# Default: 288 = 24 hours at the default 5-min cycle interval.
# Override with TAO_SWARM_MAX_UNACKED_ITERS env var.
MAX_UNACKED_ITERATIONS: int = int(os.environ.get("TAO_SWARM_MAX_UNACKED_ITERS", "288"))

# Seconds between each bot's observation cycle (default: 5 minutes).
CYCLE_INTERVAL_S: int = int(os.environ.get("TAO_SWARM_CYCLE_S", "300"))

# UNI-2214 item 1 — the Linear team the closed-loop intake producer pulls
# ``agent-ready`` tickets from. Resolved by linear_tools._resolve_team (key,
# name, or UUID all accepted). Override with TAO_INTAKE_LINEAR_TEAM.
INTAKE_LINEAR_TEAM: str = os.environ.get("TAO_INTAKE_LINEAR_TEAM", "Unite-Group")

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
# Qwen 3.5 via Ollama — used for triage, routing, and low-stakes decisions.
# Replaced Gemma 4 on 2026-08-19: Gemma was the slowest option measured and
# was stalling the Telegram intent path. Qwen 3.5 is already this file's
# standard for guardian/scribe/click (BOT_MODELS above), so the local box now
# serves one model family instead of two.
# Requires `ollama pull qwen3.5:latest` (and :32b) on the host running Ollama.
OLLAMA_TRIAGE_MODEL: str = os.environ.get("OLLAMA_TRIAGE_MODEL", "qwen3.5:latest")
OLLAMA_TRIAGE_MODEL_HEAVY: str = os.environ.get("OLLAMA_TRIAGE_MODEL_HEAVY", "qwen3.5:32b")

# Interactive triage calls (Telegram intent classification) must never hold a
# user-facing turn for the full OLLAMA_TIMEOUT_S. Past this budget the caller
# degrades to the regex layer / "unknown" rather than leaving Telegram silent.
#
# Known tradeoff, accepted deliberately: a COLD Ollama model can take 20-40s to
# load (see app/server/triage.py, which sets a 90s budget for exactly that), so
# the first message after an idle period will exceed 15s and answer from the
# regex layer instead. That is the intended bias — a chat turn that answers in
# 15s from regex beats one that answers in 40s from the model, and every
# subsequent message hits a warm model in ~1-3s. Raise this only if you would
# rather the founder wait than get a regex answer. The real fix for cold starts
# is OLLAMA_KEEP_ALIVE below, which stops the model unloading in the first place.
OLLAMA_TRIAGE_TIMEOUT_S: int = int(os.environ.get("OLLAMA_TRIAGE_TIMEOUT_S", "15"))

# How long Ollama holds a model in memory after a request. Ollama's own default
# is 5 minutes, so an assistant that is idle between messages pays a 20-40s
# reload on the next one — which the 15s interactive budget above would turn
# into a silent fall back to regex on the first message every time. Holding the
# model resident removes the cold start instead of budgeting around it.
# Set to "0" to unload immediately, or "-1" to keep loaded indefinitely.
OLLAMA_KEEP_ALIVE: str = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")

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


def _resolve_brain1_wiki_dir() -> str:
    """Locate the vault's Wiki without hardcoding a machine-specific checkout.

    The vault is checked out as ~/2nd-brain on some machines and ~/2nd Brain on
    others. Hardcoding either silently resolves to a non-existent (or near-empty)
    directory on the other, and the miss is invisible: callers just receive no
    context. Probe instead, preferring the first that exists; where only the legacy
    path is present this returns exactly what it always did.
    """
    home = pathlib.Path.home()
    candidates = (
        home / "2nd-brain" / "2nd Brain" / "Wiki",
        home / "2nd Brain" / "2nd Brain" / "Wiki",
    )
    return str(next((c for c in candidates if c.is_dir()), candidates[-1]))


BRAIN1_WIKI_DIR: str = os.environ.get("BRAIN1_WIKI_DIR", _resolve_brain1_wiki_dir())

# Gemini File Search store name for use_corpus=True deep_research calls.
# Separate from the local wiki — requires uploading wiki pages to Gemini.
# Consumed by ~/.margot/margot-deep-research/server.py, not by this process.
MARGOT_FILE_SEARCH_STORE: str = os.environ.get("MARGOT_FILE_SEARCH_STORE", "")

# ── Obsidian (RA-926 runtime) ───────────────────────────────────────────────
# Local REST API plugin on Mac brain host. Filesystem fallback via OBSIDIAN_VAULT.
OBSIDIAN_TOKEN: str = os.environ.get("OBSIDIAN_TOKEN", "")
OBSIDIAN_BASE_URL: str = os.environ.get("OBSIDIAN_URL", "https://127.0.0.1:27124")
OBSIDIAN_VAULT: str = os.environ.get(
    "OBSIDIAN_VAULT",
    str(pathlib.Path.home() / "2nd Brain" / "2nd Brain"),
)

# ── Tailscale remote brain host ───────────────────────────────────────────────
# When workers run off-Mac, set OBSIDIAN_REMOTE_URL to the tailnet REST endpoint.
BRAIN_HOST_TAILNET: str = os.environ.get("BRAIN_HOST_TAILNET", "")
OBSIDIAN_REMOTE_URL: str = os.environ.get("OBSIDIAN_REMOTE_URL", "")
if not OBSIDIAN_REMOTE_URL and BRAIN_HOST_TAILNET:
    OBSIDIAN_REMOTE_URL = f"https://{BRAIN_HOST_TAILNET}:27124"
OBSIDIAN_REMOTE_IP: str = os.environ.get("OBSIDIAN_REMOTE_IP", "")

# ── Analyst runtime (growth-sustainability direction layer) ───────────────────
ANALYST_ENABLED: bool = os.environ.get("TAO_ANALYST_ENABLED", "1") == "1"
