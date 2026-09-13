#!/usr/bin/env python3
"""POST a successful mesh ship to Pi-CEO (RA-7377).

Called from mesh/hooks/mesh_ship.sh after a real push, or after autogit moved
HEAD and the wrapper's own push was then up-to-date. Best-effort: a missing
key or a network failure must never fail the Stop hook.

Machines hold PI_CEO_API_KEY only — same contract as mesh/heartbeat.py.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _from_env_file(name: str) -> str:
    """Read a key from ~/.hermes/.env when it is not in the process env."""
    envf = Path.home() / ".hermes" / ".env"
    if not envf.exists():
        return ""
    try:
        for line in envf.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        return ""
    return ""


def api_url() -> str:
    return (
        os.environ.get("PI_CEO_API_URL")
        or _from_env_file("PI_CEO_API_URL")
        or "https://pi-dev-ops-production.up.railway.app"
    )


def api_key() -> str:
    return os.environ.get("PI_CEO_API_KEY") or _from_env_file("PI_CEO_API_KEY")


def _git(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10, check=False,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def repo_from_remote(url: str) -> str:
    """Turn a git remote URL into owner/repo. Local paths keep the last two parts."""
    text = (url or "").strip()
    if text.endswith(".git"):
        text = text[:-4]
    text = text.rstrip("/").replace("\\", "/")
    if ":" in text and "://" not in text:
        text = text.split(":", 1)[1]
    if "://" in text:
        text = text.split("://", 1)[1]
        if "/" in text:
            text = text.split("/", 1)[1]
    parts = [part for part in text.split("/") if part]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1] if parts else "unknown"


def files_changed() -> int:
    out = _git(["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"])
    return len([line for line in out.splitlines() if line.strip()])


def collect() -> dict:
    """Gather the ship row from the current git checkout."""
    remote = os.environ.get("MESH_SHIP_REMOTE", "origin")
    return {
        "machine": (os.environ.get("MESH_HOST") or socket.gethostname()).split(".")[0],
        "repo": repo_from_remote(_git(["remote", "get-url", remote])),
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"]) or None,
        "sha": _git(["rev-parse", "HEAD"]) or None,
        "subject": _git(["log", "-1", "--pretty=%s"]) or None,
        "files_changed": files_changed(),
    }


def publish(payload: dict) -> tuple[bool, str]:
    key = api_key()
    if not key:
        return False, "PI_CEO_API_KEY missing — ship feed not written"
    url = f"{api_url().rstrip('/')}/api/mesh/ship"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Pi-CEO-Secret": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return True, f"{response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read()[:200].decode(errors='replace')}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main() -> int:
    payload = collect()
    if "--print" in set(sys.argv[1:]):
        print(json.dumps(payload, indent=2))
        return 0
    ok, detail = publish(payload)
    print(json.dumps({"reported": ok, "detail": detail, "sha": payload.get("sha")}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
