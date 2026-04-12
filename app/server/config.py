import os
import secrets
import hashlib
import logging
import json
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env files before reading any os.environ values.
# override=True ensures variables in the file beat whatever the shell has set —
# specifically, the `claude` CLI sets ANTHROPIC_API_KEY="" in the parent shell
# env as a security measure, so child processes (this server) would inherit an
# empty string. Loading from the file with override=True fixes that permanently,
# regardless of how the server was launched.
# ---------------------------------------------------------------------------
_root = Path(__file__).resolve().parents[2]  # Pi-Dev-Ops/
load_dotenv(_root / ".env", override=True)
load_dotenv(_root / ".env.local", override=True)  # local overrides win

# ---------------------------------------------------------------------------
# Structured JSON logging — replaces all print() calls
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "ts":      self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        })

def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(handler)

_setup_logging()
log = logging.getLogger("pi-ceo.config")

# ---------------------------------------------------------------------------
# Password — bcrypt-ready.  If TAO_PASSWORD not set, auto-generate and print.
# The stored value is the raw password; auth.py handles hashing.
# ---------------------------------------------------------------------------

_raw_password = os.environ.get("TAO_PASSWORD", "")
_password_from_env = bool(_raw_password)  # True = user explicitly set it

if not _raw_password:
    _raw_password = secrets.token_urlsafe(24)
    log.info("Generated one-time password: %s  (set TAO_PASSWORD to persist)", _raw_password)

# ---------------------------------------------------------------------------
# Data directory — must be defined before any path references below
# ---------------------------------------------------------------------------

_DATA_DIR = Path(os.path.dirname(__file__)).parent / "data"
_DATA_DIR.mkdir(exist_ok=True)

# Password hash resolution:
#   1. TAO_PASSWORD explicitly set → hash it fresh with bcrypt so env var
#      changes take effect immediately on redeploy.
#   2. No TAO_PASSWORD but persisted hash file → use it (container restart).
#   3. Neither → SHA-256 of auto-generated password (upgrades to bcrypt on
#      first successful login via auth.py).
HASH_FILE = _DATA_DIR / ".password-hash"

if _password_from_env:
    import bcrypt as _bcrypt
    PASSWORD_HASH = _bcrypt.hashpw(_raw_password.encode(), _bcrypt.gensalt()).decode()
    try:
        HASH_FILE.write_text(PASSWORD_HASH)
        log.info("Password hash generated from TAO_PASSWORD and persisted to %s", HASH_FILE)
    except OSError as exc:
        log.warning("Could not persist password hash: %s", exc)
elif HASH_FILE.exists():
    PASSWORD_HASH = HASH_FILE.read_text().strip()
    log.info("Loaded persisted bcrypt hash from %s (no TAO_PASSWORD in env)", HASH_FILE)
else:
    PASSWORD_HASH = hashlib.sha256(_raw_password.encode()).hexdigest()
    log.info("Using SHA-256 hash of auto-generated password (will upgrade to bcrypt on first login)")

# ---------------------------------------------------------------------------
# Session secret — persist to disk so it survives restarts
# ---------------------------------------------------------------------------

_SECRET_FILE = _DATA_DIR / ".session-secret"

_env_secret = os.environ.get("TAO_SESSION_SECRET", "")
if _env_secret:
    SESSION_SECRET = _env_secret
elif _SECRET_FILE.exists():
    SESSION_SECRET = _SECRET_FILE.read_text().strip()
    log.info("Loaded session secret from %s", _SECRET_FILE)
else:
    SESSION_SECRET = secrets.token_hex(32)
    _SECRET_FILE.write_text(SESSION_SECRET)
    log.info("Generated and persisted new session secret to %s", _SECRET_FILE)

# ---------------------------------------------------------------------------
# All other settings
# ---------------------------------------------------------------------------

SESSION_TTL          = int(os.environ.get("TAO_SESSION_TTL",          "86400"))
HOST                 = os.environ.get("TAO_HOST",                       "127.0.0.1")
PORT                 = int(os.environ.get("TAO_PORT",                   "7777"))
CLAUDE_CMD           = os.environ.get("TAO_CLAUDE_CMD",                 "claude")
# CLAUDE_EXTRA_FLAGS is prepended to every subprocess `claude -p` invocation.
# In non-interactive contexts (Railway cron, scheduled tasks, autonomous runs) this
# MUST include --dangerously-skip-permissions so the CLI never stalls on a prompt.
# Default ON for marathon mode; set TAO_CLAUDE_INTERACTIVE=1 to disable for local dev.
_INTERACTIVE         = os.environ.get("TAO_CLAUDE_INTERACTIVE", "0") == "1"
CLAUDE_EXTRA_FLAGS   = [] if _INTERACTIVE else ["--dangerously-skip-permissions"]
ALLOWED_MODELS       = ["opus", "sonnet", "haiku"]
MAX_CONCURRENT_SESSIONS = int(os.environ.get("TAO_MAX_SESSIONS",        "3"))
RATE_LIMIT_PER_MIN   = int(os.environ.get("TAO_RATE_LIMIT",             "30"))
WORKSPACE_ROOT       = os.environ.get("TAO_WORKSPACE",
                           os.path.join(os.path.dirname(__file__), "..", "workspaces"))
LOG_DIR              = os.environ.get("TAO_LOGS",
                           os.path.join(os.path.dirname(__file__), "..", "logs"))
GC_MAX_AGE           = int(os.environ.get("TAO_GC_MAX_AGE",             "14400"))
LESSONS_FILE         = os.environ.get("TAO_LESSONS",
                           os.path.join(os.path.dirname(__file__), "..", "..", ".harness", "lessons.jsonl"))
