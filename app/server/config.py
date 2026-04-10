import os, secrets, hashlib, logging, json
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
if not _raw_password:
    _raw_password = secrets.token_urlsafe(24)
    log.info("Generated one-time password: %s  (set TAO_PASSWORD to persist)", _raw_password)

# ---------------------------------------------------------------------------
# Data directory — must be defined before any path references below
# ---------------------------------------------------------------------------

_DATA_DIR = Path(os.path.dirname(__file__)).parent / "data"
_DATA_DIR.mkdir(exist_ok=True)

# Store the raw password; auth.hash_password() / auth.verify_password() handle bcrypt.
# On first login, SHA-256 is upgraded to bcrypt and persisted to HASH_FILE so restarts
# don't revert to SHA-256.
HASH_FILE = _DATA_DIR / ".password-hash"
if HASH_FILE.exists():
    PASSWORD_HASH = HASH_FILE.read_text().strip()
    log.info("Loaded persisted bcrypt hash from %s", HASH_FILE)
else:
    PASSWORD_HASH = hashlib.sha256(_raw_password.encode()).hexdigest()

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
SCAN_WORKSPACE_ROOT  = os.environ.get("SCAN_WORKSPACE_ROOT",
                           str(Path.home() / "pi-seo-workspace"))
SCAN_RESULTS_DIR     = os.environ.get("SCAN_RESULTS_DIR",
                           os.path.join(os.path.dirname(__file__), "..", "..", ".harness", "scan-results"))

if not LINEAR_API_KEY:
    log.warning("LINEAR_API_KEY not set — Pi-SEO triage will run in dry-run mode")

for d in [WORKSPACE_ROOT, LOG_DIR, SCAN_WORKSPACE_ROOT, SCAN_RESULTS_DIR]:
    os.makedirs(d, exist_ok=True)
