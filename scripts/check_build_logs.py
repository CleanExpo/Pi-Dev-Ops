#!/usr/bin/env python3
"""
check_build_logs.py — Vercel build-log inspector for Pi Dev Ops

Fetches the latest Vercel deployment's full build event log, surfaces any
errors or warnings, and writes a timestamped report to
  .harness/build-logs/<timestamp>-<deploy-id>.json

Triggers:
  • Automatically via Claude hook after every `git push` to origin
  • Automatically via Claude hook after every `smoke_test.py` run
  • Manually: python scripts/check_build_logs.py [--deployment-id dpl_xxx]

Exit codes:
  0 — build clean (or warnings only)
  2 — build has TypeScript / compile errors
  3 — build failed entirely (Error state)
  1 — script error (Vercel API unavailable, bad token, etc.)
"""

import json
import sys
import urllib.request
import urllib.error
import argparse
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[1]          # Pi-Dev-Ops/
_AUTH_FILE = Path.home() / "Library" / "Application Support" / "com.vercel.cli" / "auth.json"
_LOG_DIR = _ROOT / ".harness" / "build-logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_PROJECT_ID = "prj_eIA6deQ13rgCFU3jhMBHAA4g27ng"
_TEAM_ID    = "team_KMZACI5rIltoCRhAtGCXlxUf"

_ANSI_RED    = "\033[31m"
_ANSI_YELLOW = "\033[33m"
_ANSI_GREEN  = "\033[32m"
_ANSI_CYAN   = "\033[36m"
_ANSI_RESET  = "\033[0m"


# ---------------------------------------------------------------------------
# Vercel REST helpers
# ---------------------------------------------------------------------------

def _token() -> str:
    if not _AUTH_FILE.exists():
        raise RuntimeError(
            f"Vercel auth file not found at {_AUTH_FILE}. "
            "Run `vercel login` first."
        )
    return json.loads(_AUTH_FILE.read_text())["token"]


def _api(path: str, token: str) -> dict:
    sep = "&" if "?" in path else "?"
    url = f"https://api.vercel.com{path}{sep}teamId={_TEAM_ID}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Vercel API {url} → HTTP {e.code}: {e.read().decode()[:300]}")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def latest_deployment(token: str) -> dict:
    data = _api(
        f"/v6/deployments?projectId={_PROJECT_ID}&target=production&limit=1",
        token,
    )
    deployments = data.get("deployments", [])
    if not deployments:
        raise RuntimeError("No production deployments found for this project.")
    return deployments[0]


def build_events(deploy_id: str, token: str) -> list[dict]:
    data = _api(f"/v2/deployments/{deploy_id}/events?builds=1&limit=2000", token)
    if isinstance(data, list):
        return data
    return data.get("events", [])


def classify_events(events: list[dict]) -> dict:
    errors   = []
    warnings = []
    build_lines = []
    ts_errors = []

    for e in events:
        p    = e.get("payload", {})
        raw  = p.get("text", "") or p.get("info", "") or ""
        text = raw if isinstance(raw, str) else json.dumps(raw)
        src  = e.get("type", "")

        if not text:
            continue

        # Collect all meaningful build output
        build_lines.append(f"[{src}] {text}")

        ltext = text.lower()

        # TypeScript / type errors
        if "type error:" in ltext or "failed to type check" in ltext:
            ts_errors.append(text)
            errors.append(text)
        # General errors
        elif src == "stderr" and any(k in ltext for k in ["error:", "failed", "exited with"]):
            errors.append(text)
        # Warnings
        elif src == "stderr" and any(k in ltext for k in ["warn", "warning", "deprecat"]):
            warnings.append(text)

    return {
        "errors":    errors,
        "warnings":  warnings,
        "ts_errors": ts_errors,
        "all_lines": build_lines,
    }


def analyse(deploy_id: str | None = None) -> int:
    token = _token()

    if deploy_id:
        deploy = _api(f"/v13/deployments/{deploy_id}", token)
    else:
        deploy = latest_deployment(token)

    did    = deploy.get("id") or deploy.get("uid", "unknown")
    state  = deploy.get("readyState", deploy.get("state", "?"))
    url    = deploy.get("url", "?")
    target = deploy.get("target", "?")
    ts     = deploy.get("createdAt", 0)
    created = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else "?"

    print(f"\n{_ANSI_CYAN}━━━  Pi Dev Ops · Vercel Build Log Inspector  ━━━{_ANSI_RESET}")
    print(f"  Deployment : {did}")
    print(f"  URL        : https://{url}")
    print(f"  Target     : {target}")
    print(f"  State      : {state}")
    print(f"  Created    : {created}\n")

    # Fetch events
    print("Fetching build events…", end="", flush=True)
    events = build_events(did, token)
    print(f" {len(events)} events retrieved.")

    result = classify_events(events)

    # -----------------------------------------------------------------------
    # Print summary
    # -----------------------------------------------------------------------

    if result["errors"]:
        print(f"\n{_ANSI_RED}✖  {len(result['errors'])} ERROR(S) DETECTED{_ANSI_RESET}")
        for i, e in enumerate(result["errors"][:10], 1):
            print(f"  {i}. {e.strip()[:200]}")
    else:
        print(f"\n{_ANSI_GREEN}✓  No errors in build output{_ANSI_RESET}")

    if result["warnings"]:
        print(f"\n{_ANSI_YELLOW}⚠  {len(result['warnings'])} WARNING(S){_ANSI_RESET}")
        for w in result["warnings"][:5]:
            print(f"  • {w.strip()[:200]}")

    if result["ts_errors"]:
        print(f"\n{_ANSI_RED}⚑  TypeScript errors ({len(result['ts_errors'])} found){_ANSI_RESET}")
        for e in result["ts_errors"][:5]:
            print(f"  {e.strip()[:300]}")

    # -----------------------------------------------------------------------
    # Persist report
    # -----------------------------------------------------------------------

    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    report_path = _LOG_DIR / f"{stamp}-{did[:12]}.json"
    report = {
        "timestamp":   stamp,
        "deploy_id":   did,
        "state":       state,
        "url":         url,
        "target":      target,
        "created":     created,
        "error_count": len(result["errors"]),
        "warn_count":  len(result["warnings"]),
        "ts_errors":   result["ts_errors"],
        "errors":      result["errors"],
        "warnings":    result["warnings"],
        "full_log":    result["all_lines"],
    }
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\n  Report saved → {report_path.relative_to(_ROOT)}")

    # -----------------------------------------------------------------------
    # Exit code
    # -----------------------------------------------------------------------

    if state == "ERROR":
        print(f"\n{_ANSI_RED}✖  Deployment is in ERROR state — investigate immediately.{_ANSI_RESET}\n")
        return 3
    if result["ts_errors"] or result["errors"]:
        print(f"\n{_ANSI_RED}✖  Build errors found — see report above.{_ANSI_RESET}\n")
        return 2
    print(f"\n{_ANSI_GREEN}✓  Build clean.{_ANSI_RESET}\n")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check Vercel build logs for Pi Dev Ops dashboard.")
    parser.add_argument("--deployment-id", "-d", default=None,
                        help="Specific deployment ID to inspect (default: latest production)")
    args = parser.parse_args()

    try:
        code = analyse(args.deployment_id)
        sys.exit(code)
    except RuntimeError as exc:
        print(f"{_ANSI_RED}Error: {exc}{_ANSI_RESET}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(0)