EVALUATOR_ENABLED    = os.environ.get("TAO_EVALUATOR_ENABLED", "true").lower() == "true"
EVALUATOR_MODEL      = os.environ.get("TAO_EVALUATOR_MODEL",            "sonnet")
EVALUATOR_THRESHOLD  = int(os.environ.get("TAO_EVALUATOR_THRESHOLD",    "8"))
EVALUATOR_MAX_RETRIES = int(os.environ.get("TAO_EVALUATOR_MAX_RETRIES", "2"))
WEBHOOK_SECRET       = os.environ.get("TAO_WEBHOOK_SECRET",             "")
LINEAR_WEBHOOK_SECRET = os.environ.get("TAO_LINEAR_WEBHOOK_SECRET",     "")

# ---------------------------------------------------------------------------
# Pi-SEO scanner settings
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY",               "")
USE_AGENT_SDK        = os.environ.get("TAO_USE_AGENT_SDK", "0") == "1"

LINEAR_API_KEY       = os.environ.get("LINEAR_API_KEY",                 "")
AUTONOMY_ENABLED     = os.environ.get("TAO_AUTONOMY_ENABLED", "1") != "0"
SCAN_WORKSPACE_ROOT  = os.environ.get("SCAN_WORKSPACE_ROOT",
                           str(Path.home() / "pi-seo-workspace"))
SCAN_RESULTS_DIR     = os.environ.get("SCAN_RESULTS_DIR",
                           os.path.join(os.path.dirname(__file__), "..", "..", ".harness", "scan-results"))

# RA-586 — Production gate for Pi-SEO live scanning.
# Set PI_SEO_ACTIVE=1 in Railway (or .env.local) to enable live scans.
# When 0 (default), all scan + monitor cron triggers are skipped with an info log.
# This allows the scanner code to be fully deployed without immediately running
# across all 11 repos until the operator explicitly activates it.
PI_SEO_ACTIVE        = os.environ.get("PI_SEO_ACTIVE", "0") == "1"

# RA-586 — Path exclusion patterns for known documentation false positives.
# Files matching any of these glob-style substrings are skipped by the secret scanner.
# SEC-1: dr-nrpg  — docs/runbooks/secrets-rotation.md (example rotation procedure)
# SEC-2: synthex  — scripts/generate-env-docs.js, scripts/get-linear-task.js, scripts/fetch-linear.js
# SEC-3: ccw-crm  — docs/ISS-014-VERIFICATION.md (verification report, example keys)
SCAN_PATH_EXCLUSIONS: list[str] = [p.strip() for p in
    os.environ.get("SCAN_PATH_EXCLUSIONS",
        "docs/runbooks/secrets-rotation.md,"
        "scripts/generate-env-docs.js,"
        "scripts/get-linear-task.js,"
        "scripts/fetch-linear.js,"
        "docs/ISS-014-VERIFICATION.md"
    ).split(",") if p.strip()
]

# RA-586 — Telegram alert channel for critical Pi-SEO findings.
# TELEGRAM_BOT_TOKEN: the Railway Python bot token (same as telegram-bot/.env)
# TELEGRAM_ALERT_CHAT_ID: Phill's Telegram user ID (8792816988 from ALLOWED_USERS)
# When either is unset, Telegram alerts are silently skipped (Linear tickets still created).
TELEGRAM_BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN",   "")
TELEGRAM_ALERT_CHAT_ID = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")
# Webhook secret for POST /webhook/telegram.
# Telegram requires [A-Za-z0-9_-] only (no colons). Defaults to the numeric
# prefix of the bot token (before the colon) if no explicit value is set.
TELEGRAM_WEBHOOK_SECRET = os.environ.get(
    "TELEGRAM_WEBHOOK_SECRET",
    TELEGRAM_BOT_TOKEN.split(":")[0] if ":" in TELEGRAM_BOT_TOKEN else TELEGRAM_BOT_TOKEN,
)

# RA-651 / RA-633 — Supabase server-side writes (gate_checks, alert_escalations).
# NEXT_PUBLIC_SUPABASE_URL matches the dashboard env var (same project).
# SUPABASE_SERVICE_ROLE_KEY is the service-role secret — bypasses RLS for writes.
# When either is unset, supabase_log writes are silently skipped (non-fatal).
SUPABASE_URL              = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "") or os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# RA-634 — API fallback gate (Risk Register R-02).
# When TAO_USE_FALLBACK=1, the pipeline uses the Anthropic Python SDK directly
# (api.anthropic.com with ANTHROPIC_API_KEY) instead of the claude CLI or Agent SDK.
# FALLBACK ONLY — never set in normal operation. Tested quarterly via scripts/fallback_dryrun.py.
USE_FALLBACK          = os.environ.get("TAO_USE_FALLBACK", "0") == "1"

if not LINEAR_API_KEY:
    log.warning("LINEAR_API_KEY not set — Pi-SEO triage will run in dry-run mode")
if not PI_SEO_ACTIVE:
    log.info("PI_SEO_ACTIVE=0 — Pi-SEO cron scans are paused (set PI_SEO_ACTIVE=1 to enable)")
if PI_SEO_ACTIVE and not TELEGRAM_BOT_TOKEN:
    log.warning("TELEGRAM_BOT_TOKEN not set — critical Pi-SEO findings will NOT reach Telegram")

for d in [WORKSPACE_ROOT, LOG_DIR, SCAN_WORKSPACE_ROOT, SCAN_RESULTS_DIR]:
    os.makedirs(d, exist_ok=True)
