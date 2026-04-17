#!/usr/bin/env python3
"""
smoke_test_e2e.py — RA-1154 — horizontal + vertical smoke tests against live prod.

Companion to the existing scripts/smoke_test.py (which runs against a
locally-booted server during CI). This variant hits the live Vercel deploy
to verify the WHOLE stack — Vercel routing + proxy + Railway backend — which
is what users actually touch.

Reads `.github/smoke-surfaces.json` declaratively so PR authors add their
new surfaces to the map rather than editing test code. A CI gate
(`.github/workflows/smoke_surface_gate.yml`) fails PRs touching
`dashboard/components/**` or `app/server/routes/**` without updating the map.

Two modes:
    --mode=horizontal   Breadth: probe every endpoint once, assert status + shape
    --mode=vertical     Depth: one full build-lifecycle flow with SSE streaming
    --mode=full         Both (default)

Exit codes:
    0 — all passed
    1 — at least one failure
    2 — config error (missing env vars, malformed surface map, etc.)

Env:
    DASHBOARD_URL       Base Vercel URL (default: https://pi-dev-ops.vercel.app)
    DASHBOARD_PASSWORD  Password for /api/auth/login (from Vercel env)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACE_MAP_PATH = REPO_ROOT / ".github" / "smoke-surfaces.json"


# ── Test result tracking ───────────────────────────────────────────────────
@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""
    duration_ms: int = 0


@dataclass
class TestRun:
    results: list[TestResult] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str = "", duration_ms: int = 0) -> bool:
        self.results.append(TestResult(name, ok, detail, duration_ms))
        icon = "✓" if ok else "✗"
        suffix = f" ({duration_ms} ms)" if duration_ms else ""
        print(f"  {icon} {name}{suffix}" + (f" — {detail}" if detail and not ok else ""))
        return ok

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def summary(self) -> str:
        total = len(self.results)
        return f"{self.passed_count}/{total} passed · {self.failed_count} failed"


# ── HTTP helpers (stdlib only so no extra deps in CI) ──────────────────────
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Treat 3xx as a terminal response so we can assert on redirect status codes."""

    def http_error_301(self, req, fp, code, msg, headers):  # noqa: D401, ARG002
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

    http_error_302 = http_error_301
    http_error_303 = http_error_301
    http_error_307 = http_error_301
    http_error_308 = http_error_301


