#!/usr/bin/env python3
"""Securely sync existing Margot Slack bridge credentials into Railway.

Source of truth:
- ~/.hermes/.env for existing key names / op:// references
- 1Password vault `hermes` when a value is an op:// reference

Secret values are never printed or placed in Railway argv. Credential and
channel variables are staged first; the final enable flag triggers at most one
explicitly scoped deployment.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SECRET_KEYS = ("SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET")
CHANNEL_KEY = "SLACK_MARGOT_STRENGTHENING_CHANNEL"
CHANNEL_ID = "C0BTX0LRZQ8"
ENABLE_KEY = "SLACK_TELEGRAM_BRIDGE_ENABLED"
_ENV_LINE = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")


def _strip_quotes(value: str) -> str:
    """Remove one matching pair of shell-style quotes from a value."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def read_env_keys(path: Path) -> dict[str, str]:
    """Read only the two Slack secret entries without evaluating shell syntax."""
    found: dict[str, str] = {}
    if not path.is_file():
        return found
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE.match(line)
        if match and match.group(1) in SECRET_KEYS:
            found[match.group(1)] = _strip_quotes(match.group(2))
    return found


def resolve_secret(raw: str, *, key: str) -> tuple[str, str]:
    """Resolve plaintext or an op:// reference without exposing the secret."""
    value = (raw or "").strip()
    if not value:
        raise RuntimeError(f"{key} is empty")
    if not value.startswith("op://"):
        return value, "hermes-env"
    if shutil.which("op") is None:
        raise RuntimeError(f"{key} is a 1Password reference but `op` CLI is unavailable")
    proc = subprocess.run(
        ["op", "read", value], capture_output=True, text=True,
        check=False, timeout=30,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"could not resolve {key} from 1Password")
    return proc.stdout.strip(), "1password"


def collect_existing_secrets(env_file: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Collect Slack secrets from Hermes first, then the current process env."""
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


def _railway(
    args: list[str], *, stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run Railway CLI with optional secret data supplied only through stdin."""
    proc = subprocess.run(
        ["railway", *args], input=stdin, capture_output=True, text=True,
        check=False, timeout=120,
    )
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "Railway command failed").strip()
        raise RuntimeError(message[:500])
    return proc


def _set_variable(
    *, key: str, value: str, service: str, environment: str,
    skip_deploys: bool,
) -> None:
    """Set one Railway variable through stdin with explicit service/environment."""
    args = [
        "variable", "set", key, "--stdin",
        "--service", service, "--environment", environment,
    ]
    if skip_deploys:
        args.append("--skip-deploys")
    _railway(args, stdin=value)
    print(f"synced {key} (value not shown)")


def _stage_variables(
    values: dict[str, str], *, service: str, environment: str,
) -> list[str]:
    """Stage credentials and channel without triggering partial deployments."""
    staged = {**values, CHANNEL_KEY: CHANNEL_ID}
    for key, value in staged.items():
        _set_variable(
            key=key, value=value, service=service,
            environment=environment, skip_deploys=True,
        )
    return list(staged)


def _railway_variable_names(*, service: str, environment: str) -> set[str]:
    """Return Railway variable names only; discard values immediately."""
    verify = _railway([
        "variable", "list", "--kv",
        "--service", service, "--environment", environment,
    ])
    return {
        line.partition("=")[0].strip()
        for line in verify.stdout.splitlines() if "=" in line
    }


def _verify_required_keys(
    required: list[str], *, service: str, environment: str,
) -> None:
    """Fail if any required variable name is absent from Railway."""
    present = _railway_variable_names(service=service, environment=environment)
    missing = [key for key in required if key not in present]
    if missing:
        raise RuntimeError("Railway verification missing: " + ", ".join(missing))
    print("Railway presence verification: PASS (values not shown)")


def sync_to_railway(
    values: dict[str, str], *, service: str, environment: str, deploy: bool,
) -> None:
    """Stage complete bridge config, optionally deploy once, then verify names."""
    if shutil.which("railway") is None:
        raise RuntimeError("railway CLI is unavailable")
    required = _stage_variables(values, service=service, environment=environment)
    _set_variable(
        key=ENABLE_KEY, value="1", service=service, environment=environment,
        skip_deploys=not deploy,
    )
    required.append(ENABLE_KEY)
    _verify_required_keys(required, service=service, environment=environment)
    action = "deployment triggered once" if deploy else "changes staged only"
    print(f"Railway {action} in environment: {environment}")


def _parser() -> argparse.ArgumentParser:
    """Build the operator CLI parser."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env-file", type=Path, default=Path.home() / ".hermes" / ".env",
        help="Existing Hermes env/op:// reference file (default: ~/.hermes/.env)",
    )
    parser.add_argument("--service", default="Pi-Dev-Ops")
    parser.add_argument("--environment", default="production")
    parser.add_argument("--no-deploy", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _report_sources(sources: dict[str, str]) -> None:
    """Report credential provenance without disclosing any credential value."""
    print("Existing Slack credentials located securely:")
    for key in SECRET_KEYS:
        print(f"  {key}: present via {sources[key]} (value not shown)")
    print(f"  {CHANNEL_KEY}: {CHANNEL_ID}")
    print(f"  {ENABLE_KEY}: 1")


def main(argv: list[str] | None = None) -> int:
    """Resolve existing credentials, sync them safely, and return shell status."""
    args = _parser().parse_args(argv)
    try:
        values, sources = collect_existing_secrets(args.env_file.expanduser())
        _report_sources(sources)
        if args.dry_run:
            print("DRY RUN: no Railway variables changed")
            return 0
        sync_to_railway(
            values, service=args.service, environment=args.environment,
            deploy=not args.no_deploy,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Slack bridge secret sync failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
