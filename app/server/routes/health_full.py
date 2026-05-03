"""
health_full.py — RA-1910 phase 1.

End-to-end health snapshot at /api/health/full. Aggregates seven component
checks in parallel (≤2s each, ≤2s total) and returns a structured payload
suitable for an external pinger or status page.

Public route — no auth — must be reachable by external pingers/UptimeRobot.
Returns 200 when every component is green, 503 when any component is red.
Each component check catches its own exceptions; one broken probe never
fails the endpoint.
"""
from __future__ import annotations

import asyncio
import datetime
import glob
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse


log = logging.getLogger("pi-ceo.health_full")

PROCESS_START_TIME = time.time()

router = APIRouter()

_HARNESS = Path(__file__).resolve().parent.parent.parent.parent / ".harness"

_CHECK_TIMEOUT_S = 2.0


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()


def _now_iso() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat()


async def _check_hermes_gateway() -> dict[str, Any]:
    try:
        path = _HARNESS / "hermes" / "heartbeat.jsonl"
        if not path.exists():
            return {"ok": False, "error": "no_heartbeat_file"}
        last_line = ""
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    last_line = line
        if not last_line:
            return {"ok": False, "error": "empty_heartbeat"}
        rec = json.loads(last_line)
        ts = rec.get("ts") or rec.get("last_seen") or rec.get("timestamp")
        if isinstance(ts, str):
            try:
                last_seen_ts = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except Exception:
                last_seen_ts = path.stat().st_mtime
        elif isinstance(ts, (int, float)):
            last_seen_ts = float(ts)
        else:
            last_seen_ts = path.stat().st_mtime
        age_s = time.time() - last_seen_ts
        return {"ok": age_s < 5 * 60, "last_seen": _iso(last_seen_ts)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


async def _check_pi_ceo_railway() -> dict[str, Any]:
    try:
        sha = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")
        uptime_s = int(time.time() - PROCESS_START_TIME)
        return {"ok": True, "deploy_sha": sha, "uptime_s": uptime_s}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


async def _check_margot_route() -> dict[str, Any]:
    try:
        pattern = str(_HARNESS / "margot" / "conversations" / "*.jsonl")
        files = glob.glob(pattern)
        if not files:
            return {"ok": True, "last_turn_at": None, "note": "no_conversations_yet"}
        newest = max(files, key=lambda p: os.path.getmtime(p))
        mtime = os.path.getmtime(newest)
        age_h = (time.time() - mtime) / 3600
        return {"ok": age_h < 24, "last_turn_at": _iso(mtime)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


async def _check_mcp_pi_ceo() -> dict[str, Any]:
    try:
        candidate = Path(__file__).resolve().parent.parent.parent.parent / "mcp" / "pi-ceo-server.js"
        tools_count: int | None = None
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8", errors="replace")
            tools_count = text.count("name:") if "name:" in text else None
        return {"ok": True, "tools_count": tools_count}
    except Exception as exc:
        return {"ok": True, "tools_count": None, "error": str(exc)[:120]}


async def _check_openrouter() -> dict[str, Any]:
    try:
        path = _HARNESS / "llm-cost.jsonl"
        if not path.exists():
            return {"ok": True, "last_call_at": None, "note": "no_log_file"}
        last_line = ""
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    last_line = line
        if not last_line:
            return {"ok": True, "last_call_at": None, "note": "empty_log"}
        try:
            rec = json.loads(last_line)
            ts = rec.get("ts") or rec.get("timestamp")
            if isinstance(ts, str):
                last_ts = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            elif isinstance(ts, (int, float)):
                last_ts = float(ts)
            else:
                last_ts = path.stat().st_mtime
        except Exception:
            last_ts = path.stat().st_mtime
        return {"ok": True, "last_call_at": _iso(last_ts)}
    except Exception as exc:
        return {"ok": True, "last_call_at": None, "error": str(exc)[:120]}


async def _check_supabase() -> dict[str, Any]:
    try:
        try:
            from .. import supabase_log  # noqa: PLC0415
        except Exception as exc:
            return {"ok": True, "note": "supabase_log_import_failed", "error": str(exc)[:120]}
        fn = getattr(supabase_log, "health_check", None)
        if not callable(fn):
            return {"ok": True, "note": "untested"}
        if asyncio.iscoroutinefunction(fn):
            ok = bool(await fn())
        else:
            ok = bool(fn())
        return {"ok": ok}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


async def _check_telegram_polling() -> dict[str, Any]:
    try:
        path = _HARNESS / "telegram-poll-heartbeat"
        if not path.exists():
            return {"ok": True, "note": "no_heartbeat_file"}
        mtime = path.stat().st_mtime
        age_s = time.time() - mtime
        return {"ok": age_s < 2 * 60, "last_seen": _iso(mtime)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


_CHECKS: dict[str, Any] = {
    "hermes_gateway":   _check_hermes_gateway,
    "pi_ceo_railway":   _check_pi_ceo_railway,
    "margot_route":     _check_margot_route,
    "mcp_pi_ceo":       _check_mcp_pi_ceo,
    "openrouter":       _check_openrouter,
    "supabase":         _check_supabase,
    "telegram_polling": _check_telegram_polling,
}


async def _run_with_timeout(name: str, coro_fn) -> tuple[str, dict[str, Any]]:
    try:
        result = await asyncio.wait_for(coro_fn(), timeout=_CHECK_TIMEOUT_S)
        if not isinstance(result, dict):
            return name, {"ok": False, "error": "non_dict_result"}
        if "ok" not in result:
            result["ok"] = False
        return name, result
    except asyncio.TimeoutError:
        return name, {"ok": False, "error": "timeout"}
    except Exception as exc:
        return name, {"ok": False, "error": str(exc)[:120]}


async def gather_components() -> dict[str, dict[str, Any]]:
    """Run every component probe in parallel and return name → payload map."""
    pairs = await asyncio.gather(*[
        _run_with_timeout(name, fn) for name, fn in _CHECKS.items()
    ])
    return {name: payload for name, payload in pairs}


@router.get("/api/health/full")
async def health_full() -> JSONResponse:
    components = await gather_components()
    all_ok = all(bool(v.get("ok")) for v in components.values())
    body = {
        "ok": all_ok,
        "components": components,
        "last_full_check": _now_iso(),
    }
    status_code = 200 if all_ok else 503
    return JSONResponse(content=body, status_code=status_code)
