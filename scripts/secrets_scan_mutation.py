#!/usr/bin/env python3
"""Prove secrets_check.py fails closed on a planted AWS-shaped key.

UNI-2651: a control that cannot be shown to fail is not a control. This plants
a clearly invented AWS access key ID in a scanned path, asserts the same
scanner CI uses exits 1 and names the plant, then removes it.

The token is assembled at runtime so this file never contains a contiguous
AKIA[0-9A-Z]{16} match — otherwise the scanner would fail the tree forever.
Always --dry-run: a gate must measure, not rewrite .gitignore.

First watched-red proof (UNI-2651, PR #758, commit a51100bb):
https://github.com/CleanExpo/Pi-Dev-Ops/actions/runs/34756270470/job/103721046991
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


# docs/ is in scope. tests/ is not — planting there would "prove" nothing.
# .ts is scanned; .md and *.tmp are skipped or gitignored.
PLANT_REL = "docs/.secrets-scan-mutation-plant.ts"
SCANNER = Path(__file__).resolve().parent / "secrets_check.py"


def plant_token() -> str:
    """Invented AWS access key ID. Split so this source is not itself a finding."""
    return "AKIA" + "00UNI2651PROOFZZ"


def write_plant(repo: Path, token: str) -> Path:
    path = repo / PLANT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'const k = "{token}"\n', encoding="utf-8")
    return path


def run_scan(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCANNER), "--repo-root", str(repo), "--dry-run"],
        text=True,
        capture_output=True,
        check=False,
    )


def assert_detected(result: subprocess.CompletedProcess[str]) -> None:
    combined = result.stdout + result.stderr
    if result.returncode != 1:
        raise SystemExit(
            f"FAIL: scanner exit {result.returncode}, expected 1 (secret found).\n"
            f"{combined}"
        )
    if PLANT_REL not in result.stdout:
        raise SystemExit(
            f"FAIL: scanner exited 1 but did not name {PLANT_REL}. "
            "Another finding is not this control.\n"
            f"{combined}"
        )
    if "AWS access key ID" not in result.stdout:
        raise SystemExit(
            f"FAIL: planted file was named but not classified as an AWS key.\n"
            f"{combined}"
        )


def assert_removed(result: subprocess.CompletedProcess[str]) -> None:
    if PLANT_REL in result.stdout:
        raise SystemExit(
            f"FAIL: {PLANT_REL} still reported after cleanup.\n"
            f"{result.stdout}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="UNI-2651 secrets-scan mutation")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parent.parent),
        help="Repository root to plant into and scan",
    )
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    plant = repo / PLANT_REL
    token = plant_token()

    print(f"UNI-2651 mutation — planting {PLANT_REL} under {repo}")
    try:
        write_plant(repo, token)
        detected = run_scan(repo)
        assert_detected(detected)
        print(f"  RED   scanner exit 1 and named {PLANT_REL}")
    finally:
        if plant.exists():
            plant.unlink()

    cleaned = run_scan(repo)
    assert_removed(cleaned)
    print(f"  GREEN plant removed; {PLANT_REL} no longer reported")
    print("PASS: secrets exposure scan fails closed on a planted key, then recovers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
