import os
import secrets
import hashlib
import logging
import json
from pathlib import Path
# NB: the dotenv loader was replaced with a custom `_load_env_file()` below
# (which only overrides empty strings / unresolved op:// refs so `op run`
# injected values aren't clobbered). The `from dotenv import load_dotenv`
# import was left over and broke `ruff`.

# ---------------------------------------------------------------------------
# Load .env files before reading any os.environ values.
# override=True ensures variables in the file beat whatever the shell has set —
# specifically, the `claude` CLI sets ANTHROPIC_API_KEY="" in the parent shell
# env as a security measure, so child processes (this server) would inherit an
# empty string. Loading from the file with override=True fixes that permanently,
# regardless of how the server was launched.
# ---------------------------------------------------------------------------
_root = Path(__file__).resolve().parents[2]  # Pi-Dev-Ops/
# Selective override — only replace empty strings (the claude CLI sets
# ANTHROPIC_API_KEY="" in the parent shell; treat that as unset) and plain
# op:// refs (stale values that were never resolved). Leave already-resolved
# values untouched so `op run`-injected secrets aren't clobbered by the file.
def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        cur = os.environ.get(k, "<unset>")
        if cur == "<unset>" or cur == "" or cur.startswith("op://"):
            os.environ[k] = v
_load_env_file(_root / ".env")
_load_env_file(_root / ".env.local")

# ---------------------------------------------------------------------------
# 1Password op:// ref guard (hardwired lesson, RA-1169+)
# dotenv reads "op://vault/item/field" as a literal string, not a resolved
# secret. Detect unresolved refs and either (a) treat them as absent when the
# caller has a sensible default, or (b) fail hard with a clear error pointing
# at the fix: launch via `op run --env-file=.env.local -- uvicorn ...`
# ---------------------------------------------------------------------------
_OP_REF_PREFIX = "op://"
_unresolved_refs: list[str] = []
for _k, _v in list(os.environ.items()):
    if isinstance(_v, str) and _v.startswith(_OP_REF_PREFIX):
        _unresolved_refs.append(_k)
        # Scrub it so downstream config sees it as unset rather than feeding
        # the literal ref into API clients (which would produce opaque auth
        # errors like "invalid bearer token").
        os.environ.pop(_k, None)

# Warning deferred to after logger init below — see _emit_op_ref_warning().

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

if _unresolved_refs:
    log.warning(
        "1Password op:// refs detected but UNRESOLVED for: %s — "
        "launch with `op run --env-file=.env.local -- uvicorn app.server.main:app` "
        "(local) or set OP_SERVICE_ACCOUNT_TOKEN + wrap Dockerfile CMD with `op run` "
        "(Railway). These env vars will be treated as unset for this process.",
        ", ".join(sorted(_unresolved_refs)),
    )

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
DATA_DIR: str = str(_DATA_DIR)  # public export for sessions.py and other modules

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

# ── MODEL ROUTING POLICY (RA-1099 — hardwired 2026-04-17) ──────────────────
# Opus 4.7 is reserved for Senior PM (planner) and Senior Orchestrator agents.
# Every other agent role MUST use Sonnet 4.6 or Haiku 4.5.
# Override via TAO_OPUS_ALLOWED_ROLES if you ever need to widen this — but the
# default is strict by design (cost + latency).
OPUS_ALLOWED_ROLES   = set(
    os.environ.get("TAO_OPUS_ALLOWED_ROLES", "planner,orchestrator").split(",")
)
# Long-form model IDs returned by _resolve_model_id() in pipeline.py and
# session_evaluator.py. Kept here so a single edit changes both readers.
MODEL_ID_OPUS        = "claude-opus-4-7"
MODEL_ID_SONNET      = "claude-sonnet-4-6"
MODEL_ID_HAIKU       = "claude-haiku-4-5-20251001"
MODEL_SHORT_TO_ID    = {
    "opus":   MODEL_ID_OPUS,
    "sonnet": MODEL_ID_SONNET,
    "haiku":  MODEL_ID_HAIKU,
}
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

# RA-674 — Confidence-weighted evaluator thresholds.
# Tier 1 (auto-ship fast): score ≥ EVAL_AUTOSHIP_SCORE  AND confidence ≥ EVAL_AUTOSHIP_CONFIDENCE%
# Tier 2 (pass):           score ≥ EVALUATOR_THRESHOLD   AND confidence ≥ EVAL_FLAG_CONFIDENCE%
# Tier 3 (pass + flag):    score ≥ EVALUATOR_THRESHOLD   AND confidence <  EVAL_FLAG_CONFIDENCE%
# Retry:                   score <  EVALUATOR_THRESHOLD   (existing behaviour, unchanged)
EVAL_AUTOSHIP_SCORE      = float(os.environ.get("TAO_EVAL_AUTOSHIP_SCORE",      "9.5"))
EVAL_AUTOSHIP_CONFIDENCE = float(os.environ.get("TAO_EVAL_AUTOSHIP_CONFIDENCE", "90"))
EVAL_FLAG_CONFIDENCE     = float(os.environ.get("TAO_EVAL_FLAG_CONFIDENCE",     "60"))
WEBHOOK_SECRET       = os.environ.get("TAO_WEBHOOK_SECRET",             "")
LINEAR_WEBHOOK_SECRET = os.environ.get("TAO_LINEAR_WEBHOOK_SECRET",     "")

