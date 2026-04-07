import hashlib, hmac, json, time
from fastapi import Request, HTTPException
from . import config

def hash_password(p): return hashlib.sha256(p.encode()).hexdigest()
def verify_password(p): return hmac.compare_digest(hash_password(p), config.PASSWORD_HASH)

def create_session_token():
    payload = json.dumps({"iat": int(time.time()), "exp": int(time.time()) + config.SESSION_TTL}, separators=(",",":"))
    sig = hmac.new(config.SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"

def verify_session_token(token):
    try:
        parts = token.rsplit(".", 1)
        if len(parts) != 2: return False
        data, sig = parts
        expected = hmac.new(config.SESSION_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected): return False
        return json.loads(data).get("exp", 0) >= time.time()
    except: return False

_req_log = {}
_last_gc: float = 0.0
_GC_INTERVAL: float = 300.0  # purge stale IPs every 5 minutes

def check_rate_limit(ip):
    global _last_gc
    now = time.time()
    # Inline GC: purge IP keys with no requests in the last 120 seconds.
    # Runs at most once per _GC_INTERVAL to stay cheap on hot paths.
    if now - _last_gc > _GC_INTERVAL:
        _last_gc = now
        stale = [k for k, v in _req_log.items() if not v or now - v[-1] > 120]
        for k in stale:
            del _req_log[k]
    _req_log.setdefault(ip, [])
    _req_log[ip] = [t for t in _req_log[ip] if now - t < 60]
    if len(_req_log[ip]) >= config.RATE_LIMIT_PER_MIN: return False
    _req_log[ip].append(now)
    return True

async def require_auth(request: Request):
    token = request.cookies.get("tao_session")
    if token and verify_session_token(token): return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and verify_session_token(auth[7:]): return True
    raise HTTPException(status_code=401, detail="Not authenticated")

async def require_rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(ip): raise HTTPException(status_code=429, detail="Rate limit exceeded")
    return True
