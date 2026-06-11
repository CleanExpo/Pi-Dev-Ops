"""Session routes: build, list, kill, SSE logs, resume (RA-937).

RA-6504: Added GET /api/sessions/{sid}/logs/stream — a hardened SSE endpoint
that replays existing output_lines, polls for new lines until terminal state,
emits heartbeat comments every 15 s to keep proxies alive, and sends an
explicit "truncated" event when the replay window exceeds the cap.
"""
import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import require_auth, require_rate_limit
from ..sessions import create_session, get_session, list_sessions, kill_session, _sessions, run_build
from ..orchestrator import fan_out
from ..models import BuildRequest, ParallelBuildRequest
from .. import config, persistence
from ..persistence import _safe_sid

router = APIRouter()


@router.post("/api/build", dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def build(body: BuildRequest):
    evaluator_enabled = body.evaluator_enabled if body.evaluator_enabled is not None else config.EVALUATOR_ENABLED
    # RA-677: per-request budget overrides global default; global default overrides None
    budget = body.budget_minutes or config.AUTONOMY_BUDGET_MINS or None
    try:
        session = await create_session(
            body.repo_url, body.brief, body.model,
            evaluator_enabled=evaluator_enabled,
            intent=body.intent,
            budget_minutes=budget,
            scope=body.scope,                       # RA-676: session scope contract
            plan_discovery=body.plan_discovery,     # RA-679: plan variation discovery
            complexity_tier=body.complexity_tier,   # RA-681: brief tier override
        )
    except RuntimeError as e:
        raise HTTPException(429, str(e))
    return {"session_id": session.id, "status": session.status}


@router.post("/api/build/parallel", dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def build_parallel(body: ParallelBuildRequest):
    """Fan-out a complex brief across N parallel worker sessions (RA-464)."""
    if not body.brief:
        raise HTTPException(400, "brief required for parallel builds")
    evaluator_enabled = body.evaluator_enabled if body.evaluator_enabled is not None else config.EVALUATOR_ENABLED
    # RA-1021: enforce server-side cap regardless of model validation path.
    n_workers = min(body.n_workers, 10)
    result = await fan_out(
        body.repo_url, body.brief,
        n_workers=n_workers, model=body.model,
        intent=body.intent, evaluator_enabled=evaluator_enabled,
    )
    return result


def _find_active_session_for_repo(repo_url: str) -> str | None:
    """Return the session ID of the first non-terminal session for repo_url, or None."""
    terminal = {"done", "complete", "failed", "killed", "interrupted"}
    for s in _sessions.values():
        if s.repo_url == repo_url and s.status not in terminal:
            return s.id
    return None


@router.get("/api/sessions", dependencies=[Depends(require_auth)])
async def get_sessions():
    return list_sessions()


@router.get("/api/sessions/persistence", dependencies=[Depends(require_auth)])
async def sessions_persistence_status():
    """RA-1376: Persistence state observable.

    Returns the number of session JSON files on disk vs sessions held
    in memory.  A mismatch (file_count > memory_count) means sessions
    survived a restart that have not yet been GC'd.  Consumed by /health
    dashboards and the autonomy watchdog.
    """
    disk_sessions = persistence.load_all_sessions()
    return {
        "file_count": len(disk_sessions),
        "memory_count": len(_sessions),
        "sessions_dir": persistence._sessions_dir(),
    }


@router.post("/api/sessions/{sid}/kill", dependencies=[Depends(require_auth)])
async def stop_session(sid: str):
    if not await kill_session(sid):
        raise HTTPException(404, "Not found")
    return {"ok": True}


_SSE_AFTER_MAX = 100_000
_SSE_TERMINAL_TIMEOUT = 300.0  # seconds before closing a completed session's SSE


@router.get("/api/sessions/{sid}/logs", dependencies=[Depends(require_auth)])
async def stream_session_logs(sid: str, after: int = 0):
    """SSE stream of build log events for a session.

    Query param `after` = index of the last event the client has seen (0 = all).
    Clamped to [0, 100_000] (RA-1022).
    Streams existing events immediately, then polls for new ones until terminal.
    Sessions that have been in a terminal state for >5 minutes are closed with
    a final "closed" event rather than polling indefinitely (RA-1022).
    """
    # RA-1022: clamp unbounded `after` parameter
    after = min(max(after, 0), _SSE_AFTER_MAX)

    session = get_session(sid)
    if not session:
        raise HTTPException(404, "Session not found")

    terminal = {"done", "complete", "failed", "killed"}

    async def generate():
        cursor = after
        terminal_since: float | None = None
        while True:
            lines = session.output_lines
            while cursor < len(lines):
                event = lines[cursor]
                yield f"data: {json.dumps({'i': cursor, **event})}\n\n"
                cursor += 1
            if session.status in terminal:
                # RA-1022: track when the session first entered a terminal state
                if terminal_since is None:
                    terminal_since = time.monotonic()
                elapsed = time.monotonic() - terminal_since
                if elapsed >= _SSE_TERMINAL_TIMEOUT:
                    yield "data: {\"type\":\"closed\",\"reason\":\"session_complete\"}\n\n"
                    break
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


_SSE_STREAM_REPLAY_MAX = 5_000   # max lines replayed before emitting "truncated"
_SSE_STREAM_HEARTBEAT_S = 15.0   # SSE comment heartbeat interval (proxy keep-alive)
_SSE_STREAM_POLL_S = 0.3         # poll interval while session is active
_SSE_STREAM_TERMINAL = frozenset({"done", "complete", "failed", "killed", "interrupted"})


@router.get("/api/sessions/{sid}/logs/stream", dependencies=[Depends(require_auth)])
async def stream_session_logs_v2(sid: str, after: int = 0):
    """SSE build-log stream with heartbeat, truncation event, and reconnect support (RA-6504).

    Contract
    --------
    • ``after`` — 0-based index of the last line the client already has.  The
      server sends lines[after:] on connect, then polls until the session reaches
      a terminal state.  Clamped to [0, _SSE_AFTER_MAX] to prevent abuse.
    • Heartbeat — an SSE comment line (": heartbeat") is emitted every
      ~15 s while the generator is idle so that Vercel/nginx proxies do not
      close the connection.
    • Truncation — when ``after`` is 0 and there are more than
      ``_SSE_STREAM_REPLAY_MAX`` existing lines the endpoint first emits a
      ``truncated`` event (with the count of skipped lines), then replays only
      the most-recent ``_SSE_STREAM_REPLAY_MAX`` lines.  This prevents the
      initial burst from OOM-ing the client.
    • Terminal event — a ``{"type":"done","status":"<status>"}`` event is emitted
      immediately when the session enters a terminal state, then the stream is
      closed.  The client MUST poll ``GET /api/sessions`` as the authoritative
      source of truth for session state; the SSE stream is best-effort.
    • The ``sid`` is sanitised via ``_safe_sid()`` before use (path-traversal
      guard, same as the persistence layer).

    Reconnect doctrine (Vercel SSE proxy drops)
    --------------------------------------------
    Clients SHOULD use the ``Last-Event-ID`` or ``after`` query-param pattern:
    track the highest ``i`` value received, reconnect with ``?after=<i>``, and
    continue to poll ``/api/sessions`` as the source of truth while the stream
    is disconnected.  The UI build-strip follows this doctrine.
    """
    # Sanitise before _any_ use — mirrors persistence._safe_sid() guard.
    safe = _safe_sid(sid)
    if not safe:
        raise HTTPException(400, "Invalid session ID")

    # Clamp after to [0, _SSE_AFTER_MAX]
    after = min(max(after, 0), _SSE_AFTER_MAX)

    session = get_session(sid)
    if session is None:
        raise HTTPException(404, "Session not found")

    async def generate():
        cursor = after
        last_heartbeat = time.monotonic()

        # ── Truncation guard ──────────────────────────────────────────────────
        total_existing = len(session.output_lines)
        if cursor == 0 and total_existing > _SSE_STREAM_REPLAY_MAX:
            skipped = total_existing - _SSE_STREAM_REPLAY_MAX
            truncation_event = json.dumps({
                "type": "truncated",
                "skipped": skipped,
                "replay_from": skipped,
            })
            yield f"data: {truncation_event}\n\n"
            cursor = skipped

        # ── Main loop: replay + poll ──────────────────────────────────────────
        while True:
            lines = session.output_lines

            # Drain available lines
            while cursor < len(lines):
                event = lines[cursor]
                yield f"data: {json.dumps({'i': cursor, **event})}\n\n"
                cursor += 1
                last_heartbeat = time.monotonic()  # reset on any data sent

            # Terminal state: emit done event and close
            if session.status in _SSE_STREAM_TERMINAL:
                terminal_event = json.dumps({
                    "type": "done",
                    "status": session.status,
                    "lines": cursor,
                })
                yield f"data: {terminal_event}\n\n"
                break

            # Heartbeat comment — keeps proxy connections alive
            now = time.monotonic()
            if now - last_heartbeat >= _SSE_STREAM_HEARTBEAT_S:
                yield ": heartbeat\n\n"
                last_heartbeat = now

            await asyncio.sleep(_SSE_STREAM_POLL_S)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/sessions/{sid}/resume", dependencies=[Depends(require_auth)])
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
    persistence.save_session(session)
    asyncio.create_task(run_build(session, resume_from=last_phase))
    return {"session_id": session.id, "resumed_from": last_phase}
