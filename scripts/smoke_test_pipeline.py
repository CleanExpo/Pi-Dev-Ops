#!/usr/bin/env python3
"""RA-1154 pipeline smoke. Redeploy settle/respawn: smoke_pipeline_resilience.py."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.smoke_pipeline_assertions import (
    PipelineAssertions,
    apply_terminal as _apply_terminal,
    observe_row as _observe_row,
    observe_stream_event as _observe_stream_event,
)
from scripts.smoke_pipeline_client import Session
from scripts.smoke_pipeline_resilience import (
    Probe,
    classify_session_list,
    find_session,
    is_terminal_status,
    logs_stream_path,
    max_respawns,
    parse_session_list,
    parse_uptime,
    should_respawn,
    wait_until_settled,
    wall_clock_s,
)


PI_CEO_URL     = os.environ.get("PI_CEO_URL", "https://pi-dev-ops-production.up.railway.app").rstrip("/")
PASSWORD       = os.environ.get("DASHBOARD_PASSWORD") or os.environ.get("TAO_PASSWORD") or ""
TARGET_REPO    = os.environ.get("SMOKE_TARGET_REPO", "https://github.com/CleanExpo/Pi-Dev-Ops")
TEST_BRIEF     = os.environ.get(
    "SMOKE_BRIEF",
    "Add a one-line comment to scripts/send_telegram.py explaining that this "
    "file is the single zero-dependency push helper used by cron, CI, and "
    "Claude sessions. Do NOT change any logic. Do not reformat. Full feature "
    "audit first, then make the minimal edit."
)
MAX_WAIT_S     = int(os.environ.get("SMOKE_MAX_WAIT_S", "1200"))  # 20 min


def probe_backend(s: Session) -> Probe:
    health_code, health_body = s.get("/health")
    list_code, list_body = s.get("/api/sessions")
    return Probe(
        http_status=list_code if list_code else health_code,
        sessions=parse_session_list(list_body) if list_code == 200 else None,
        uptime_s=parse_uptime(health_body) if health_code == 200 else None,
        error="" if list_code == 200 else list_body[:120],
    )


def spawn_session(s: Session, pa: PipelineAssertions) -> tuple[str | None, str]:
    code, body = s.post("/api/build", {
        "repo_url": TARGET_REPO,
        "brief":    TEST_BRIEF,
        "intent":   "smoke",
    })
    if code in {0, 401, 502, 503, 504}:
        print(f"[A1] spawn HTTP {code} — treating as redeploy bounce")
        return None, "bouncing" if code != 401 else "auth_stale"
    if code != 200:
        print(f"[A1 FAIL] POST /api/build → HTTP {code}: {body[:200]}")
        pa.fail(f"spawn HTTP {code}")
        return None, "fail"
    try:
        resp = json.loads(body)
    except json.JSONDecodeError:
        pa.fail(f"spawn non-JSON response: {body[:200]}")
        return None, "fail"
    sid = resp.get("session_id") or resp.get("id")
    if not sid:
        pa.fail(f"no session_id in response: {body[:200]}")
        return None, "fail"
    pa.spawned = True
    print(f"[A1 PASS] session spawned: {sid}")
    return sid, "ok"


def watch_stream(s: Session, sid: str, pa: PipelineAssertions, start: float) -> None:
    stream_path = logs_stream_path(sid)
    print(f"[stream] {stream_path}")
    try:
        for event in s.stream(stream_path, timeout_s=MAX_WAIT_S):
            now = time.time() - start
            _observe_stream_event(pa, event, now)
            if event.get("type") == "done" or now > MAX_WAIT_S:
                if now > MAX_WAIT_S:
                    pa.fail(f"stream exceeded MAX_WAIT_S={MAX_WAIT_S}s")
                print(f"  [t+{now:.0f}s] stream ended")
                return
    except Exception as exc:
        print(f"[stream] dropped ({exc}) — will classify via /api/sessions")


def poll_terminal(s: Session, sid: str, pa: PipelineAssertions, start: float) -> str:
    budget = max(60, MAX_WAIT_S - int(time.time() - start))
    print(f"[poll] waiting up to {budget}s for terminal state...")
    deadline = time.time() + budget
    last = "unknown"
    while time.time() < deadline:
        probe = probe_backend(s)
        last = classify_session_list(probe, sid)
        if last != "found":
            return last
        me = find_session(probe.sessions or [], sid)
        if me:
            _observe_row(pa, me, time.time() - start)
            if is_terminal_status(me.get("status")):
                _apply_terminal(pa, me)
                return "terminal"
        time.sleep(15)
    if last == "found":
        pa.fail(f"session still running after {budget}s — polling budget exhausted")
        return "timeout"
    return last


def run_attempts(s: Session) -> tuple[PipelineAssertions, str | None]:
    wall = time.time() + wall_clock_s()
    pa = PipelineAssertions()
    sid: str | None = None
    allowed = max_respawns()
    for attempt in range(1, allowed + 2):
        if not wait_until_settled(
            lambda: probe_backend(s), until=wall, relogin=lambda: s.login(PASSWORD),
        ):
            pa.fail("backend did not settle after Railway bounce")
            return pa, sid
        pa = PipelineAssertions()
        sid, kind = spawn_session(s, pa)
        if should_respawn(kind):
            if attempt <= allowed:
                print(f"[redeploy] spawn {kind}; retry {attempt}/{allowed}")
                continue
            pa.fail(f"spawn kept bouncing after {attempt} attempt(s)")
            return pa, sid
        if kind != "ok" or not sid:
            return pa, sid
        start = time.time()
        watch_stream(s, sid, pa, start)
        outcome = poll_terminal(s, sid, pa, start)
        if should_respawn(outcome) and attempt <= allowed:
            print(f"[redeploy] session {outcome}; respawn {attempt}/{allowed}")
            continue
        if should_respawn(outcome):
            pa.fail(f"session {sid[:8]} wiped by redeploy after {attempt} attempt(s)")
        return pa, sid
    pa.fail(f"could not hold a session through {allowed} respawn(s)")
    return pa, sid


def cleanup_session(s: Session, sid: str | None) -> None:
    if not sid:
        return
    try:
        code, _body = s.post(f"/api/sessions/{sid}/kill", {})
        print(f"[cleanup] kill session → {code}" + (" (acceptable)" if code == 404 else ""))
    except Exception as exc:
        print(f"[cleanup] kill failed: {exc}")


def _print_report(pa: PipelineAssertions) -> int:
    print()
    print("━━━ ASSERTIONS ━━━")
    print(pa.summary())
    if pa.errors:
        print("\n━━━ ERRORS ━━━")
        for err in pa.errors:
            print(f"  ✗ {err}")
    ok = pa.all_passed()
    print()
    print(f"━━━ RESULT: {'PASS' if ok else 'FAIL'} ━━━")
    return 0 if ok else 1


def run_pipeline_smoke() -> int:
    if not PASSWORD:
        print("ERROR: DASHBOARD_PASSWORD (or TAO_PASSWORD) env var required", file=sys.stderr)
        return 2
    print(f"━━━ PIPELINE SMOKE — {PI_CEO_URL}")
    print(f"    Target repo: {TARGET_REPO}")
    print(f"    Max wait:    {MAX_WAIT_S} s")
    print()
    s = Session(PI_CEO_URL)
    if not s.login(PASSWORD):
        print("ERROR: login failed", file=sys.stderr)
        return 2
    pa, sid = run_attempts(s)
    cleanup_session(s, sid)
    return _print_report(pa)


if __name__ == "__main__":
    sys.exit(run_pipeline_smoke())
