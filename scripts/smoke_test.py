"""
smoke_test.py — Pi CEO E2E regression smoke test
Run against a live server to verify all API surface checks.

Usage:
    python scripts/smoke_test.py [--url http://127.0.0.1:7777] [--password <pw>]
    python scripts/smoke_test.py --target=prod   # hits production Railway URL

Exit codes:
    0 — all checks passed
    1 — one or more checks failed

Environment variables (fallback if --password not given):
    TAO_PASSWORD — server password
"""
import sys
import os
import argparse
import asyncio
import datetime
import json
import time
import urllib.request
import urllib.error
import http.cookiejar

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
_PROD_URL = "https://pi-dev-ops-production.up.railway.app"

parser = argparse.ArgumentParser(description="Pi CEO smoke test")
parser.add_argument("--url", default="http://127.0.0.1:7777", help="Server base URL")
parser.add_argument("--password", default=os.environ.get("TAO_PASSWORD", ""), help="Server password")
parser.add_argument("--target", choices=["prod", "local"], default="local",
                    help="'prod' hits the Railway production URL")
parser.add_argument("--emit-metrics", action="store_true",
                    help="Write results to .harness/post-deploy-metrics/ JSONL")
parser.add_argument("--agent-sdk", action="store_true",
                    help="Run SDK path verification checks (RA-575); requires server running")
args = parser.parse_args()

# --target=prod overrides --url and flags prod mode (skips local FS checks)
PROD_MODE = args.target == "prod"
if PROD_MODE and args.url == "http://127.0.0.1:7777":
    args.url = _PROD_URL

BASE = args.url.rstrip("/")
PASSWORD = args.password

# ---------------------------------------------------------------------------
# Metrics emission helper (RA-583)
# ---------------------------------------------------------------------------
_METRICS_DIR = os.path.join(os.path.dirname(__file__), "..", ".harness", "post-deploy-metrics")


def _emit_metrics(passed: list, failed: list, target: str) -> None:
    """Write one post-deploy metrics row to daily JSONL. Swallows any I/O error."""
    try:
        os.makedirs(_METRICS_DIR, exist_ok=True)
        today = datetime.date.today().isoformat()
        path = os.path.join(_METRICS_DIR, f"{today}.jsonl")
        row = json.dumps({
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds"),
            "target": target,
            "total": len(passed) + len(failed),
            "passed": len(passed),
            "failed": len(failed),
            "success": len(failed) == 0,
            "failed_checks": failed,
        })
        with open(path, "a", encoding="utf-8") as f:
            f.write(row + "\n")
    except Exception:
        pass


