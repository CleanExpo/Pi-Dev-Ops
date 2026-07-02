#!/usr/bin/env python3
"""RA-1696 — automated desk voice stack preflight (non-interactive)."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def _check(name: str, ok: bool, detail: str = "") -> dict[str, object]:
    return {"name": name, "ok": ok, "detail": detail}


def main() -> int:
    checks: list[dict[str, object]] = []

    profile = Path.home() / "bron-workspace" / "voice" / "profile-locked.md"
    checks.append(_check("profile_locked", profile.exists(), str(profile)))

    py = Path.home() / ".hermes/hermes-agent/.venv/bin/python"
    if py.exists():
        r = subprocess.run(
            [str(py), "-c", "import faster_whisper; print(faster_whisper.__version__)"],
            capture_output=True,
            text=True,
        )
        checks.append(_check("faster_whisper", r.returncode == 0, r.stdout.strip() or r.stderr.strip()))
    else:
        checks.append(_check("faster_whisper", False, f"missing {py}"))

    try:
        with urllib.request.urlopen("http://127.0.0.1:8642/health", timeout=3) as resp:
            checks.append(_check("hermes_health", resp.status == 200))
    except Exception as exc:
        checks.append(_check("hermes_health", False, str(exc)))

    tts_rc = subprocess.run(
        [sys.executable, str(_REPO / "scripts/verify_margot_voice_tts.py"), "--json"],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
    )
    tts_ok = tts_rc.returncode == 0
    tts_detail = ""
    if tts_rc.stdout.strip():
        try:
            tts_detail = json.loads(tts_rc.stdout).get("latency_ms", "")
        except json.JSONDecodeError:
            tts_detail = tts_rc.stdout.strip()[:200]
    checks.append(_check("elevenlabs_tts", tts_ok, str(tts_detail)))

    report = {"ok": all(c["ok"] for c in checks), "checks": checks}
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