class Session:
    """Minimal HTTP session with cookie jar, for preserving pi_session after login."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            _NoRedirect(),
        )

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        timeout: float = 15.0,
    ) -> tuple[int, str]:
        url = self.base_url + path
        data = None
        headers = {"User-Agent": "pi-ceo-smoke-e2e/1.0"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors="replace") if e.fp else ""
        except urllib.error.URLError as e:
            return 0, f"URLError: {e}"

    def login(self, password: str) -> bool:
        status, _ = self.request("POST", "/api/auth/login", body={"password": password})
        return status == 200


# ── Surface map loader (stdlib only — JSON) ────────────────────────────────
def _load_surface_map() -> dict:
    if not SURFACE_MAP_PATH.is_file():
        print(f"[fatal] {SURFACE_MAP_PATH} not found", file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(SURFACE_MAP_PATH.read_text())
    except json.JSONDecodeError as exc:
        print(f"[fatal] {SURFACE_MAP_PATH}: invalid JSON — {exc}", file=sys.stderr)
        sys.exit(2)


# ── Horizontal: probe every endpoint once ──────────────────────────────────
def run_horizontal(session: Session, password: str, surfaces: list[dict]) -> TestRun:
    run = TestRun()
    print("\n━━━ HORIZONTAL ━━━ probe every declared endpoint once")

    # Run `auth: false` surfaces first — BEFORE login, so the cookie jar is
    # empty and redirect checks behave as a fresh browser. Then log in once,
    # then run `auth: true` surfaces. Order within each bucket preserved.
    unauth_surfaces = [s for s in surfaces if not s.get("auth")]
    auth_surfaces   = [s for s in surfaces if s.get("auth")]

    def probe(surface: dict) -> None:
        name = surface.get("name", "unnamed")
        path = surface["path"]
        method = surface.get("method", "GET").upper()
        expected_status = surface.get("expected_status", 200)
        body = surface.get("body")
        body_contains: list[str] = surface.get("body_contains", []) or []

        t0 = time.perf_counter()
        status, resp_body = session.request(method, path, body=body)
        dt_ms = int((time.perf_counter() - t0) * 1000)

        ok = status == expected_status
        run.check(f"[{name}] {method} {path[:60]} → {status}",
                  ok, f"expected {expected_status}, got {status}", dt_ms)

        if ok and body_contains:
            missing = [s for s in body_contains if s not in resp_body]
            run.check(f"[{name}] body contains expected strings", not missing,
                      f"missing: {missing}" if missing else "")

    # Phase A — unauthenticated probes (cookie jar empty)
    for s in unauth_surfaces:
        probe(s)

    # Phase B — authenticate once, then run auth:true probes
    login_ok = session.login(password)
    run.check("cookie issued by login", login_ok, "POST /api/auth/login")

    for s in auth_surfaces:
        probe(s)

    return run


# ── Vertical: one full flow across the stack ───────────────────────────────
def run_vertical(session: Session, password: str, flow_spec: dict) -> TestRun:
    run = TestRun()
    flow = flow_spec.get("flow", "unknown")
    print(f"\n━━━ VERTICAL ━━━ {flow} across Vercel → proxy → Railway")

    # Shared state across steps (e.g. session_id from a POST is used in SSE URL)
    state: dict[str, str] = {}
    steps = flow_spec.get("steps") or []

    for i, step in enumerate(steps, 1):
        action = step.get("action", "")
        expected = step.get("expected", {}) or {}

        if action == "login":
            t0 = time.perf_counter()
            ok = session.login(password)
            dt = int((time.perf_counter() - t0) * 1000)
            run.check(f"step {i} login", ok, "POST /api/auth/login", dt)

        elif action in ("get", "post", "delete"):
            # Support either literal `path` or `path_template` (rendered with state)
            if "path" in step:
                path = step["path"]
            elif "path_template" in step:
                path = step["path_template"].format(**state)
            else:
                run.check(f"step {i} {action}", False, "missing path or path_template")
                return run
            body = step.get("body")
            t0 = time.perf_counter()
            status, resp_body = session.request(action.upper(), path, body=body)
            dt = int((time.perf_counter() - t0) * 1000)

            expected_status = expected.get("status", 200)
            ok = status == expected_status
            run.check(f"step {i} {action.upper()} {path[:60]} → {status}",
                      ok, f"expected {expected_status}, got {status}: {resp_body[:120]}", dt)

            if not ok:
                return run  # Abort subsequent steps if one fails

            # Extract session_id for downstream steps if response has one
            for key in ("session_id", "id"):
                try:
                    parsed = json.loads(resp_body)
                    if isinstance(parsed, dict) and key in parsed:
                        state["session_id"] = str(parsed[key])
                        break
                except (json.JSONDecodeError, TypeError):
                    pass

            # body_contains check
            body_contains: list[str] = expected.get("body_contains", []) or []
            if body_contains:
                missing = [s for s in body_contains if s not in resp_body]
                run.check(f"step {i} body contains", not missing,
                          f"missing: {missing}" if missing else "")

        elif action == "sse":
            # Open SSE, count events, verify we get N events within timeout
            tpl = step.get("path_template", "")
            path = tpl.format(**state)
            min_events = expected.get("min_events", 1)
            timeout_s = expected.get("timeout_s", 30)
            ok = _probe_sse(session, path, min_events, timeout_s, run, i)
            if not ok:
                return run

        elif action == "kill":
            tpl = step.get("path_template", "")
            path = tpl.format(**state)
            expected_status = expected.get("status", 200)
            t0 = time.perf_counter()
            status, _ = session.request("POST", path)
            dt = int((time.perf_counter() - t0) * 1000)
            # 200 OR 404 (already finished) are both acceptable
            ok = status in (expected_status, 404)
            run.check(f"step {i} kill session → {status}", ok,
                      f"expected {expected_status} or 404", dt)

        else:
            run.check(f"step {i} unknown action {action}", False, "typo in surface map?")

    return run


def _probe_sse(
    session: Session,
    path: str,
    min_events: int,
    timeout_s: int,
    run: TestRun,
    step_num: int,
) -> bool:
    """Open an SSE stream and count 'data:' events until min_events or timeout."""
    url = session.base_url + path
    # Re-use session cookies via the opener
    req = urllib.request.Request(
        url,
        headers={"Accept": "text/event-stream", "User-Agent": "pi-ceo-smoke-e2e/1.0"},
    )

    t0 = time.perf_counter()
    event_count = 0
    try:
        with session.opener.open(req, timeout=timeout_s) as resp:
            for raw_line in resp:
                line = raw_line.decode(errors="replace").strip()
                if line.startswith("data:"):
                    event_count += 1
                if event_count >= min_events:
                    break
                if (time.perf_counter() - t0) > timeout_s:
                    break
    except (urllib.error.URLError, OSError) as exc:
        run.check(f"step {step_num} SSE {path[:60]}", False,
                  f"connection error: {exc}", int((time.perf_counter() - t0) * 1000))
        return False

    dt_ms = int((time.perf_counter() - t0) * 1000)
    ok = event_count >= min_events
    run.check(
        f"step {step_num} SSE {path[:60]} got {event_count} events",
        ok,
        f"expected ≥{min_events} within {timeout_s}s",
        dt_ms,
    )
    return ok


# ── Entry point ────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Full-stack smoke test (RA-1154)")
    parser.add_argument("--mode", choices=["horizontal", "vertical", "full"], default="full")
    parser.add_argument("--url", default=os.environ.get("DASHBOARD_URL", "https://pi-dev-ops.vercel.app"))
    parser.add_argument("--password", default=os.environ.get("DASHBOARD_PASSWORD", ""))
    args = parser.parse_args()

    if not args.password:
        print("[fatal] --password or DASHBOARD_PASSWORD env var required", file=sys.stderr)
        return 2

    surface_map = _load_surface_map()
    session = Session(args.url)

    print(f"Target: {args.url}")
    print(f"Mode:   {args.mode}")

    all_runs: list[TestRun] = []

    if args.mode in ("horizontal", "full"):
        horizontal_surfaces = surface_map.get("horizontal", []) or []
        if horizontal_surfaces:
            all_runs.append(run_horizontal(session, args.password, horizontal_surfaces))

    if args.mode in ("vertical", "full"):
        vertical = surface_map.get("vertical")
        if vertical:
            all_runs.append(run_vertical(session, args.password, vertical))

    total_passed = sum(r.passed_count for r in all_runs)
    total_failed = sum(r.failed_count for r in all_runs)

    print()
    print("═" * 60)
    print(f"TOTAL: {total_passed} passed · {total_failed} failed")
    print("═" * 60)

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
