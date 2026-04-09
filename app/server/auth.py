import hashlib, hmac, json, time, logging
import bcrypt
from fastapi import Request, HTTPException
from . import config

log = logging.getLogger("pi-ceo.auth")

# ---------------------------------------------------------------------------
# Password hashing — bcrypt with transparent migration from legacy SHA-256
# ---------------------------------------------------------------------------

def _is_legacy_hash(h: str) -> bool:
    """SHA-256 hashes are exactly 64 hex characters."""
    return len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def hash_password(p: str) -> str:
    """Return a bcrypt hash of the password."""
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str) -> bool:
    """Verify password against stored hash, migrating from SHA-256 if needed."""
    stored = config.PASSWORD_HASH
    if _is_legacy_hash(stored):
        # Legacy SHA-256 path — timing-safe comparison
        candidate = hashlib.sha256(p.encode()).hexdigest()
        match = hmac.compare_digest(candidate, stored)
        if match:
            # Upgrade: re-hash with bcrypt and update config at runtime.
            # The new hash is only in-memory; set TAO_PASSWORD to persist it.
            config.PASSWORD_HASH = hash_password(p)
            log.info("Password hash upgraded from SHA-256 to bcrypt (set TAO_PASSWORD to persist)")
        return match
    try:
        return bcrypt.checkpw(p.encode(), stored.encode())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Session tokens — signed JWS-style payload.signature
# ---------------------------------------------------------------------------

def create_session_token() -> str:
    payload = json.dumps(
        {"iat": int(time.time()), "exp": int(time.time()) + config.SESSION_TTL},
        separators=(",", ":"),
    )
    sig = hmac.new(config.SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_session_token(token: str) -> bool:
    try:
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            return False
        data, sig = parts
        expected = hmac.new(config.SESSION_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        return json.loads(data).get("exp", 0) >= time.time()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Rate limiting — sliding-window per IP
# ---------------------------------------------------------------------------

_req_log: dict[str, list[float]] = {}
_last_gc: float = 0.0
_GC_INTERVAL: float = 300.0  # purge stale IPs every 5 minutes


def check_rate_limit(ip: str) -> bool:
    global _last_gc
    now = time.time()
    if now - _last_gc > _GC_INTERVAL:
        _last_gc = now
        stale = [k for k, v in _req_log.items() if not v or now - v[-1] > 120]
        for k in stale:
            del _req_log[k]
    _req_log.setdefault(ip, [])
    _req_log[ip] = [t for t in _req_log[ip] if now - t < 60]
    if len(_req_log[ip]) >= config.RATE_LIMIT_PER_MIN:
        log.warning("Rate limit hit ip=%s", ip)
        return False
    _req_log[ip].append(now)
    return True


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def require_auth(request: Request) -> bool:
    token = request.cookies.get("tao_session")
    if token and verify_session_token(token):
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and verify_session_token(auth[7:]):
        return True
    log.warning("Unauthenticated request path=%s ip=%s", request.url.path,
                request.client.host if request.client else "?")
    raise HTTPException(status_code=401, detail="Not authenticated")


async def require_rate_limit(request: Request) -> bool:
    ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    return True
