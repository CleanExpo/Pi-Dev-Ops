import asyncio, json, os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from .auth import verify_password, create_session_token, verify_session_token, require_auth, require_rate_limit
from .sessions import create_session, get_session, list_sessions, kill_session, restore_sessions
from . import config

app = FastAPI(title="Pi CEO", docs_url=None, redoc_url=None, openapi_url=None)

@app.on_event("startup")
async def on_startup():
    restore_sessions()
    print("[startup] Pi CEO ready.")

# True when deployed on Railway (or any cloud with this env var set)
_IS_CLOUD = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER") or os.environ.get("FLY_APP_NAME"))

# Allowed origins: local Next.js dev + Vercel deployments
# Append extra origins via TAO_ALLOWED_ORIGINS (comma-separated)
_extra = os.environ.get("TAO_ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://pi-dev-ops.vercel.app",
    "https://dashboard-unite-group.vercel.app",
] + [o.strip() for o in _extra.split(",") if o.strip()]

class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' ws: wss: https://*.vercel.app https://*.railway.app; "
            "img-src 'self' data:; "
            "frame-ancestors 'none';"
        )
        return response

app.add_middleware(SecurityHeaders)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Cookie", "Authorization"],
)
# NOTE: TrustedHostMiddleware removed — Railway terminates TLS and proxies requests;
# restricting to 127.0.0.1 would block all cloud traffic.

@app.post("/api/login")
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

@app.post("/api/logout")
async def logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie("tao_session", path="/")
    return r

@app.get("/api/me")
async def me(_=Depends(require_auth)):
    return {"authenticated": True}

@app.post("/api/build", dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def build(request: Request):
    body = await request.json()
    repo_url = body.get("repo_url", "").strip()
    brief = body.get("brief", "").strip()
    model = body.get("model", "sonnet").strip()
    if not repo_url: raise HTTPException(400, "repo_url required")
    if not repo_url.startswith(("https://", "git@")): raise HTTPException(400, "Invalid URL")
    if model not in config.ALLOWED_MODELS: raise HTTPException(400, f"model must be {config.ALLOWED_MODELS}")
    try: session = await create_session(repo_url, brief, model)
    except RuntimeError as e: raise HTTPException(429, str(e))
    return {"session_id": session.id, "status": session.status}

@app.get("/api/sessions", dependencies=[Depends(require_auth)])
async def get_sessions(): return list_sessions()

@app.post("/api/sessions/{sid}/kill", dependencies=[Depends(require_auth)])
async def stop_session(sid: str):
    if not await kill_session(sid): raise HTTPException(404, "Not found")
    return {"ok": True}

@app.websocket("/ws/build/{sid}")
async def ws_build(websocket: WebSocket, sid: str):
    # Accept token from cookie or Authorization header (cookie may not cross-origin on WS)
    token = (
        websocket.cookies.get("tao_session")
        or websocket.headers.get("authorization", "").replace("Bearer ", "")
    )
    if not token or not verify_session_token(token):
        await websocket.close(code=4001, reason="Not authenticated")
        return
    await websocket.accept()
    session = get_session(sid)
    if not session:
        await websocket.send_json({"type": "error", "text": "Session not found"})
        await websocket.close()
        return
    last = 0
    try:
        while True:
            current = session.output_lines[last:]
            for line in current:
                await websocket.send_json(line)
            last = len(session.output_lines)
            if session.status not in ("created", "cloning", "building"):
                for line in session.output_lines[last:]:
                    await websocket.send_json(line)
                await websocket.send_json({"type": "done", "text": f"Session {session.status}", "status": session.status})
                break
            await asyncio.sleep(0.15)
    except (WebSocketDisconnect, Exception):
        pass

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def index():
    p = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(p) if os.path.exists(p) else JSONResponse({"status": "Pi CEO running"})

@app.get("/health")
async def health():
    return {"status": "ok"}