# RA-677 — AUTONOMY_BUDGET: single-knob pipeline configuration (minutes).
# 0 = disabled; per-request budget_minutes overrides this global default.
# When set, auto-tunes eval_threshold, max_retries, model, and timeout.
AUTONOMY_BUDGET_MINS = int(os.environ.get("TAO_AUTONOMY_BUDGET", "0"))

# ---------------------------------------------------------------------------
# Pi-SEO scanner settings
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY",               "")

# RA-1094B — SDK-only mandate. The Agent SDK has been the production path
# since RA-576 (subprocess `claude -p` fallbacks removed from sessions.py).
# Default is True; an explicit "0" setting raises ImportError at module load.
# The flag is retained only for telemetry / test patching.
if os.environ.get("TAO_USE_AGENT_SDK") == "0":
    raise ImportError(
        "TAO_USE_AGENT_SDK=0 is not supported since RA-1094B. "
        "The Agent SDK has been the only supported path since RA-576. "
        "Unset the variable or set it to 1."
    )
USE_AGENT_SDK        = True

# RA-1009 — Prompt caching: set ENABLE_PROMPT_CACHING_1H=1 in Railway to activate.
# When enabled, SDK calls and direct Anthropic API calls attach cache_control blocks
# to static system-prompt content, reducing cost up to 90% on repeated sessions.
ENABLE_PROMPT_CACHING_1H: bool = os.environ.get("ENABLE_PROMPT_CACHING_1H", "0") == "1"

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
        # Pi-Dev-Ops internal false positives (RA-654, RA-687)
        "docs/runbooks/secrets-rotation.md,"
        "scripts/generate-env-docs.js,"
        "scripts/get-linear-task.js,"
        "scripts/fetch-linear.js,"
        "docs/ISS-014-VERIFICATION.md,"
        "scripts/,"
        "dashboard/scripts/,"
        "Dockerfile,"
        "railway.toml,"
        "app/server/scanner.py,"
        "archive/,"
        # RA-687 — dashboard/app/layout.tsx:21 contains an intentional
        # dangerouslySetInnerHTML for the theme-init script (CSP-nonce-protected,
        # prevents FOUC on theme load). React 19 + Next.js 16 require the raw
        # <script> path here — suppressHydrationWarning + nonce keep it safe.
        "dashboard/app/layout.tsx,"
        # RA-834 — portfolio-wide false positive patterns confirmed 2026-04-14
        # supabase/config.toml: local dev placeholder anon/service keys (not production)
        "supabase/config.toml,"
        # storybook-static/: generated build output — not tracked in production deploys
        "storybook-static/,"
        # .claude/archived/: Claude Code session archives — not shipped code
        ".claude/archived/,"
        # .husky/: git hook scripts — dev tooling, never deployed
        ".husky/,"
        # public/api-docs.html: generated OpenAPI HTML — example key strings in templates
        "public/api-docs.html,"
        # NodeJS-Starter-V1/: template scaffold nested in CCW-CRM — not active code
        "NodeJS-Starter-V1/,"
        # Test files: hardcoded test-database credentials (local dev only, not production)
        "test_asyncpg.py,"
        "test_nopass.py,"
        "test_new_user.py,"
        "test_asyncpg_simple.py,"
        "test_testuser.py,"
        "test_psycopg2.py,"
        # setup/deploy scripts: use $VAR_NAME placeholders, not real keys
        "phase23-setup.sh,"
        "setup-digitalocean.sh,"
        # restoreassist change-password page: scanner matches variable names in form logic
        "app/dashboard/change-password/page.tsx,"
        # ccw-crm utility scripts: hardcoded local-dev credentials (not production)
        "apps/backend/check_orders.py,"
        "apps/backend/create_demo_orders_simple.py,"
        "apps/backend/verify_sequence_deployment.py,"
        "apps/backend/verify_race_condition_fix.py,"
        # ccw-crm test/demo files: placeholder webhook and token values
        "apps/backend/test_shopify_integration.py,"
        # ccw-crm schema/source files: placeholder example values
        "apps/backend/src/db/shopify_schemas.py,"
        # ccw-crm AI agent: confirmation_token in a string template (not a hardcoded secret)
        "apps/backend/src/ai/agents/specialized/task_executor_agent.py,"
        # ccw-crm payment processor: test placeholder tokens
        "apps/backend/src/integrations/payments/processor.py,"
        # dr-nrpg: enum constant triggers token pattern (not a real token)
        "apps/web/lib/api-errors.ts,"
        # dr-nrpg: dev-only captcha placeholder constant
        "apps/web/src/lib/security/captcha.ts,"
        # RA-834 (Pi-Dev-Ops / Pi-CEO) — FP exclusions confirmed 2026-04-17
        # .harness/scan-results/: scanner scanning its own archived output JSON (self-match)
        ".harness/scan-results/,"
        # .harness/monitor-digests/: monitor digest JSON contains quoted scan findings
        ".harness/monitor-digests/,"
        # .harness/lessons.jsonl: historical lessons reference API key patterns in examples
        ".harness/lessons.jsonl,"
        # .harness/board-meetings/: meeting notes quote credentials as illustrative examples
        ".harness/board-meetings/,"
        # .harness/handoff.md: session handoff doc references key names, not values
        ".harness/handoff.md,"
        # .harness/agent-sdk-metrics/: generated metric JSON includes example tokens
        ".harness/agent-sdk-metrics/,"
        # .harness/feature_list.json: feature descriptions quote scanner regex patterns
        ".harness/feature_list.json,"
        # .harness/pipeline/: pipeline artefacts include quoted credential-shaped strings
        ".harness/pipeline/,"
        # skills/pi-seo-*/SKILL.md: skill docs describe scanner patterns (self-match)
        "skills/pi-seo-remediation/,"
        "skills/pi-seo-scanner/,"
        "skills/pi-seo-health-monitor/,"
        "skills/security-audit/,"
        "skills/ship-release/,"
        # app/server/triage.py + autopr.py: contain scanner regex patterns (self-match, like scanner.py)
        "app/server/triage.py,"
        "app/server/autopr.py,"
        # tests/: test fixtures use mock tokens and placeholder API keys
        "tests/fixtures/,"
        "tests/test_webhook.py,"
        # scripts/smoke_test*.py: smoke tests carry inline sample tokens for assertions
        "scripts/smoke_test.py,"
        "scripts/smoke_test_critical.py,"
        # scripts/fetch_anthropic_docs.py: fetches API docs containing example key shapes
        "scripts/fetch_anthropic_docs.py,"
        # scripts/analyze.sh + deploy scripts: reference env var names in shell
        "scripts/analyze.sh,"
        "scripts/deploy_railway.sh,"
        # dashboard/scripts/: build-time scripts with placeholder secrets
        "dashboard/scripts/,"
        # dashboard/.next/: Next.js build artefacts — generated, not source
        "dashboard/.next/,"
        # node_modules/: third-party deps — not our code
        "node_modules/,"
        # docs/ship-chain/: educational examples with illustrative tokens
        "docs/ship-chain/,"
        # Top-level deployment docs: describe env vars and deployment procedures
        "DEPLOYMENT_GUIDE.md,"
        "DEPLOYMENT.md,"
        "READY_TO_DEPLOY.md,"
        "DEPLOYMENT_STATUS.md,"
        "CLAUDE.md,"
        "README.md,"
        # _deploy.py: legacy deploy helper with env var references
        "_deploy.py,"
        # archive/: archived historical code, not deployed
        "archive/run_parallel_board.py"
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

