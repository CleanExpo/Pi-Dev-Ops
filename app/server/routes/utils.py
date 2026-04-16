"""Utility routes: gc, lessons, autonomy status, WebSocket build stream (RA-937)."""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
import asyncio

from ..auth import require_auth, verify_session_token
from ..sessions import get_session, _sessions
from ..gc import collect_garbage
from ..lessons import load_lessons, append_lesson
from ..autonomy import autonomy_status
from ..models import LessonRequest

router = APIRouter()

# RA-1015: per-session WebSocket connection cap — prevents runaway polling loops
_ws_connections: dict[str, int] = {}
_ws_lock = asyncio.Lock()
_WS_MAX_PER_SESSION = 5


@router.post("/api/gc", dependencies=[Depends(require_auth)])
async def run_gc():
    result = collect_garbage(_sessions)
    return result


@router.get("/api/lessons", dependencies=[Depends(require_auth)])
async def get_lessons(category: str | None = None, limit: int = 50):
    return load_lessons(category=category, limit=min(limit, 200))


@router.post("/api/lessons", dependencies=[Depends(require_auth)])
async def post_lesson(body: LessonRequest):
    entry = append_lesson(body.source[:100], body.category[:50], body.lesson, body.severity)
    return entry


@router.get("/api/autonomy/status", dependencies=[Depends(require_auth)])
async def get_autonomy_status():
    """Return current autonomy poller heartbeat + recent pickup events."""
    return autonomy_status()


@router.websocket("/ws/build/{sid}")
async def ws_build(websocket: WebSocket, sid: str):
    # Accept token from cookie or Authorization header (cookie may not cross-origin on WS)
    token = (
        websocket.cookies.get("tao_session")
        or websocket.headers.get("authorization", "").replace("Bearer ", "")
    )
    if not token or not verify_session_token(token):
        await websocket.close(code=4001, reason="Not authenticated")
        return

    # RA-1015: enforce per-session connection cap before accepting
    async with _ws_lock:
        count = _ws_connections.get(sid, 0)
        if count >= _WS_MAX_PER_SESSION:
            await websocket.close(code=1008, reason="Too many connections for this session")
            return
        _ws_connections[sid] = count + 1

    await websocket.accept()
    try:
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
    finally:
        # RA-1015: always decrement on disconnect, even on error paths
        async with _ws_lock:
            remaining = _ws_connections.get(sid, 1) - 1
            if remaining <= 0:
                _ws_connections.pop(sid, None)
            else:
                _ws_connections[sid] = remaining
