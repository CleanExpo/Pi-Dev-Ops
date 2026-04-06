import os, secrets, hashlib
_raw_password = os.environ.get("TAO_PASSWORD", "")
if not _raw_password:
    _raw_password = secrets.token_urlsafe(24)
    print(f"\n{'='*60}\n  PI CEO PASSWORD:\n  {_raw_password}\n{'='*60}\n")
PASSWORD_HASH = hashlib.sha256(_raw_password.encode()).hexdigest()
SESSION_SECRET = os.environ.get("TAO_SESSION_SECRET", secrets.token_hex(32))
SESSION_TTL = int(os.environ.get("TAO_SESSION_TTL", "86400"))
HOST = os.environ.get("TAO_HOST", "127.0.0.1")
PORT = int(os.environ.get("TAO_PORT", "7777"))
CLAUDE_CMD = os.environ.get("TAO_CLAUDE_CMD", "claude")
ALLOWED_MODELS = ["opus", "sonnet", "haiku"]
MAX_CONCURRENT_SESSIONS = int(os.environ.get("TAO_MAX_SESSIONS", "3"))
RATE_LIMIT_PER_MIN = int(os.environ.get("TAO_RATE_LIMIT", "30"))
WORKSPACE_ROOT = os.environ.get("TAO_WORKSPACE", os.path.join(os.path.dirname(__file__), "..", "workspaces"))
LOG_DIR = os.environ.get("TAO_LOGS", os.path.join(os.path.dirname(__file__), "..", "logs"))
for d in [WORKSPACE_ROOT, LOG_DIR]: os.makedirs(d, exist_ok=True)
