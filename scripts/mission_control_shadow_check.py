"""Run the synthetic /control browser check and offline Jev advisory replay."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    dashboard = root / "dashboard"
    browser_cli = dashboard / "node_modules" / ".bin" / "playwright"
    if not browser_cli.is_file():
        print("Playwright is not installed in dashboard/node_modules", file=sys.stderr)
        return 2
    output = dashboard / "test-results" / "mission-control-shadow"
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    snapshot = output / "snapshot.jsonl"
    advisory = output / "advisory.jsonl"
    snapshot.unlink(missing_ok=True)
    advisory.unlink(missing_ok=True)
    env = os.environ.copy()
    env["MISSION_CONTROL_RECEIPT_PATH"] = str(snapshot)
    browser = subprocess.run(
        [str(browser_cli), "test", "e2e/mission-control-receipt.spec.ts"], cwd=dashboard, env=env, check=False
    )
    if not snapshot.is_file():
        print("Browser check produced no snapshot; advisory replay unavailable", file=sys.stderr)
        return browser.returncode or 2
    replay = subprocess.run(
        [sys.executable, str(root / "scripts" / "mission_control_jev_shadow.py"), str(snapshot), str(advisory)],
        cwd=root, check=False,
    )
    if replay.returncode == 0:
        print(f"Browser snapshot: {snapshot}\nOffline advisory receipt: {advisory}")
    if browser.returncode != 0:
        print("Browser assertions failed; advisory receipt is triage only", file=sys.stderr)
        return browser.returncode
    return replay.returncode


if __name__ == "__main__":
    os.umask(0o077)
    sys.exit(main())