# RA-697 — Agent SDK canary routing rate.
# When > 0.0, that fraction of requests are routed through the Managed Agents API
# canary path instead of the default SDK path.
# 0.0 = disabled (default); 1.0 = 100% canary.
# Set TAO_USE_AGENT_SDK_CANARY_RATE in Railway env to activate.
AGENT_SDK_CANARY_RATE: float = float(os.environ.get("TAO_USE_AGENT_SDK_CANARY_RATE", "0.0"))

# Linear project/team identifiers — not secrets, but centralised here so
# they don't appear as literals scattered across source files.
LINEAR_TEAM_ID    = os.environ.get("LINEAR_TEAM_ID",    "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673")
LINEAR_PROJECT_ID = os.environ.get("LINEAR_PROJECT_ID", "f45212be-3259-4bfb-89b1-54c122c939a7")

# RA-692 — Vercel deployment drift monitoring.
# VERCEL_TOKEN: personal access token with read:deployments scope.
# VERCEL_TEAM_ID: optional team/org slug (e.g. "unite-group").
# VERCEL_PROJECT_ID: project identifier for the dashboard frontend.
# When any are unset, /api/health/vercel returns degraded=True and
# deployment drift checks are skipped (non-fatal).
VERCEL_TOKEN      = os.environ.get("VERCEL_TOKEN",      "")
VERCEL_TEAM_ID    = os.environ.get("VERCEL_TEAM_ID",    "")
VERCEL_PROJECT_ID = os.environ.get("VERCEL_PROJECT_ID", "")

if not LINEAR_API_KEY:
    log.warning("LINEAR_API_KEY not set — Pi-SEO triage will run in dry-run mode")
if not PI_SEO_ACTIVE:
    log.info("PI_SEO_ACTIVE=0 — Pi-SEO cron scans are paused (set PI_SEO_ACTIVE=1 to enable)")
if PI_SEO_ACTIVE and not TELEGRAM_BOT_TOKEN:
    log.warning("TELEGRAM_BOT_TOKEN not set — critical Pi-SEO findings will NOT reach Telegram")
if not VERCEL_TOKEN:
    log.warning("VERCEL_TOKEN not set — frontend deployment drift monitoring is BLIND (RA-692)")

for d in [WORKSPACE_ROOT, LOG_DIR, SCAN_WORKSPACE_ROOT, SCAN_RESULTS_DIR]:
    os.makedirs(d, exist_ok=True)