def _raise_linear_failure_ticket(failed_checks: list) -> None:
    """Create an Urgent Linear ticket on smoke test failure. Swallows errors."""
    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        return
    try:
        _LINEAR = "https://api.linear.app/graphql"
        checks_md = "\n".join(f"- {c}" for c in failed_checks)
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) { success issue { identifier } }
        }
        """
        variables = {
            "input": {
                "teamId": "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673",
                "projectId": "f45212be-3259-4bfb-89b1-54c122c939a7",
                "title": f"[SMOKE-FAIL] Production smoke test failed — {len(failed_checks)} check(s)",
                "description": (
                    f"Post-deploy smoke test failed against `{BASE}`.\n\n"
                    f"**Failed checks ({len(failed_checks)}):**\n{checks_md}\n\n"
                    "Run `python scripts/smoke_test.py --target=prod` to reproduce."
                ),
                "priority": 1,  # Urgent
            }
        }
        payload = json.dumps({"query": mutation, "variables": variables}).encode()
        req = urllib.request.Request(
            _LINEAR, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": api_key},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        ident = (result.get("data", {}).get("issueCreate", {}).get("issue") or {}).get("identifier", "?")
        print(f"  [LINEAR] Created failure ticket: {ident}")
    except Exception as exc:
        print(f"  [LINEAR] Could not create ticket: {exc}")

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))


def _req(method: str, path: str, body=None, headers=None, use_cookie=True) -> tuple[int, dict | str]:
    """Make an HTTP request. Returns (status_code, response_body)."""
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    opener = _opener if use_cookie else urllib.request.build_opener()
    try:
        with opener.open(req) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw
    except (ConnectionRefusedError, OSError) as e:
        return 0, {"error": str(e)}


def get(path, **kw):  return _req("GET", path, **kw)
def post(path, body=None, **kw): return _req("POST", path, body=body, **kw)
def delete(path, **kw): return _req("DELETE", path, **kw)


# ---------------------------------------------------------------------------
# WebSocket check (stdlib asyncio + raw HTTP upgrade)
# ---------------------------------------------------------------------------
async def _ws_connect_check(sid: str) -> bool:
    """Open the WebSocket, read at least one JSON frame, close cleanly."""
    host = BASE.replace("http://", "").replace("https://", "")
    host_part, _, port_str = host.partition(":")
    port = int(port_str) if port_str else 80
    # Get tao_session cookie value
    cookie_val = None
    for c in _jar:
        if c.name == "tao_session":
            cookie_val = c.value
            break
    if not cookie_val:
        return False

    ws_key = "dGhlIHNhbXBsZSBub25jZQ=="
    headers = (
        f"GET /ws/build/{sid} HTTP/1.1\r\n"
        f"Host: {host_part}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {ws_key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"Cookie: tao_session={cookie_val}\r\n"
        f"\r\n"
    )
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host_part, port), timeout=5
        )
        writer.write(headers.encode())
        await writer.drain()
        # Read HTTP upgrade response
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = await asyncio.wait_for(reader.read(256), timeout=5)
            if not chunk:
                break
            buf += chunk
        if b"101 Switching Protocols" not in buf:
            writer.close()
            return False
        # Read one WebSocket frame (text or binary)
        frame_header = await asyncio.wait_for(reader.read(2), timeout=10)
        writer.close()
        return len(frame_header) >= 2
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
PASS = []
FAIL = []


def check(name: str, ok: bool, detail: str = ""):
    marker = "PASS" if ok else "FAIL"
    suffix = f" ({detail})" if detail else ""
    print(f"  [{marker}] {name}{suffix}")
    (PASS if ok else FAIL).append(name)


# ---------------------------------------------------------------------------
# CHECKS
# ---------------------------------------------------------------------------
print(f"\nPi CEO Smoke Test — {BASE}\n{'=' * 50}")

# ── 1. Server health ──────────────────────────────────────────────────────
print("\n[1/9] Server Health")
sc, body = get("/health")
if sc == 0:
    print(f"\nFATAL: Cannot reach server at {BASE} — {body.get('error', 'connection refused')}")
    print("Start the server first:  cd app && uvicorn server.main:app --host 127.0.0.1 --port 7777")
    sys.exit(1)
check("GET /health returns 200", sc == 200)
check("Health body has status:ok", isinstance(body, dict) and body.get("status") == "ok", str(body))

# ── 2. Authentication ────────────────────────────────────────────────────
print("\n[2/9] Authentication")
sc, _ = get("/api/sessions", use_cookie=False)
check("Unauthenticated /api/sessions returns 401", sc == 401, f"got {sc}")

if not PASSWORD:
    check("Login skipped — no password provided (set TAO_PASSWORD)", False, "missing password")
    print("\nFATAL: Cannot continue without password. Set TAO_PASSWORD or pass --password.")
    print(f"\nResult: {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1)

sc, body = post("/api/login", {"password": PASSWORD})
check("POST /api/login returns 200", sc == 200, f"got {sc}")
check("Login body has ok:true", isinstance(body, dict) and body.get("ok") is True, str(body))

cookie_set = any(c.name == "tao_session" for c in _jar)
check("tao_session cookie set", cookie_set)

sc, body = get("/api/me")
check("GET /api/me returns authenticated:true", sc == 200 and isinstance(body, dict) and body.get("authenticated") is True, str(body))

# ── 3. Build session ──────────────────────────────────────────────────────
print("\n[3/9] Build Session")
sc, body = post("/api/build", {"repo_url": "https://github.com/CleanExpo/Pi-Dev-Ops", "model": "sonnet"})
check("POST /api/build returns 200", sc == 200, f"got {sc}")
session_id = body.get("session_id") if isinstance(body, dict) else None
check("Response has session_id", bool(session_id), str(body))
check("Response has status:created", isinstance(body, dict) and body.get("status") == "created", str(body))

sc, sessions = get("/api/sessions")
check("GET /api/sessions returns 200", sc == 200, f"got {sc}")
ids = [s.get("id") for s in sessions] if isinstance(sessions, list) else []
check("New session visible in session list", session_id in ids, f"session_id={session_id}")

# ── 4. WebSocket ──────────────────────────────────────────────────────────
print("\n[4/9] WebSocket")
if session_id:
    ws_ok = asyncio.run(_ws_connect_check(session_id))
    check("WebSocket /ws/build/{sid} connects and streams frames", ws_ok)
else:
    check("WebSocket check skipped — no session_id", False)

# ── 5. Session persistence ────────────────────────────────────────────────
print("\n[5/9] Session Persistence")
if PROD_MODE:
    # Skip local filesystem checks in prod mode — Railway container FS not accessible
    print("  (skipped in prod mode — remote filesystem not accessible)")
    check("Session persistence (prod: check via API)", isinstance(sessions, list), "sessions list returned from API")
else:
    logs_dir = os.environ.get("TAO_LOGS", os.path.join(os.path.dirname(__file__), "..", "app", "logs"))
    sessions_dir = os.path.join(logs_dir, "sessions")
    check("sessions/ directory exists", os.path.isdir(sessions_dir), sessions_dir)
    if session_id and os.path.isdir(sessions_dir):
        json_file = os.path.join(sessions_dir, f"{session_id}.json")
        time.sleep(0.5)
        check("Session JSON persisted to disk", os.path.isfile(json_file), json_file)
        if os.path.isfile(json_file):
            with open(json_file) as _f:
                _sdata = json.load(_f)
            check("Session JSON has evaluator_model field", "evaluator_model" in _sdata, str(list(_sdata.keys())))
            check("Session JSON has evaluator_consensus field", "evaluator_consensus" in _sdata, str(list(_sdata.keys())))
    else:
        check("Session JSON check skipped", False, "no session_id or sessions_dir missing")

# ── 6. Garbage collection ─────────────────────────────────────────────────
print("\n[6/9] Garbage Collection")
sc, body = post("/api/gc")
check("POST /api/gc returns 200", sc == 200, f"got {sc}")
check("GC response has removed key", isinstance(body, dict) and "removed" in body, str(body))
errors_val = body.get("errors", 0) if isinstance(body, dict) else 1
check("GC response has no errors", errors_val == [] or errors_val == 0, str(body))

# ── 7. Lessons API ────────────────────────────────────────────────────────
print("\n[7/9] Lessons API")
sc, body = get("/api/lessons")
check("GET /api/lessons returns 200", sc == 200, f"got {sc}")
check("Lessons response is a list", isinstance(body, list), str(type(body)))
check("Lessons list is non-empty (seed data present)", isinstance(body, list) and len(body) > 0, f"len={len(body) if isinstance(body, list) else 'N/A'}")

sc, entry = post("/api/lessons", {
    "source": "smoke-test",
    "category": "smoke-test",
    "lesson": "Smoke test lesson — safe to delete",
    "severity": "info",
})
check("POST /api/lessons returns 200", sc == 200, f"got {sc}")
check("New lesson entry has expected fields", isinstance(entry, dict) and "lesson" in entry and "category" in entry, str(entry))

sc, filtered = get("/api/lessons?category=persistence")
check("GET /api/lessons?category=persistence returns 200", sc == 200, f"got {sc}")
check("Category filter returns a list", isinstance(filtered, list), str(type(filtered)))

# ── 8. Webhook ────────────────────────────────────────────────────────────
print("\n[8/9] Webhook")
# Missing signature → 400
sc, _ = post("/api/webhook", {"event": "test"}, use_cookie=False)
check("Webhook with no signature returns 400", sc == 400, f"got {sc}")

# Invalid GitHub signature → depends on WEBHOOK_SECRET being configured
webhook_body = json.dumps({
    "repository": {"html_url": "https://github.com/CleanExpo/Pi-Dev-Ops"},
    "ref": "refs/heads/main",
}).encode()
fake_sig = "sha256=deadbeefdeadbeefdeadbeefdeadbeefdeadbeef1234deadbeefdeadbeef1234"
sc, _ = _req(
    "POST", "/api/webhook",
    body={"repository": {"html_url": "https://github.com/CleanExpo/Pi-Dev-Ops"}, "ref": "refs/heads/main"},
    headers={"x-github-event": "push", "x-hub-signature-256": fake_sig},
    use_cookie=False,
)
check("Webhook with invalid signature returns 401 or 500", sc in (401, 500), f"got {sc}")

# ── 9. Rate limiting ──────────────────────────────────────────────────────
print("\n[9/9] Rate Limiting  (sends rapid POST /api/login — this is the last check)")
hit_429 = False
for _ in range(35):
    sc, _ = _req("POST", "/api/login", body={"password": "wrong-password-rate-limit-test"}, use_cookie=False)
    if sc == 429:
        hit_429 = True
        break
check("Rapid requests trigger 429 Too Many Requests", hit_429)

# ── 10. Autonomy status (RA-584) ─────────────────────────────────────────
print("\n[10/10] Autonomy Status")
sc, body = get("/api/autonomy/status")
check("GET /api/autonomy/status returns 200", sc == 200, f"got {sc}")
if sc == 200 and isinstance(body, dict):
    check("Autonomy body has 'enabled' field", "enabled" in body, str(body))
    check("Autonomy body has 'poll_count' field", "poll_count" in body, str(body))

# ── 11. SDK path verification (--agent-sdk) ───────────────────────────────
if args.agent_sdk:
    print("\n[11/10] Agent SDK Path Verification (RA-575)")

    # 11a. Import check
    sdk_importable = False
    try:
        import importlib
        _sdk = importlib.import_module("claude_agent_sdk")
        sdk_importable = True
        _sdk_classes = [c for c in ("ClaudeSDKClient", "ClaudeAgentOptions", "AssistantMessage", "ResultMessage", "TextBlock") if hasattr(_sdk, c)]
        check("claude_agent_sdk importable", True, f"version={getattr(_sdk, '__version__', 'unknown')}")
        check("SDK exports required classes", len(_sdk_classes) == 5, f"found: {_sdk_classes}")
    except ImportError:
        check("claude_agent_sdk importable", False, "not installed — run: pip install claude-agent-sdk")

    # 11b. sessions.py function signature
    try:
        import sys as _sys
        _repo_root = os.path.join(os.path.dirname(__file__), "..")
        if _repo_root not in _sys.path:
            _sys.path.insert(0, _repo_root)
        import inspect
        from app.server import sessions as _sessions
        _fn = getattr(_sessions, "_run_claude_via_sdk", None)
        check("_run_claude_via_sdk exists in sessions.py", _fn is not None)
        if _fn:
            _sig = inspect.signature(_fn)
            _params = list(_sig.parameters)
            check("_run_claude_via_sdk has session_id param", "session_id" in _params, f"params={_params}")
            check("_run_claude_via_sdk has phase param", "phase" in _params, f"params={_params}")
        _eval_fn = getattr(_sessions, "_extract_eval_score", None)
        check("_extract_eval_score helper exists", _eval_fn is not None)
    except Exception as e:
        check("sessions.py SDK function check", False, str(e))

    # 11c. Metrics dir writable
    _sdk_metrics_dir = os.path.join(os.path.dirname(__file__), "..", ".harness", "agent-sdk-metrics")
    try:
        os.makedirs(_sdk_metrics_dir, exist_ok=True)
        _test_file = os.path.join(_sdk_metrics_dir, ".write-test")
        with open(_test_file, "w") as _f:
            _f.write("ok")
        os.unlink(_test_file)
        check("SDK metrics dir writable", True, _sdk_metrics_dir)
    except Exception as e:
        check("SDK metrics dir writable", False, str(e))

    # 11d. sdk_metrics.py analyser
    _analyser = os.path.join(os.path.dirname(__file__), "sdk_metrics.py")
    check("scripts/sdk_metrics.py exists", os.path.isfile(_analyser), _analyser)

    # 11e. Minimal SDK call (only if sdk importable + claude CLI available)
    if sdk_importable:
        print("  [SDK] Attempting minimal _run_prompt_via_sdk() call...")
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            from app.server.agents.board_meeting import _run_prompt_via_sdk
            _result = _run_prompt_via_sdk("Reply with exactly the word CONFIRMED and nothing else.", timeout=30)
            sdk_call_ok = "CONFIRMED" in _result.upper() if _result else False
            check("SDK _run_prompt_via_sdk() returns CONFIRMED", sdk_call_ok, repr(_result[:60]) if _result else "empty response")
        except Exception as exc:
            check("SDK _run_prompt_via_sdk() call", False, str(exc)[:120])

# ── Summary ───────────────────────────────────────────────────────────────
total = len(PASS) + len(FAIL)
print(f"\n{'=' * 50}")
print(f"Result: {len(PASS)}/{total} checks passed")
if FAIL:
    print("\nFailed checks:")
    for name in FAIL:
        print(f"  - {name}")
print()

# ── Metrics emission (--emit-metrics or prod mode) ────────────────────────
if args.emit_metrics or PROD_MODE:
    target_label = "prod" if PROD_MODE else BASE
    _emit_metrics(PASS, FAIL, target_label)
    print(f"  [METRICS] Row written to .harness/post-deploy-metrics/")

# ── Auto-raise Linear ticket on prod failure ──────────────────────────────
if PROD_MODE and FAIL:
    print("  [LINEAR] Raising failure ticket...")
    _raise_linear_failure_ticket(FAIL)

sys.exit(0 if not FAIL else 1)
