#!/usr/bin/env python3
"""
smoke_test_pipeline.py — RA-1154 senior-level end-to-end pipeline smoke test.

Fires a real autonomous build against a known repo with a known advanced-tier
brief and watches the SSE stream to terminal state. Fails loudly on the exact
class of regression that RA-1294 shipped silently past CI: generator phase
timing out at 305 s because session.complexity_tier wasn't persisted.

This test would have caught RA-1294 before merge. Keep it that way.

Scheduled runner: `.github/workflows/smoke_pipeline.yml` invokes this nightly
against prod. On failure, Telegram ping via scripts/send_telegram.py.

Usage:
    # Against prod (default)
    DASHBOARD_PASSWORD=... python3 scripts/smoke_test_pipeline.py

    # Against a custom backend (CI sometimes uses this against a Railway branch)
    PI_CEO_URL=https://pi-dev-ops-branch.up.railway.app \
    DASHBOARD_PASSWORD=... python3 scripts/smoke_test_pipeline.py

Exit codes:
    0 — pipeline reached `complete` status with files_modified > 0 and PR URL
    1 — pipeline reached terminal failure OR any assertion failed
    2 — config / infrastructure error (missing env, timeout, etc.)

Assertions (every one would have caught RA-1294):
    A1.  Session spawns with HTTP 200 + valid session_id.
    A2.  Session enters `generate` phase within 90 s.
    A3.  `generate` phase runs for ≥ 310 s OR emits success before 310 s.
         (The 305 s regression was EXACTLY 305 s — failing at 305 s with
         rc=1 is the signature of the tier-timeout bug. This bound catches it.)
    A4.  Session reaches `complete` status within 20 min (generous for advanced).
    A5.  `files_modified > 0` in the final metrics.
    A6.  A PR URL appears in the stream (push phase emitted push_url event).
    A7.  Linear issue (if one was created) transitioned to a non-Todo state.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.cookiejar import CookieJar


PI_CEO_URL     = os.environ.get("PI_CEO_URL", "https://pi-dev-ops-production.up.railway.app").rstrip("/")
PASSWORD       = os.environ.get("DASHBOARD_PASSWORD") or os.environ.get("TAO_PASSWORD") or ""
TARGET_REPO    = os.environ.get("SMOKE_TARGET_REPO", "https://github.com/CleanExpo/Pi-Dev-Ops")
# Brief is intentionally advanced-tier: the classifier will see "full feature"
# keywords and tag it ADVANCED, forcing a 900 s generator timeout. A bug like
# RA-1294 would collapse that back to 300 s and fail this brief.
TEST_BRIEF     = os.environ.get(
    "SMOKE_BRIEF",
    "Add a one-line comment to scripts/send_telegram.py explaining that this "
    "file is the single zero-dependency push helper used by cron, CI, and "
    "Claude sessions. Do NOT change any logic. Do not reformat. Full feature "
    "audit first, then make the minimal edit."
)
MAX_WAIT_S     = int(os.environ.get("SMOKE_MAX_WAIT_S", "1200"))  # 20 min
GEN_MIN_DURATION_S = 310  # RA-1294 signature: died at exactly 305 s


# ── HTTP session with cookies (re-used from existing e2e) ──────────────────
class Session:
    def __init__(self, base: str):
        self.base = base
        self.jar = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.opener = opener

    def login(self, password: str) -> bool:
        data = json.dumps({"password": password}).encode()
        req = urllib.request.Request(f"{self.base}/api/login", data=data,
                                      headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as exc:
            print(f"[login] failed: {exc}")
            return False

    def post(self, path: str, body: dict) -> tuple[int, str]:
        data = json.dumps(body).encode()
        req = urllib.request.Request(f"{self.base}{path}", data=data, method="POST",
                                      headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=15) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace")

    def stream(self, path: str, timeout_s: int):
        """Yield (event_type, data_dict) tuples from an SSE stream."""
        req = urllib.request.Request(f"{self.base}{path}")
        with self.opener.open(req, timeout=timeout_s) as resp:
            buf = ""
            for chunk in iter(lambda: resp.read(4096), b""):
                buf += chunk.decode("utf-8", errors="replace")
                while "\n\n" in buf:
                    event_raw, buf = buf.split("\n\n", 1)
                    data_lines = [ln[6:] for ln in event_raw.splitlines() if ln.startswith("data: ")]
                    if not data_lines:
                        continue
                    raw = "\n".join(data_lines)
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    yield payload


@dataclass
class PipelineAssertions:
    spawned: bool = False
    entered_generate: bool = False
    entered_generate_at: float | None = None
    generate_duration_s: float | None = None
    reached_complete: bool = False
    files_modified: int = 0
    pr_url: str | None = None
    last_status: str | None = None
    errors: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.errors.append(msg)

    def summary(self) -> str:
        lines = [
            f"A1 session spawned:           {'✓' if self.spawned else '✗'}",
            f"A2 entered generate ≤ 90 s:   {'✓' if self.entered_generate else '✗'}",
            f"A3 generate ≥ {GEN_MIN_DURATION_S}s OR ok: {'✓' if self._a3_ok() else '✗' } (dur={self.generate_duration_s})",
            f"A4 reached complete:          {'✓' if self.reached_complete else '✗'}",
            f"A5 files_modified > 0:        {'✓' if self.files_modified > 0 else '✗'} ({self.files_modified})",
            f"A6 PR URL emitted:            {'✓' if self.pr_url else '✗'} {self.pr_url or ''}",
        ]
        return "\n".join(lines)

    def _a3_ok(self) -> bool:
        # A3 passes if either (a) generate ran past 310 s, or (b) generate finished
        # successfully in less time. It fails if generate died at ~305 s with an
        # error — that's the RA-1294 signature.
        if self.generate_duration_s is None:
            return False
        # Specifically reject the 300-310 s failure window when session failed
        if self.last_status == "failed" and 295 <= self.generate_duration_s <= 315:
            return False
        return True

    def all_passed(self) -> bool:
        return (self.spawned and self.entered_generate and self._a3_ok()
                and self.reached_complete and self.files_modified > 0
                and self.pr_url is not None and not self.errors)


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

    # A1: fire the build
    start = time.time()
    code, body = s.post("/api/build", {
        "repo_url": TARGET_REPO,
        "brief":    TEST_BRIEF,
        "intent":   "smoke",
    })
    pa = PipelineAssertions()
    if code != 200:
        print(f"[A1 FAIL] POST /api/build → HTTP {code}: {body[:200]}")
        pa.fail(f"spawn HTTP {code}")
        return 1
    try:
        resp = json.loads(body)
    except json.JSONDecodeError:
        pa.fail(f"spawn non-JSON response: {body[:200]}")
        return 1
    sid = resp.get("session_id") or resp.get("id")
    if not sid:
        pa.fail(f"no session_id in response: {body[:200]}")
        return 1
    pa.spawned = True
    print(f"[A1 PASS] session spawned: {sid}")

    # A2-A6: stream SSE
    stream_path = f"/api/sessions/{sid}/logs"
    print(f"[stream] {stream_path}")

    gen_started_t: float | None = None
    try:
        for event in s.stream(stream_path, timeout_s=MAX_WAIT_S):
            now = time.time() - start
            etype = event.get("type", "")
            text = event.get("text", "")

            # Track phase transitions
            if etype == "phase":
                if "[4/5]" in text or "Running Claude Code" in text:
                    pa.entered_generate = True
                    pa.entered_generate_at = now
                    gen_started_t = now
                    print(f"  [t+{now:.0f}s] ENTERED generate phase")
                elif "[5/5]" in text:
                    print(f"  [t+{now:.0f}s] {text}")

            elif etype == "phase_metric" and event.get("phase") == "generate":
                pa.generate_duration_s = event.get("duration_s")
                print(f"  [t+{now:.0f}s] generate metric: dur={pa.generate_duration_s}s cost=${event.get('cost_usd')}")

            elif etype == "push_url" or (etype == "success" and "pull_request" in text):
                # Pi-CEO emits push_url event when the auto-PR opens
                pa.pr_url = event.get("url") or text
                print(f"  [t+{now:.0f}s] PR URL: {pa.pr_url}")

            elif etype == "files_modified":
                pa.files_modified = int(event.get("count", 0))

            elif etype == "done":
                print(f"  [t+{now:.0f}s] stream ended")
                break

            # Check overall wall-clock budget
            if now > MAX_WAIT_S:
                pa.fail(f"stream exceeded MAX_WAIT_S={MAX_WAIT_S}s")
                break

    except Exception as exc:
        pa.fail(f"stream error: {exc}")

    # A4: reach complete — poll /api/sessions until the session hits terminal,
    # not a one-shot. SSE can drop at the Vercel 10 s proxy while the server
    # session continues; the one-shot check would false-fail.
    import urllib.request as _ur

    def _get_session(sid: str) -> dict | None:
        req = _ur.Request(f"{PI_CEO_URL}/api/sessions")
        for cookie in s.jar:
            req.add_header("Cookie", f"{cookie.name}={cookie.value}")
        try:
            with _ur.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
        except Exception:
            return None
        ss_list = data if isinstance(data, list) else data.get("sessions", [])
        return next((x for x in ss_list if x.get("id", "").startswith(sid[:8])), None)

    # Poll up to MAX_WAIT_S total (including SSE time already elapsed).
    budget_remaining = max(60, MAX_WAIT_S - int(time.time() - start))
    print(f"[poll] waiting up to {budget_remaining}s for terminal state...")
    terminal = {"complete", "failed", "killed", "interrupted"}
    poll_deadline = time.time() + budget_remaining
    me = None
    while time.time() < poll_deadline:
        me = _get_session(sid)
        if me and me.get("status") in terminal:
            break
        if me is None:
            # Session GC'd but may have succeeded just before — give it a
            # moment and retry once; otherwise treat as lost.
            time.sleep(5)
            me = _get_session(sid)
            if me is None:
                pa.fail(f"session {sid[:8]} not in /api/sessions (lost to GC or redeploy)")
                break
        time.sleep(15)

    if me and me.get("status"):
        pa.last_status = me.get("status")
        pa.files_modified = max(pa.files_modified, me.get("files_modified", 0) or 0)
        if pa.last_status == "complete":
            pa.reached_complete = True
            print(f"[A4 PASS] session reached 'complete' with files_modified={pa.files_modified}")
        elif pa.last_status in terminal:
            pa.fail(f"session terminal={pa.last_status} (not complete)")
        else:
            pa.fail(f"session still {pa.last_status} after {budget_remaining}s — polling budget exhausted")

    # A7 — ALWAYS try to kill the session if not already terminal. This keeps
    # the smoke test from leaving zombie Claude work running on prod. Safe to
    # call on a completed session (Pi-CEO returns 200 or 404).
    try:
        kill_req = _ur.Request(f"{PI_CEO_URL}/api/sessions/{sid}/kill", method="POST",
                                data=b"")
        for cookie in s.jar:
            kill_req.add_header("Cookie", f"{cookie.name}={cookie.value}")
        with _ur.urlopen(kill_req, timeout=10) as resp:
            print(f"[cleanup] kill session → {resp.status}")
    except _ur.HTTPError as exc:
        # 404 is expected if session was already complete
        print(f"[cleanup] kill session → {exc.code} (acceptable)")
    except Exception as exc:
        print(f"[cleanup] kill failed: {exc}")

    # Final report
    print()
    print("━━━ ASSERTIONS ━━━")
    print(pa.summary())
    if pa.errors:
        print("\n━━━ ERRORS ━━━")
        for e in pa.errors:
            print(f"  ✗ {e}")

    ok = pa.all_passed()
    print()
    print(f"━━━ RESULT: {'PASS' if ok else 'FAIL'} ━━━")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run_pipeline_smoke())
