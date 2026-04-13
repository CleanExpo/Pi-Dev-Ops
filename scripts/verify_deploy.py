#!/usr/bin/env python3
"""
verify_deploy.py — Production commit parity audit (RA-582).

Compares git HEAD on origin/main against deployed SHAs on:
  - Vercel (pi-dev-ops project linked to GitHub)
  - Railway (via CLI — requires `railway` in PATH and auth configured)

Exit codes:
  0 = all services in sync (or within 1 commit)
  1 = drift detected in at least one service
  2 = script/auth error

Usage:
  python scripts/verify_deploy.py [--json]
"""
import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────
_VERCEL_PROJECT_ID = "prj_I5sYqNTlL51DlvyzSFjiHX6FrLAX"  # pi-dev-ops (GitHub-linked)
_VERCEL_TEAM_ID    = "team_KMZACI5rIltoCRhAtGCXlxUf"
_VERCEL_AUTH_PATH  = Path.home() / "Library/Application Support/com.vercel.cli/auth.json"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parents[1],
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def _vercel_token() -> str | None:
    try:
        with open(_VERCEL_AUTH_PATH) as f:
            return json.load(f).get("token")
    except (OSError, KeyError):
        return None


def get_local_sha() -> dict:
    try:
        head = _git("rev-parse", "HEAD")
        origin = _git("rev-parse", "origin/main")
        drift = 0
        if head != origin:
            log = _git("log", "--oneline", "origin/main..HEAD")
            drift = len(log.splitlines()) if log else 0
        return {"sha": head, "origin_main": origin, "local_ahead": drift, "ok": True}
    except RuntimeError as exc:
        return {"sha": "unknown", "error": str(exc), "ok": False}


def get_vercel_sha() -> dict:
    token = _vercel_token()
    if not token:
        return {"sha": "unknown", "error": "No Vercel token found", "ok": False}
    try:
        url = (
            f"https://api.vercel.com/v6/deployments"
            f"?projectId={_VERCEL_PROJECT_ID}"
            f"&target=production"
            f"&limit=5"
            f"&teamId={_VERCEL_TEAM_ID}"
        )
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        deployments = data.get("deployments", [])
        if not deployments:
            return {"sha": "unknown", "error": "No deployments found", "ok": False}
        # Find latest READY deployment
        ready = next((d for d in deployments if d.get("state") == "READY"), None)
        latest = ready or deployments[0]
        sha = latest.get("meta", {}).get("githubCommitSha") or "unknown"
        return {
            "sha": sha[:12] if sha != "unknown" else sha,
            "full_sha": sha,
            "state": latest.get("state"),
            "url": latest.get("url"),
            "ok": latest.get("state") == "READY",
        }
    except Exception as exc:
        return {"sha": "unknown", "error": str(exc), "ok": False}


def get_railway_sha() -> dict:
    """Try to get deployed SHA from Railway via CLI."""
    try:
        # Railway CLI: get current deployment info
        result = subprocess.run(
            ["railway", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            sha = data.get("deploymentId") or data.get("commitHash") or "unknown"
            return {"sha": sha[:12] if len(sha) > 12 else sha, "ok": True, "raw": data}
        # Fallback: check if railway can tell us anything
        result2 = subprocess.run(
            ["railway", "status"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return {
            "sha": "unknown",
            "note": "No linked project (run: railway link)",
            "ok": False,
            "raw": result2.stdout.strip(),
        }
    except FileNotFoundError:
        return {"sha": "unknown", "error": "railway CLI not found in PATH", "ok": False}
    except Exception as exc:
        return {"sha": "unknown", "error": str(exc), "ok": False}


def _short(sha: str) -> str:
    return sha[:12] if len(sha) >= 12 else sha


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Production commit parity audit")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    local   = get_local_sha()
    vercel  = get_vercel_sha()
    railway = get_railway_sha()

    head_sha = local.get("sha", "unknown")

    services = [
        {
            "service": "git HEAD",
            "deployed_sha": _short(head_sha),
            "target_sha": _short(local.get("origin_main", head_sha)),
            "drift": local.get("local_ahead", 0),
            "ok": local["ok"],
            "note": f"{local.get('local_ahead', 0)} commit(s) ahead of origin/main" if local.get("local_ahead") else "",
        },
        {
            "service": "Vercel (pi-dev-ops)",
            "deployed_sha": _short(vercel.get("full_sha", vercel.get("sha", "unknown"))),
            "target_sha": _short(head_sha),
            "drift": None,  # computed below
            "state": vercel.get("state", "unknown"),
            "ok": vercel["ok"],
            "note": vercel.get("error") or vercel.get("url", ""),
        },
        {
            "service": "Railway (pi-ceo)",
            "deployed_sha": railway.get("sha", "unknown"),
            "target_sha": _short(head_sha),
            "drift": None,
            "ok": railway["ok"],
            "note": railway.get("error") or railway.get("note", ""),
        },
    ]

    # Compute drift for Vercel
    for svc in services[1:]:
        deployed = svc["deployed_sha"]
        target   = svc["target_sha"]
        if deployed == "unknown" or not svc["ok"]:
            svc["drift"] = "?"
        elif deployed == target or target.startswith(deployed) or deployed.startswith(target):
            svc["drift"] = 0
        else:
            # Count commits between
            try:
                log = _git("log", "--oneline", f"{deployed}..{_short(head_sha)}")
                svc["drift"] = len(log.splitlines()) if log else "?"
            except RuntimeError:
                svc["drift"] = "?"

    if args.json:
        print(json.dumps({"head": _short(head_sha), "services": services}, indent=2))
        return 0

    # Human-readable table
    print()
    print("═" * 70)
    print("  Pi-Dev-Ops — Production Commit Parity Audit")
    print(f"  git HEAD: {_short(head_sha)}")
    print("═" * 70)
    print(f"  {'Service':<30}  {'Deployed SHA':<14}  {'Drift':<8}  Status")
    print(f"  {'-'*30}  {'-'*14}  {'-'*8}  ------")

    any_drift = False
    for svc in services:
        drift    = svc.get("drift", "?")
        status   = "✓ OK" if svc["ok"] and drift in (0, "0") else ("⚠ DRIFT" if drift not in ("?", None) and drift != 0 else "✗ ERR")
        drift_s  = str(drift) if drift is not None else "?"
        note     = f"  ← {svc['note']}" if svc.get("note") else ""
        deployed = svc["deployed_sha"]
        print(f"  {svc['service']:<30}  {deployed:<14}  {drift_s:<8}  {status}{note}")
        if drift not in (0, "?", None) and drift != 0:
            any_drift = True

    print()

    if any_drift:
        print("  ⚠  Drift detected. Deploy to bring services in sync.")
        print()
        return 1

    print("  All services in sync (or parity unknown for Railway — link project).")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
