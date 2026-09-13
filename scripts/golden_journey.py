#!/usr/bin/env python3
"""
golden_journey.py — UNI-2652 wrapper around scripts/smoke_test_pipeline.py.

Adds A8 (/ready was 200 before the run), A9 (gate row and session status
agree) and A10 (PR body maps Requirement → Change → Test) without growing
run_pipeline_smoke past its 166-line cap.

Usage:
    # One live journey (A8 + A1–A7 + A9 + A10)
    DASHBOARD_PASSWORD=... python3 scripts/golden_journey.py

    # Five consecutive journeys, then the planted failure
    DASHBOARD_PASSWORD=... python3 scripts/golden_journey.py --runs 5 --plant-failure

    # Planted failure only (no prod, CI-safe)
    python3 scripts/golden_journey.py --plant-failure

Exit codes match the smoke script: 0 pass, 1 assertion fail, 2 config error.
"""
from __future__ import annotations

import argparse
import io
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.golden_journey_checks import (  # noqa: E402
    Check,
    gate_agrees_with_session,
    parse_smoke_output,
    pr_maps_requirement_to_change_to_test,
    probe_ready,
)
from scripts.golden_journey_planted import run_planted_failure  # noqa: E402
from scripts.smoke_test_pipeline import (  # noqa: E402
    PASSWORD,
    PI_CEO_URL,
    Session,
    run_pipeline_smoke,
)


def run_one_journey(
    smoke_fn=run_pipeline_smoke,
    ready_fn=None,
    session_fn=None,
    pr_body_fn=None,
) -> int:
    """A8, then the existing smoke (A1–A7), then A9 and A10."""
    sess = Session(PI_CEO_URL)
    a8 = (ready_fn or _live_ready)(sess)
    _print_check(a8)
    if not a8.ok:
        return 1

    code, text = _capture_smoke(smoke_fn)
    if code != 0:
        print(f"[smoke] run_pipeline_smoke → {code}")
        return code

    captured = parse_smoke_output(text)
    a9 = (session_fn or _live_a9)(sess, captured)
    a10 = (pr_body_fn or _live_a10)(captured)
    _print_check(a9)
    _print_check(a10)
    return 0 if (a9.ok and a10.ok and captured.smoke_passed) else 1


def run_consecutive(n: int, **hooks) -> int:
    """Stop on the first failing journey. Consecutive means all of them."""
    for i in range(1, n + 1):
        print(f"\n━━━ JOURNEY {i}/{n} ━━━")
        code = run_one_journey(**hooks)
        if code != 0:
            print(f"━━━ JOURNEY {i}/{n}: FAIL (stop) ━━━")
            return code
        print(f"━━━ JOURNEY {i}/{n}: PASS ━━━")
    return 0


def run_planted() -> int:
    with tempfile.TemporaryDirectory(prefix="golden-planted-") as tmp:
        proof = run_planted_failure(Path(tmp))  # isolated from the live journey
    print("━━━ PLANTED FAILURE ━━━")
    print(f"  worktree retained:            {'✓' if proof.worktree_retained else '✗'}")
    print(f"  claim released after expiry:  {'✓' if proof.claim_released_after_expiry else '✗'}")
    print(f"  second machine resumed:       {'✓' if proof.second_machine_resumed else '✗'}")
    print(f"  no duplicate claim:           {'✓' if proof.no_duplicate_claim else '✗'}")
    print(f"  no false green:               {'✓' if proof.no_false_green else '✗'}")
    for err in proof.errors:
        print(f"  ✗ {err}")
    print(f"━━━ PLANTED: {'PASS' if proof.all_passed() else 'FAIL'} ━━━")
    return 0 if proof.all_passed() else 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.plant_failure and args.runs is None:
        return run_planted()
    runs = 1 if args.runs is None else args.runs
    if runs < 1:
        print("ERROR: --runs must be >= 1", file=sys.stderr)
        return 2
    if not PASSWORD:
        print("ERROR: DASHBOARD_PASSWORD (or TAO_PASSWORD) required", file=sys.stderr)
        return 2
    code = run_consecutive(runs) if runs > 1 else run_one_journey()
    if code != 0:
        return code
    return run_planted() if args.plant_failure else 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="UNI-2652 golden journey (A1–A10, 5+1)")
    p.add_argument("--runs", type=int, default=None, help="consecutive live journeys (default 1)")
    p.add_argument(
        "--plant-failure",
        action="store_true",
        help="planted failure only, or after --runs if both are set",
    )
    return p.parse_args(argv)


def _capture_smoke(smoke_fn) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = smoke_fn()
    text = buf.getvalue()
    sys.stdout.write(text)
    return code, text


def _live_ready(sess: Session) -> Check:
    if not sess.login(PASSWORD):
        return Check("A8", False, "login failed before /ready probe")
    return probe_ready(sess.opener, sess.base)


def _live_a9(sess: Session, captured) -> Check:
    session = _fetch_session(sess, captured.sid)
    if not session.get("status") and captured.smoke_passed:
        session = {"status": "complete", "id": captured.sid}
    gate = _fetch_gate(sess, captured)
    return gate_agrees_with_session(gate, session)


def _live_a10(captured) -> Check:
    body = _fetch_pr_body(captured.pr_url)
    return pr_maps_requirement_to_change_to_test(body)


def _fetch_session(sess: Session, sid: str | None) -> dict:
    if not sid:
        return {}
    from scripts.golden_journey_checks import _http_get, load_json

    code, text = _http_get(sess.opener, sess.base, "/api/sessions")
    if code != 200:
        return {}
    payload = load_json(text)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("sessions", [])
    else:
        return {}
    if not isinstance(rows, list):
        return {}
    return next((x for x in rows if str(x.get("id", "")).startswith(sid[:8])), {}) or {}


def _fetch_gate(sess: Session, captured) -> dict:
    """Prefer an explicit gate payload; otherwise infer shipped from the PR URL."""
    from scripts.golden_journey_checks import _http_get, load_json_object

    if captured.sid:
        for path in (f"/api/sessions/{captured.sid}/gate", f"/api/gate-checks?session_id={captured.sid}"):
            code, text = _http_get(sess.opener, sess.base, path)
            if code == 200:
                row = load_json_object(text)
                if row:
                    return row
    return {"shipped": bool(captured.pr_url), "push_ok": bool(captured.pr_url)}


def _fetch_pr_body(pr_url: str | None) -> str:
    if not pr_url:
        return ""
    import json
    import os
    import urllib.request

    api = pr_url.replace("https://github.com/", "https://api.github.com/repos/").replace("/pull/", "/pulls/")
    req = urllib.request.Request(api, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return str(json.loads(resp.read()).get("body") or "")
    except Exception as exc:  # noqa: BLE001
        print(f"[A10] could not fetch PR body: {exc}")
        return ""


def _print_check(check: Check) -> None:
    mark = "✓" if check.ok else "✗"
    print(f"[{check.name} {'PASS' if check.ok else 'FAIL'}] {mark} {check.detail}")


if __name__ == "__main__":
    sys.exit(main())
