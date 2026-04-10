import asyncio
import json
import os
import logging
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, field_validator
from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from .auth import verify_password, create_session_token, verify_session_token, require_auth, require_rate_limit
from .sessions import create_session, get_session, list_sessions, kill_session, restore_sessions, _sessions, run_build
from .gc import collect_garbage, gc_loop
from .lessons import load_lessons, append_lesson
from .webhook import verify_github_signature, verify_linear_signature, parse_github_event, parse_linear_event, linear_issue_to_brief
from .orchestrator import fan_out
from .cron import list_triggers, create_trigger, delete_trigger, cron_loop
from .autonomy import linear_todo_poller, autonomy_status
from . import config

log = logging.getLogger("pi-ceo.main")

app = FastAPI(title="Pi CEO", docs_url=None, redoc_url=None, openapi_url=None)

# ─── Pydantic request models (RA-515) ─────────────────────────────────────────

class BuildRequest(BaseModel):
    repo_url: str
    brief: str = ""
    model: str = "sonnet"
    evaluator_enabled: bool | None = None
    intent: str = ""

    @field_validator("repo_url")
    @classmethod
    def valid_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("https://", "git@")):
            raise ValueError("repo_url must start with https:// or git@")
        return v

    @field_validator("model")
    @classmethod
    def valid_model(cls, v: str) -> str:
        if v not in ("opus", "sonnet", "haiku"):
            raise ValueError("model must be opus | sonnet | haiku")
        return v


class ParallelBuildRequest(BuildRequest):
    n_workers: int = 2

    @field_validator("n_workers")
    @classmethod
    def valid_workers(cls, v: int) -> int:
        if not (1 <= v <= 8):
            raise ValueError("n_workers must be 1–8")
        return v


class TriggerRequest(BaseModel):
    repo_url: str
    brief: str = ""
    model: str = "sonnet"
    minute: int
    hour: int | None = None

    @field_validator("repo_url")
    @classmethod
    def valid_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("https://", "git@")):
            raise ValueError("repo_url must start with https:// or git@")
        return v

    @field_validator("model")
    @classmethod
    def valid_model(cls, v: str) -> str:
        if v not in ("opus", "sonnet", "haiku"):
            raise ValueError("model must be opus | sonnet | haiku")
        return v

    @field_validator("minute")
    @classmethod
    def valid_minute(cls, v: int) -> int:
        if not (0 <= v <= 59):
            raise ValueError("minute must be 0-59")
        return v

    @field_validator("hour")
    @classmethod
    def valid_hour(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 23):
            raise ValueError("hour must be 0-23")
        return v


class LessonRequest(BaseModel):
    source: str = "manual"
    category: str = "general"
    lesson: str
    severity: str = "info"

    @field_validator("lesson")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("lesson cannot be empty")
        return v.strip()


class ScanRequest(BaseModel):
    project_id: str | None = None
    scan_types: list[Literal["security", "code_quality", "dependencies", "deployment_health"]] | None = None
    dry_run: bool = False
    auto_pr: bool = False  # RA-537: open GitHub PRs for auto-fixable findings


# ─── Resilient background task wrapper (RA-522) ────────────────────────────────

async def _resilient(coro_factory, name: str, restart_delay: float = 10.0):
    """Wrap a background coroutine with crash-recovery and auto-restart."""
    while True:
        try:
            await coro_factory()
        except asyncio.CancelledError:
            log.info("Background task '%s' cancelled", name)
            return
        except Exception as exc:
            log.error("Background task '%s' crashed: %s — restarting in %.0fs", name, exc, restart_delay, exc_info=True)
            await asyncio.sleep(restart_delay)


