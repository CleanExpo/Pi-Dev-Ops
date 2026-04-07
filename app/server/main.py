import asyncio, json, os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from .auth import verify_password, create_session_token, verify_session_token, require_auth, require_rate_limit
from .sessions import create_session, get_session, list_sessions, kill_session, restore_sessions, _sessions
from .gc import collect_garbage, gc_loop
from .lessons import load_lessons, append_lesson
from .webhook import verify_github_signature, verify_linear_signature, parse_github_event, parse_linear_event, linear_issue_to_brief
from . import config

app = FastAPI(title="Pi CEO", docs_url=None, redoc_url=None, openapi_url=None)

@app.on_event("startup")
async def on_startup():
    restore_sessions()
    asyncio.create_task(gc_loop(_sessions))
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
    evaluator_enabled = body.get("evaluator_enabled", config.EVALUATOR_ENABLED)
    intent = body.get("intent", "").strip()
    if not repo_url: raise HTTPException(400, "repo_url required")
    if not repo_url.startswith(("https://", "git@")): raise HTTPException(400, "Invalid URL")
    if model not in config.ALLOWED_MODELS: raise HTTPException(400, f"model must be {config.ALLOWED_MODELS}")
    try: session = await create_session(repo_url, brief, model, evaluator_enabled=evaluator_enabled, intent=intent)
    except RuntimeError as e: raise HTTPException(429, str(e))
    return {"session_id": session.id, "status": session.status}

@app.get("/api/sessions", dependencies=[Depends(require_auth)])
async def get_sessions(): return list_sessions()

@app.post("/api/sessions/{sid}/kill", dependencies=[Depends(require_auth)])
async def stop_session(sid: str):
    if not await kill_session(sid): raise HTTPException(404, "Not found")
    return {"ok": True}

@app.post("/api/webhook", dependencies=[Depends(require_rate_limit)])
async def webhook(request: Request):
    raw_body = await request.body()
    gh_event = request.headers.get("x-github-event", "")
    gh_sig = request.headers.get("x-hub-signature-256", "")
    linear_sig = request.headers.get("linear-signature", "")

    if gh_event and gh_sig:
        # GitHub webhook
        if not config.WEBHOOK_SECRET:
            raise HTTPException(500, "Webhook secret not configured")
        if not verify_github_signature(raw_body, gh_sig, config.WEBHOOK_SECRET):
            raise HTTPException(401, "Invalid signature")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid JSON")
        event = parse_github_event(gh_event, payload)
        if not event:
            return {"skipped": True, "reason": f"Unsupported event: {gh_event}"}
        brief = f"Triggered by GitHub {event['event']} on {event.get('ref', 'unknown')}. Analyze changes, run tests if present, commit fixes."
        try:
            session = await create_session(event["repo_url"], brief, config.EVALUATOR_MODEL)
        except RuntimeError as e:
            raise HTTPException(429, str(e))
        return {"triggered": True, "session_id": session.id, "repo": event["repo_url"], "event": event["event"]}

    elif linear_sig:
        # Linear webhook
        if not config.LINEAR_WEBHOOK_SECRET:
            raise HTTPException(500, "Linear webhook secret not configured")
        if not verify_linear_signature(raw_body, linear_sig, config.LINEAR_WEBHOOK_SECRET):
            raise HTTPException(401, "Invalid signature")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid JSON")
        event = parse_linear_event(payload)
        if not event:
            return {"skipped": True, "reason": "Not an issue-started event"}
        if not event.get("repo_url"):
            return {"skipped": True, "reason": "No repo URL found in issue (add repo:<url> label)"}
        brief = linear_issue_to_brief(event)
        try:
            session = await create_session(event["repo_url"], brief, config.EVALUATOR_MODEL)
        except RuntimeError as e:
            raise HTTPException(429, str(e))
        return {"triggered": True, "session_id": session.id, "source": "linear", "title": event["title"]}

    else:
        raise HTTPException(400, "Missing webhook signature header (x-hub-signature-256 or Linear-Signature)")

@app.post("/api/gc", dependencies=[Depends(require_auth)])
async def run_gc():
    result = collect_garbage(_sessions)
    return result

@app.get("/api/lessons", dependencies=[Depends(require_auth)])
async def get_lessons(category: str | None = None, limit: int = 50):
    return load_lessons(category=category, limit=min(limit, 200))

@app.post("/api/lessons", dependencies=[Depends(require_auth)])
async def post_lesson(request: Request):
    body = await request.json()
    source = str(body.get("source", "manual"))[:100]
    category = str(body.get("category", "general"))[:50]
    lesson = str(body.get("lesson", "")).strip()
    severity = str(body.get("severity", "info"))
    if not lesson:
        raise HTTPException(400, "lesson required")
    entry = append_lesson(source, category, lesson, severity)
    return entry

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
            if session.status not in ("created", "cloning", "building", "evaluating"):
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
