#!/usr/bin/env python3
"""Securely sync existing Margot Slack bridge credentials into Railway.

Source of truth:
- ~/.hermes/.env for existing key names / op:// references
- 1Password vault `hermes` when a value is an op:// reference

Security properties:
- never prints secret values
- never places secret values in Railway argv
- sends each value to Railway through stdin
- validates only key presence after sync
- stages credentials/channel first, then uses the final enable flag to trigger
  exactly one deployment in the explicitly selected Railway environment

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
CHANNEL_KEY = "SLACK_MARGOT_STRENGTHENING_CHANNEL"
CHANNEL_ID = "C0BTX0LRZQ8"
ENABLE_KEY = "SLACK_TELEGRAM_BRIDGE_ENABLED"
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
        # Values are supplied through stdin, not argv. Keep any CLI error bounded.
        message = (proc.stderr or proc.stdout or "Railway command failed").strip()
        raise RuntimeError(message[:500])
    return proc


def _set_variable(
    *,
    key: str,
    value: str,
    service: str,
    environment: str,
    skip_deploys: bool,
) -> None:
    args = [
        "variable", "set", key, "--stdin",
        "--service", service,
        "--environment", environment,
    ]
    if skip_deploys:
        args.append("--skip-deploys")
    _railway(args, stdin=value)
    print(f"synced {key} (value not shown)")


def sync_to_railway(
    values: dict[str, str],
    *,
    service: str,
    environment: str,
    deploy: bool,
) -> None:
    if shutil.which("railway") is None:
        raise RuntimeError("railway CLI is unavailable")

    # Stage both secrets and the known private strengthening channel without
    # triggering partial deployments. All commands target the environment by
    # name, so this does not depend on whichever environment happens to be
    # linked in the operator's local .railway state.
    staged = {
        **values,
        CHANNEL_KEY: CHANNEL_ID,
    }
    for key, value in staged.items():
        _set_variable(
            key=key,
            value=value,
            service=service,
            environment=environment,
            skip_deploys=True,
        )

    # The enable flag is intentionally last. With deploy=True it commits one
    # Railway deployment after the complete config is staged. With --no-deploy,
    # it is staged as well and no deployment is triggered.
    _set_variable(
        key=ENABLE_KEY,
        value="1",
        service=service,
        environment=environment,
        skip_deploys=not deploy,
    )

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
    required = [*staged, ENABLE_KEY]
    missing = [key for key in required if key not in present]
    if missing:
        raise RuntimeError("Railway verification missing: " + ", ".join(missing))
    print("Railway presence verification: PASS (values not shown)")
    if deploy:
        print(f"Railway deployment triggered once in environment: {environment}")
    else:
        print(f"Railway changes staged only in environment: {environment}")


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
    parser.add_argument("--no-deploy", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        values, sources = collect_existing_secrets(args.env_file.expanduser())
        print("Existing Slack credentials located securely:")
        for key in SECRET_KEYS:
            print(f"  {key}: present via {sources[key]} (value not shown)")
        print(f"  {CHANNEL_KEY}: {CHANNEL_ID}")
        print(f"  {ENABLE_KEY}: 1")

        if args.dry_run:
            print("DRY RUN: no Railway variables changed")
            return 0

        sync_to_railway(
            values,
            service=args.service,
            environment=args.environment,
            deploy=not args.no_deploy,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Slack bridge secret sync failed: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
