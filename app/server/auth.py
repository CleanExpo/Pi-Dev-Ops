import hashlib
import hmac
import json
import os
import time
import logging
import bcrypt
from fastapi import Request, HTTPException
from . import config

log = logging.getLogger("pi-ceo.auth")

# True when running on Railway / Render / Fly — these platforms sit behind a
# trusted edge that sets X-Forwarded-For to the actual client IP.
_IS_CLOUD = bool(
    os.environ.get("RAILWAY_ENVIRONMENT")
    or os.environ.get("RENDER")
    or os.environ.get("FLY_APP_NAME")
)

# ---------------------------------------------------------------------------
# Token revocation — in-memory set (RA-1014)
# Entries are (token_hash, expiry_timestamp). Cleaned up lazily on verify.
# Safe to lose on restart — Railway restarts invalidate all sessions anyway.
# ---------------------------------------------------------------------------

_revoked_tokens: dict[str, float] = {}  # token_hash -> expiry_timestamp
_revoked_last_gc: float = 0.0


def _token_hash(token: str) -> str:
    """SHA-256 fingerprint of a token — used as the revocation key."""
    return hashlib.sha256(token.encode()).hexdigest()


def revoke_token(token: str) -> None:
    """Add a token to the revocation set. Expiry matches SESSION_TTL."""
    key = _token_hash(token)
    _revoked_tokens[key] = time.time() + config.SESSION_TTL


def _is_token_revoked(token: str) -> bool:
    """Return True if token has been explicitly revoked. Prunes stale entries."""
    global _revoked_last_gc
    now = time.time()
    # Prune expired entries every 5 minutes
    if now - _revoked_last_gc > 300.0:
        _revoked_last_gc = now
        stale = [k for k, exp in _revoked_tokens.items() if exp < now]
        for k in stale:
            del _revoked_tokens[k]
    key = _token_hash(token)
    entry = _revoked_tokens.get(key)
    return entry is not None and entry >= now

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
            # Upgrade: re-hash with bcrypt, update config, and persist to disk.
            new_hash = hash_password(p)
            config.PASSWORD_HASH = new_hash
            try:
                config.HASH_FILE.write_text(new_hash)
                log.info("Password hash upgraded from SHA-256 to bcrypt and persisted to %s", config.HASH_FILE)
            except OSError as exc:
                log.warning("bcrypt hash upgrade succeeded but could not persist: %s", exc)
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
        if json.loads(data).get("exp", 0) < time.time():
            return False
        # RA-1014: reject tokens that have been explicitly revoked on logout
        if _is_token_revoked(token):
            return False
        return True
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
    # IP resolution strategy:
    #
    # In cloud (Railway/Render/Fly): The app sits behind a trusted edge proxy
    # that injects X-Forwarded-For with the real client IP.  Using
    # request.client.host in these environments gives the *load-balancer* IP
    # (e.g. 10.x.x.x), which may differ per-instance, so the per-IP bucket
    # never fills and rate limiting silently breaks.  Trust XFF here because
    # Railway strips any client-supplied XFF before adding its own.
    #
    # Locally: Direct TCP connection — use request.client.host so we never
    # accidentally trust a crafted X-Forwarded-For header in dev.
    if _IS_CLOUD:
        forwarded = request.headers.get("x-forwarded-for", "")
        ip = forwarded.split(",")[0].strip() if forwarded else "unknown"
    elif request.client is not None:
        ip = request.client.host
    else:
        ip = "unknown"
    if not check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    return True
