"""Auth routes: /api/login, /api/logout, /api/me (RA-937)."""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ..auth import verify_password, create_session_token, require_auth, require_rate_limit, revoke_token
from .. import config

log = logging.getLogger("pi-ceo.auth")

# Re-derive here to avoid importing from app_factory (would create a coupling)
_IS_CLOUD = bool(
    os.environ.get("RAILWAY_ENVIRONMENT")
    or os.environ.get("RENDER")
    or os.environ.get("FLY_APP_NAME")
)

router = APIRouter()


@router.post("/api/login")
async def login(request: Request, _=Depends(require_rate_limit)):
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()
    if not verify_password(body.get("password", "")):
        # RA-1017: structured audit log on failure
        log.warning("Login failed: ip=%s reason=bad_password", client_ip)
        raise HTTPException(401, "Invalid password")
    token = create_session_token()
    # RA-1017: structured audit log on success
    log.info("Login success: ip=%s", client_ip)
    response = JSONResponse({"ok": True})
    # Cross-origin cookies require SameSite=None + Secure (HTTPS only)
    response.set_cookie(
        "tao_session", token,
        httponly=True,
        secure=_IS_CLOUD,           # True on Railway (HTTPS), False locally (HTTP)
        samesite="none" if _IS_CLOUD else "strict",
        max_age=config.SESSION_TTL,
        path="/",
    )
    return response


@router.post("/api/logout")
async def logout(request: Request):
    # RA-1014: revoke the token so it cannot be reused within its remaining TTL
    token = (
        request.cookies.get("tao_session")
        or request.headers.get("Authorization", "").replace("Bearer ", "")
    )
    if token:
        revoke_token(token)
    r = JSONResponse({"ok": True})
    r.delete_cookie("tao_session", path="/")
    return r


@router.get("/api/me")
async def me(_=Depends(require_auth)):
    return {"authenticated": True}