@app.on_event("startup")
async def on_startup():
    restore_sessions()
    asyncio.create_task(_resilient(lambda: gc_loop(_sessions), "gc_loop"))
    asyncio.create_task(_resilient(cron_loop, "cron_loop"))
    asyncio.create_task(_resilient(linear_todo_poller, "linear_todo_poller"))
    if config.AUTONOMY_ENABLED:
        log.info("Autonomy poller enabled — polling Linear every 5 min for Todo issues")
    else:
        log.info("Autonomy poller DISABLED (TAO_AUTONOMY_ENABLED=0)")
    if not config.ANTHROPIC_API_KEY:
        log.warning(
            "ANTHROPIC_API_KEY is empty — Anthropic SDK calls will fail. "
            "If launched from a terminal running the claude CLI, start with: "
            "source .env.local && uvicorn ..."
        )
    if not config.WEBHOOK_SECRET:
        log.warning("TAO_WEBHOOK_SECRET not set — GitHub webhook endpoint is unprotected")
    if not config.LINEAR_WEBHOOK_SECRET:
        log.warning("TAO_LINEAR_WEBHOOK_SECRET not set — Linear webhook endpoint is unprotected")
    log.info("Pi CEO ready on %s:%s", config.HOST, config.PORT)


@app.on_event("shutdown")
async def on_shutdown():
    """Drain active sessions on SIGTERM (RA-521)."""
    active = [s for s in _sessions.values() if getattr(s, "status", "") in ("created", "cloning", "building", "evaluating")]
    if active:
        log.info("Shutdown: draining %d active sessions", len(active))
        for session in active:
            session.status = "interrupted"
            proc = getattr(session, "process", None)
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass
        await asyncio.sleep(2)
    log.info("Shutdown complete")

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
async def build(body: BuildRequest):
    evaluator_enabled = body.evaluator_enabled if body.evaluator_enabled is not None else config.EVALUATOR_ENABLED
    try:
        session = await create_session(body.repo_url, body.brief, body.model, evaluator_enabled=evaluator_enabled, intent=body.intent)
    except RuntimeError as e:
        raise HTTPException(429, str(e))
    return {"session_id": session.id, "status": session.status}

