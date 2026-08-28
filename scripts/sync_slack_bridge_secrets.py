#!/usr/bin/env python3
"""Securely sync existing Margot Slack bridge credentials into Railway.

Source of truth:
- ~/.hermes/.env for existing key names / op:// references
- 1Password vault `hermes` when a value is an op:// reference

Security properties:
- never prints secret values
- never places secret values in argv
- sends each value to Railway through stdin
- validates only key presence after sync
- batches Railway changes with --skip-deploys, then performs one redeploy

This script intentionally does not create, rotate, or invent Slack credentials.
It only reuses credentials that already exist in the established secret chain.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SECRET_KEYS = (
    "SLACK_BOT_TOKEN",
    "SLACK_SIGNING_SECRET",
)
STATIC_VALUES = {
    "SLACK_MARGOT_STRENGTHENING_CHANNEL": "C0BTX0LRZQ8",
    "SLACK_TELEGRAM_BRIDGE_ENABLED": "1",
}
_ENV_LINE = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def read_env_keys(path: Path) -> dict[str, str]:
    """Read only the Slack keys we need; never evaluate shell syntax."""
    found: dict[str, str] = {}
    if not path.is_file():
        return found
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE.match(line)
        if not match:
            continue
        key, raw = match.groups()
        if key in SECRET_KEYS:
            found[key] = _strip_quotes(raw)
    return found


def resolve_secret(raw: str, *, key: str) -> tuple[str, str]:
    """Resolve plaintext or op:// reference without exposing the value."""
    value = (raw or "").strip()
    if not value:
        raise RuntimeError(f"{key} is empty")
    if not value.startswith("op://"):
        return value, "hermes-env"
    if shutil.which("op") is None:
        raise RuntimeError(f"{key} is a 1Password reference but `op` CLI is unavailable")
    proc = subprocess.run(
        ["op", "read", value],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"could not resolve {key} from 1Password")
    return proc.stdout.strip(), "1password"


def collect_existing_secrets(env_file: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Collect existing secrets using ~/.hermes/.env first, process env second."""
    raw = read_env_keys(env_file)
    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for key in SECRET_KEYS:
        candidate = raw.get(key) or (os.environ.get(key) or "").strip()
        if not candidate:
            raise RuntimeError(f"{key} was not found in {env_file} or the current environment")
        value, source = resolve_secret(candidate, key=key)
        values[key] = value
        sources[key] = source if key in raw else "process-env"
    return values, sources


def _railway(args: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["railway", *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0:
        # Railway output should not contain stdin values; still keep reporting bounded.
        message = (proc.stderr or proc.stdout or "Railway command failed").strip()
        raise RuntimeError(message[:500])
    return proc


def sync_to_railway(
    values: dict[str, str],
    *,
    service: str,
    environment: str,
    redeploy: bool,
) -> None:
    if shutil.which("railway") is None:
        raise RuntimeError("railway CLI is unavailable")

    assignments = {**values, **STATIC_VALUES}
    for key, value in assignments.items():
        _railway(
            [
                "variable", "set", key, "--stdin",
                "--service", service,
                "--environment", environment,
                "--skip-deploys",
            ],
            stdin=value,
        )
        print(f"synced {key} (value not shown)")

    verify = _railway([
        "variable", "list", "--kv",
        "--service", service,
        "--environment", environment,
    ])
    present = {
        line.partition("=")[0].strip()
        for line in verify.stdout.splitlines()
        if "=" in line
    }
    missing = [key for key in assignments if key not in present]
    if missing:
        raise RuntimeError("Railway verification missing: " + ", ".join(missing))
    print("Railway presence verification: PASS (values not shown)")

    if redeploy:
        # Existing Pi-Dev-Ops scripts use the linked Railway project/environment.
        # Variable writes above are explicitly scoped to production; redeploy once
        # after all four values are staged to avoid four needless deployments.
        _railway(["redeploy", "--service", service, "--yes"])
        print("Railway redeploy requested once after secret sync")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path.home() / ".hermes" / ".env",
        help="Existing Hermes env/op:// reference file (default: ~/.hermes/.env)",
    )
    parser.add_argument("--service", default="Pi-Dev-Ops")
    parser.add_argument("--environment", default="production")
    parser.add_argument("--no-redeploy", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        values, sources = collect_existing_secrets(args.env_file.expanduser())
        print("Existing Slack credentials located securely:")
        for key in SECRET_KEYS:
            print(f"  {key}: present via {sources[key]} (value not shown)")
        print(f"  SLACK_MARGOT_STRENGTHENING_CHANNEL: {STATIC_VALUES['SLACK_MARGOT_STRENGTHENING_CHANNEL']}")
        print("  SLACK_TELEGRAM_BRIDGE_ENABLED: 1")

        if args.dry_run:
            print("DRY RUN: no Railway variables changed")
            return 0

        sync_to_railway(
            values,
            service=args.service,
            environment=args.environment,
            redeploy=not args.no_redeploy,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Slack bridge secret sync failed: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
