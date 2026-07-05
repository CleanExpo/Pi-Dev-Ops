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


# RA-1099 Wave-3: surface the Fable-5 adversary-canary amplification so a daily
# job can watch it (the sdk-metrics jsonl is ephemeral on the Railway container).
_CANARY_KILL_THRESHOLD = 1100.0  # billed output tokens / 1k visible chars on adversary runs


@router.get("/api/canary/fable", dependencies=[Depends(require_auth)])
async def get_fable_canary():
    """Amplification summary for the Fable-5 adversary canary over the last 7 days."""
    import glob
    import json
    import os
    import statistics
    from pathlib import Path

    metrics_dir = Path(__file__).resolve().parents[3] / ".harness" / "agent-sdk-metrics"
    amps: list[float] = []
    fable_runs = refusals = 0
    for fp in sorted(glob.glob(str(metrics_dir / "*.jsonl")))[-7:]:
        try:
            for line in open(fp, encoding="utf-8"):
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("phase") != "adversary" or "fable" not in str(r.get("model", "")):
                    continue
                fable_runs += 1
                if r.get("stop_reason") == "refusal" or r.get("error") == "refusal":
                    refusals += 1
                ot, olen = r.get("output_tokens"), r.get("output_len")
                if ot and olen:
                    amps.append(ot / (olen / 1000.0))
        except OSError:
            continue
    median_amp = round(statistics.median(amps), 1) if amps else None
    armed = "adversary" in os.environ.get("TAO_FABLE_ALLOWED_ROLES", "")
    breached = median_amp is not None and median_amp > _CANARY_KILL_THRESHOLD
    return {
        "armed": armed,
        "fable_adversary_runs_7d": fable_runs,
        "refusals_7d": refusals,
        "median_amplification": median_amp,
        "kill_threshold": _CANARY_KILL_THRESHOLD,
        "breached": breached,
        "status": "DISARMED" if not armed else "BREACH" if breached else "OK",
    }


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