@app.post("/api/build/parallel", dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def build_parallel(body: ParallelBuildRequest):
    """Fan-out a complex brief across N parallel worker sessions (RA-464)."""
    if not body.brief:
        raise HTTPException(400, "brief required for parallel builds")
    evaluator_enabled = body.evaluator_enabled if body.evaluator_enabled is not None else config.EVALUATOR_ENABLED
    result = await fan_out(body.repo_url, body.brief, n_workers=body.n_workers, model=body.model, intent=body.intent, evaluator_enabled=evaluator_enabled)
    return result

@app.get("/api/sessions", dependencies=[Depends(require_auth)])
async def get_sessions():
    return list_sessions()

@app.post("/api/sessions/{sid}/kill", dependencies=[Depends(require_auth)])
async def stop_session(sid: str):
    if not await kill_session(sid):
        raise HTTPException(404, "Not found")
    return {"ok": True}

@app.get("/api/sessions/{sid}/logs", dependencies=[Depends(require_auth)])
async def stream_session_logs(sid: str, after: int = 0):
    """SSE stream of build log events for a session.

    Query param `after` = index of the last event the client has seen (0 = all).
    Streams existing events immediately, then polls for new ones until terminal.
    """
    session = get_session(sid)
    if not session:
        raise HTTPException(404, "Session not found")

    terminal = {"done", "complete", "failed", "killed"}

    async def generate():
        cursor = after
        while True:
            lines = session.output_lines
            while cursor < len(lines):
                event = lines[cursor]
                yield f"data: {json.dumps({'i': cursor, **event})}\n\n"
                cursor += 1
            if session.status in terminal:
                yield "data: {\"type\":\"done\",\"text\":\"\"}\n\n"
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

@app.post("/api/sessions/{sid}/resume", dependencies=[Depends(require_auth)])
async def resume_session(sid: str):
    """Resume an interrupted session from its last completed phase (GROUP E)."""
    session = get_session(sid)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status != "interrupted":
        raise HTTPException(400, f"Status is '{session.status}', not 'interrupted'")
    last_phase = getattr(session, "last_completed_phase", "")
    if not last_phase:
        raise HTTPException(400, "No phase checkpoint — cannot resume")
    session.status = "building"
    from . import persistence
    persistence.save_session(session)
    asyncio.create_task(run_build(session, resume_from=last_phase))
    return {"session_id": session.id, "resumed_from": last_phase}

def _find_active_session_for_repo(repo_url: str) -> str | None:
    """Return the session ID of the first non-terminal session for repo_url, or None."""
    terminal = {"done", "complete", "failed", "killed", "interrupted"}
    for s in _sessions.values():
        if s.repo_url == repo_url and s.status not in terminal:
            return s.id
    return None


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
        repo_url = event["repo_url"]
        existing_id = _find_active_session_for_repo(repo_url)
        if existing_id:
            log.info("Skipping duplicate webhook for %s — session %s already active", repo_url, existing_id)
            return {"skipped": True, "reason": f"session {existing_id} already active", "session_id": existing_id}
        brief = f"Triggered by GitHub {event['event']} on {event.get('ref', 'unknown')}. Analyze changes, run tests if present, commit fixes."
        try:
            session = await create_session(repo_url, brief, config.EVALUATOR_MODEL)
        except RuntimeError as e:
            raise HTTPException(429, str(e))
        return {"triggered": True, "session_id": session.id, "repo": repo_url, "event": event["event"]}

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
        repo_url = event["repo_url"]
        existing_id = _find_active_session_for_repo(repo_url)
        if existing_id:
            log.info("Skipping duplicate webhook for %s — session %s already active", repo_url, existing_id)
            return {"skipped": True, "reason": f"session {existing_id} already active", "session_id": existing_id}
        brief = linear_issue_to_brief(event)
        linear_issue_id = event.get("issue_id") or None
        try:
            session = await create_session(
                repo_url, brief, config.EVALUATOR_MODEL,
                linear_issue_id=linear_issue_id,
            )
        except RuntimeError as e:
            raise HTTPException(429, str(e))
        return {"triggered": True, "session_id": session.id, "source": "linear", "title": event["title"], "linear_issue_id": linear_issue_id}

    else:
        raise HTTPException(400, "Missing webhook signature header (x-hub-signature-256 or Linear-Signature)")

@app.get("/api/triggers", dependencies=[Depends(require_auth)])
async def get_triggers():
    return list_triggers()

@app.post("/api/triggers", dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def add_trigger(body: TriggerRequest):
    trigger = create_trigger(repo_url=body.repo_url, brief=body.brief, minute=body.minute, hour=body.hour, model=body.model)
    return trigger

@app.delete("/api/triggers/{tid}", dependencies=[Depends(require_auth)])
async def remove_trigger(tid: str):
    if not delete_trigger(tid):
        raise HTTPException(404, "Trigger not found")
    return {"ok": True}

@app.post("/api/scan", dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def trigger_scan(body: ScanRequest):
    """Trigger Pi-SEO autonomous scan for one or all projects."""
    from .scanner import ProjectScanner
    from .triage import TriageEngine

    project_id = body.project_id
    scan_types = [s for s in body.scan_types] if body.scan_types else None
    dry_run = body.dry_run

    scanner = ProjectScanner()
    engine = TriageEngine()

    async def _run() -> dict:
        if project_id:
            projects = scanner.load_projects()
            proj = next((p for p in projects if p["id"] == project_id), None)
            if not proj:
                return {"error": f"project_id '{project_id}' not found"}
            results = await scanner.scan_project(proj, scan_types)
            created = engine.triage(project_id, results, dry_run=dry_run)
            out: dict = {
                "project_id": project_id,
                "scan_results": [
                    {"scan_type": r.scan_type, "findings": len(r.findings), "health_score": r.health_score}
                    for r in results
                ],
                "tickets_created": len(created),
                "dry_run": dry_run,
            }
            if body.auto_pr:
                from .autopr import run_autopr
                out["auto_pr"] = await run_autopr(proj, dry_run=dry_run)
            return out
        else:
            all_results = await scanner.scan_all(scan_types=scan_types)
            all_created = engine.triage_all(all_results, dry_run=dry_run)
            out = {
                "projects_scanned": len(all_results),
                "tickets_created": sum(len(v) for v in all_created.values()),
                "dry_run": dry_run,
                "summary": {
                    pid: {"findings": sum(len(r.findings) for r in results), "tickets": len(all_created.get(pid, []))}
                    for pid, results in all_results.items()
                },
            }
            if body.auto_pr:
                from .autopr import run_autopr_all
                out["auto_pr"] = await run_autopr_all(dry_run=dry_run)
            return out

    asyncio.create_task(_run())
    return {"ok": True, "message": "Scan started — results will be saved to .harness/scan-results/"}


@app.get("/api/projects/health", dependencies=[Depends(require_auth)])
async def projects_health():
    """Return health scores for all projects based on latest scan results."""
    from .scanner import ProjectScanner
    scanner = ProjectScanner()
    return scanner.get_health_summary()


# ─── Monitor endpoints (RA-541) ───────────────────────────────────────────────

class MonitorRequest(BaseModel):
    project_id: str | None = None
    use_agent: bool = False
    dry_run: bool = False


@app.post("/api/monitor", dependencies=[Depends(require_auth)])
async def trigger_monitor(body: MonitorRequest, background_tasks: BackgroundTasks):
    """Run a Pi-SEO monitor cycle (portfolio health + regression detection)."""
    from .agents.pi_seo_monitor import run_monitor_cycle

    async def _run():
        run_monitor_cycle(
            project_id=body.project_id,
            use_agent=body.use_agent,
            dry_run=body.dry_run,
        )

    background_tasks.add_task(_run)
    return {"ok": True, "dry_run": body.dry_run}


@app.get("/api/monitor/digest", dependencies=[Depends(require_auth)])
async def get_monitor_digest():
    """Return the latest monitor digest JSON."""
    import glob as _glob
    digests_root = Path(__file__).parent.parent.parent / ".harness" / "monitor-digests"
    files = sorted(_glob.glob(str(digests_root / "*.json")), reverse=True)
    if not files:
        return {"error": "No monitor digest found"}
    try:
        with open(files[0]) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return {"error": str(exc)}


# ─── Ship Chain pipeline endpoints ───────────────────────────────────────────

class SpecRequest(BaseModel):
    idea: str
    repo_url: str
    pipeline_id: str | None = None
    model: str = "sonnet"


class PlanRequest(BaseModel):
    pipeline_id: str
    model: str = "sonnet"


class TestRequest(BaseModel):
    pipeline_id: str
    session_id: str


class ShipRequest(BaseModel):
    pipeline_id: str


@app.post("/api/spec", dependencies=[Depends(require_auth)])
async def run_spec(body: SpecRequest, background_tasks: BackgroundTasks):
    """Phase 1: Convert a raw idea into a structured spec.md."""
    from .pipeline import run_spec_phase
    import uuid as _uuid

    pipeline_id = body.pipeline_id or _uuid.uuid4().hex[:8]

    def _run():
        try:
            run_spec_phase(body.idea, body.repo_url, pipeline_id=pipeline_id, model=body.model)
        except Exception as exc:
            log.error("Spec phase failed: pipeline=%s err=%s", pipeline_id, exc)

    background_tasks.add_task(_run)
    return {"ok": True, "pipeline_id": pipeline_id}


@app.post("/api/plan", dependencies=[Depends(require_auth)])
async def run_plan(body: PlanRequest, background_tasks: BackgroundTasks):
    """Phase 2: Convert spec.md into a concrete implementation plan.md."""
    from .pipeline import run_plan_phase

    def _run():
        try:
            run_plan_phase(body.pipeline_id, model=body.model)
        except Exception as exc:
            log.error("Plan phase failed: pipeline=%s err=%s", body.pipeline_id, exc)

    background_tasks.add_task(_run)
    return {"ok": True, "pipeline_id": body.pipeline_id}


@app.post("/api/test", dependencies=[Depends(require_auth)])
async def run_test(body: TestRequest, background_tasks: BackgroundTasks):
    """Phase 4: Run smoke tests and record results."""
    from .pipeline import run_test_phase

    def _run():
        try:
            run_test_phase(body.pipeline_id, body.session_id)
        except Exception as exc:
            log.error("Test phase failed: pipeline=%s err=%s", body.pipeline_id, exc)

    background_tasks.add_task(_run)
    return {"ok": True, "pipeline_id": body.pipeline_id}


@app.post("/api/ship", dependencies=[Depends(require_auth)])
async def run_ship(body: ShipRequest):
    """Phase 6: Hard gate + ship. Returns ship-log immediately (synchronous)."""
    from .pipeline import run_ship_phase
    try:
        state = run_ship_phase(body.pipeline_id)
        ship_log = state.ship_log or {}
        return {"ok": ship_log.get("shipped", False), "pipeline_id": body.pipeline_id, "ship_log": ship_log}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/pipeline/{pipeline_id}", dependencies=[Depends(require_auth)])
async def get_pipeline(pipeline_id: str):
    """Return full PipelineState for a pipeline."""
    from .pipeline import load_pipeline_state
    from dataclasses import asdict
    state = load_pipeline_state(pipeline_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")
    return asdict(state)


@app.get("/api/pipelines", dependencies=[Depends(require_auth)])
async def get_pipelines():
    """List all pipeline summaries."""
    from .pipeline import list_pipelines
    return list_pipelines()


@app.post("/api/gc", dependencies=[Depends(require_auth)])
async def run_gc():
    result = collect_garbage(_sessions)
    return result

@app.get("/api/lessons", dependencies=[Depends(require_auth)])
async def get_lessons(category: str | None = None, limit: int = 50):
    return load_lessons(category=category, limit=min(limit, 200))

@app.post("/api/lessons", dependencies=[Depends(require_auth)])
async def post_lesson(body: LessonRequest):
    entry = append_lesson(body.source[:100], body.category[:50], body.lesson, body.severity)
    return entry

@app.get("/api/autonomy/status", dependencies=[Depends(require_auth)])
async def get_autonomy_status():
    """Return current autonomy poller heartbeat + recent pickup events."""
    return autonomy_status()


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

_START_TIME = __import__("time").time()

_claude_ok: bool = False
_claude_check_task: asyncio.Task | None = None

async def _poll_claude_cli() -> None:
    """Check Claude CLI in background every 30s — never blocks health endpoint."""
    global _claude_ok
    while True:
        try:
            proc = await asyncio.create_subprocess_exec(
                config.CLAUDE_CMD, "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
                _claude_ok = proc.returncode == 0
            except asyncio.TimeoutError:
                proc.kill()
                _claude_ok = False
        except Exception:
            _claude_ok = False
        await asyncio.sleep(30)


@app.on_event("startup")
async def _start_claude_poll():
    asyncio.create_task(_resilient(_poll_claude_cli, "claude_cli_poll"))


@app.get("/health")
async def health():
    import time
    import shutil
    uptime_s = int(time.time() - _START_TIME)
    active = sum(1 for s in _sessions.values() if getattr(s, "status", "") in ("created", "cloning", "building", "evaluating"))
    total  = len(_sessions)

    disk_free_gb: float | None = None
    try:
        disk = shutil.disk_usage(config.WORKSPACE_ROOT)
        disk_free_gb = round(disk.free / 1e9, 1)
    except Exception:
        pass

    anthropic_key_ok = bool(config.ANTHROPIC_API_KEY)
    linear_key_ok    = bool(config.LINEAR_API_KEY)
    autonomy_enabled = bool(config.AUTONOMY_ENABLED)

    # Autonomy is considered "armed" only when the flag is on AND the key is present.
    # This is the field the marathon watchdog should read to detect the silent-failure
    # mode where /health says ok but no builds ever fire.
    autonomy_armed = autonomy_enabled and linear_key_ok

    # Expose the poller heartbeat so external monitors can alert on staleness.
    from . import autonomy as _autonomy
    last_poll_at = getattr(_autonomy, "_last_poll_at", 0.0) or 0.0
    poll_count   = getattr(_autonomy, "_poll_count", 0)
    seconds_since_last_poll = int(time.time() - last_poll_at) if last_poll_at else None

    # Server is healthy as long as disk is accessible.
    # claude_cli status is informational — CI runners don't have the CLI installed.
    healthy = disk_free_gb is not None
    payload = {
        "status":           "ok" if healthy else "degraded",
        "uptime_s":         uptime_s,
        "sessions":         {"active": active, "total": total, "max": config.MAX_CONCURRENT_SESSIONS},
        "claude_cli":       _claude_ok,
        "anthropic_key":    anthropic_key_ok,
        "linear_key":       linear_key_ok,
        "autonomy": {
            "enabled":                 autonomy_enabled,
            "armed":                   autonomy_armed,
            "poll_count":              poll_count,
            "seconds_since_last_poll": seconds_since_last_poll,
        },
        "disk_free_gb":     disk_free_gb,
        "version":          "1.0.0",
    }
    return JSONResponse(payload, status_code=200 if healthy else 503)
