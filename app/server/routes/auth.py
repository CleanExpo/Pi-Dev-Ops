"""Auth routes: /api/login, /api/logout, /api/me (RA-937)."""
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ..auth import verify_password, create_session_token, require_auth, require_rate_limit
from .. import config

# Re-derive here to avoid importing from app_factory (would create a coupling)
_IS_CLOUD = bool(
    os.environ.get("RAILWAY_ENVIRONMENT")
    or os.environ.get("RENDER")
    or os.environ.get("FLY_APP_NAME")
)

router = APIRouter()


@router.post("/api/login")
async def login(request: Request, _=Depends(require_rate_limit)):
    body = await request.json()
    if not verify_password(body.get("password", "")):
        raise HTTPException(401, "Invalid password")
    token = create_session_token()
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
async def logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie("tao_session", path="/")
    return r


@router.get("/api/me")
async def me(_=Depends(require_auth)):
    return {"authenticated": True}
