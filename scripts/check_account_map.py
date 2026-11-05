#!/usr/bin/env python3
"""Read-only validator for ops/ACCOUNT-MAP.yaml (RA-8187, AR-01).

The account map says which subscription login (Claude, Codex, Cursor) is pinned to which
machine, so the night queue can route work by each account's own headroom. It holds email
addresses only. Phill fills the emails; agents only validate the shape. This script never
writes anything.

Rules (each failure prints its rule name; any failure exits 1):

    FILE                 the map is missing or is not valid YAML
    DUPLICATE_KEY        one mapping repeats a key (YAML would silently keep only the last)
    SCHEMA               wrong top-level shape or version, empty lists, account pinned nowhere
    SECRET_FIELD         a key whose name looks like a credential, at any level
    UNKNOWN_KEY          a key outside the allowed schema
    SECRET_VALUE         a value or YAML comment that looks like a credential (key, JWT,
                         bearer, "password=...")
    MISSING_FIELD        an account lacks label, provider, plan, email or machines
    BAD_PROVIDER         provider is not claude, codex or cursor
    BAD_EMAIL            email is not a single well-formed address
    DUPLICATE_LABEL      two accounts share a label
    DUPLICATE_MACHINE    two machines share an id
    UNKNOWN_MACHINE      a pin names a machine the map does not declare
    CLAUDE_PIN_MISSING   a machine has no Claude account pinned
    CLAUDE_PIN_MULTIPLE  a machine has more than one Claude account pinned
    SHARED_CLAUDE_EMAIL  one Claude email is pinned on two or more machines
    PENDING_EMAIL        (only with --require-real) an email is still a .invalid placeholder

A placeholder email uses the reserved `.invalid` domain. It passes the shape checks but is
printed as PENDING, so a seed never reads as a live mapping.

    python3 scripts/check_account_map.py                    # validate the committed map
    python3 scripts/check_account_map.py --path other.yaml
    python3 scripts/check_account_map.py --require-real     # fail while any email is pending
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from account_map_secrets import (  # noqa: E402
    DuplicateKeyError, UniqueKeyLoader, comment_lines, looks_secret_name, looks_secret_value,
)

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "ops" / "ACCOUNT-MAP.yaml"
SCHEMA_VERSION = 1
PROVIDERS = ("claude", "codex", "cursor")
TOP_KEYS = {"version", "machines", "accounts"}
MACHINE_KEYS = {"id", "host", "notes"}
ACCOUNT_KEYS = {"label", "provider", "plan", "email", "machines", "notes"}
REQUIRED_ACCOUNT_KEYS = ("label", "provider", "plan", "email", "machines")
PLACEHOLDER_SUFFIX = ".invalid"

_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


@dataclass
class Finding:
    rule: str
    message: str


@dataclass
class Report:
    errors: list = field(default_factory=list)
    pending: list = field(default_factory=list)

    def error(self, rule: str, message: str) -> None:
        self.errors.append(Finding(rule, message))


def _scan_keys(node, where: str, allowed: set, report: Report) -> None:
    """Flag keys outside the allowlist. Secret-named keys are flagged by _scan_values."""
    for key in node:
        name = str(key)
        if name not in allowed and not looks_secret_name(name):
            report.error("UNKNOWN_KEY", f"{where}: key '{name}' is not part of the schema")


def _check_text(node: dict, keys: tuple, where: str, report: Report) -> None:
    """Free-text fields hold a string or null, never a nested structure or a number."""
    for key in keys:
        if key in node and node[key] is not None and not isinstance(node[key], str):
            report.error("SCHEMA", f"{where}: '{key}' must be text or null, "
                         f"got {type(node[key]).__name__}")


def _scan_values(node, where: str, report: Report) -> None:
    """At any depth, flag secret-named keys and string values that look like credentials."""
    if isinstance(node, dict):
        for key, value in node.items():
            if looks_secret_name(key):
                report.error("SECRET_FIELD", f"{where}: key '{key}' looks like a credential; "
                             "the map holds emails only")
            _scan_values(value, f"{where}.{key}", report)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _scan_values(value, f"{where}[{i}]", report)
    elif isinstance(node, str) and looks_secret_value(node):
        report.error("SECRET_VALUE", f"{where}: value looks like a credential; "
                     "remove it, the map holds emails only")


def _check_machines(machines, report: Report) -> list:
    ids = []
    for i, machine in enumerate(machines):
        where = f"machines[{i}]"
        if not isinstance(machine, dict) or not isinstance(machine.get("id"), str) \
                or not machine["id"].strip():
            report.error("SCHEMA", f"{where}: each machine needs a non-empty string 'id'")
            continue
        _scan_keys(machine, where, MACHINE_KEYS, report)
        _check_text(machine, ("host", "notes"), where, report)
        if machine["id"] in ids:
            report.error("DUPLICATE_MACHINE", f"{where}: machine id '{machine['id']}' repeats")
        ids.append(machine["id"])
    return ids


def _check_email(email, where: str, report: Report) -> None:
    if not isinstance(email, str) or not _EMAIL.match(email):
        report.error("BAD_EMAIL", f"{where}: email {email!r} is not a single valid address")


def _check_account(account, where: str, machine_ids: list, labels: set, report: Report) -> bool:
    """Check one account; return True when it is sound enough for the pin rules."""
    if not isinstance(account, dict):
        report.error("SCHEMA", f"{where}: each account must be a mapping")
        return False
    _scan_keys(account, where, ACCOUNT_KEYS, report)
    _check_text(account, ("plan", "notes"), where, report)
    missing = [k for k in REQUIRED_ACCOUNT_KEYS if k not in account]
    for key in missing:
        report.error("MISSING_FIELD", f"{where}: required field '{key}' is missing")
    label_ok = _check_label(account, where, labels, report)
    if "provider" in account and account["provider"] not in PROVIDERS:
        report.error("BAD_PROVIDER", f"{where}: provider {account['provider']!r} is not one of "
                     f"{', '.join(PROVIDERS)}")
    if "email" in account:
        _check_email(account["email"], where, report)
    pins = account.get("machines")
    if "machines" in account and (not isinstance(pins, list) or not pins
                                  or not all(isinstance(p, str) for p in pins)):
        report.error("SCHEMA", f"{where}: 'machines' must list at least one machine id string")
        return False
    for pin in pins or []:
        if pin not in machine_ids:
            report.error("UNKNOWN_MACHINE", f"{where}: pinned to undeclared machine {pin!r}")
    return not missing and label_ok


def _check_label(account: dict, where: str, labels: set, report: Report) -> bool:
    """A label must be a non-empty string and unique; return False when it is unusable."""
    if "label" not in account:
        return True  # reported as MISSING_FIELD by the caller
    label = account["label"]
    if not isinstance(label, str) or not label.strip():
        report.error("SCHEMA", f"{where}: 'label' must be a non-empty string, got {label!r}")
        return False
    if label in labels:
        report.error("DUPLICATE_LABEL", f"{where}: label '{label}' repeats")
    labels.add(label)
    return True


def _note_pending(account, where: str, require_real: bool, report: Report) -> None:
    label = account.get("label", where)
    email = account.get("email")
    if isinstance(email, str) and email.lower().endswith(PLACEHOLDER_SUFFIX):
        report.pending.append(f"{label}: email is a placeholder awaiting Phill")
        if require_real:
            report.error("PENDING_EMAIL", f"{where}: {label} still has a placeholder email")
    if account.get("plan") is None:
        report.pending.append(f"{label}: plan not yet recorded")


def _check_claude_pins(claude_accounts: list, machine_ids: list, report: Report) -> None:
    per_machine = {m: [] for m in machine_ids}
    machines_by_email = {}
    for account in claude_accounts:
        for pin in account["machines"]:
            if pin in per_machine:
                per_machine[pin].append(account["label"])
        if isinstance(account["email"], str):
            seen = machines_by_email.setdefault(account["email"].lower(), set())
            seen.update(account["machines"])
    for machine, labels in per_machine.items():
        if not labels:
            report.error("CLAUDE_PIN_MISSING", f"machine '{machine}' has no Claude account pinned")
        elif len(labels) > 1:
            report.error("CLAUDE_PIN_MULTIPLE", f"machine '{machine}' has {len(labels)} Claude "
                         f"accounts pinned ({', '.join(map(str, labels))}); exactly one allowed")
    for email, machines in machines_by_email.items():
        if len(machines) > 1:
            report.error("SHARED_CLAUDE_EMAIL", f"one Claude email is pinned on "
                         f"{len(machines)} machines ({', '.join(sorted(map(str, machines)))})")


def _check_top(data, report: Report) -> bool:
    if not isinstance(data, dict):
        report.error("SCHEMA", "the map must be a YAML mapping with version, machines, accounts")
        return False
    _scan_keys(data, "map", TOP_KEYS, report)
    if data.get("version") != SCHEMA_VERSION:
        report.error("SCHEMA", f"version must be {SCHEMA_VERSION}, got {data.get('version')!r}")
        return False
    for key in ("machines", "accounts"):
        if not isinstance(data.get(key), list) or not data[key]:
            report.error("SCHEMA", f"'{key}' must be a non-empty list")
            return False
    return True


def validate(data, require_real: bool = False) -> Report:
    report = Report()
    if not _check_top(data, report):
        return report
    _scan_values(data, "map", report)
    machine_ids = _check_machines(data["machines"], report)
    labels: set = set()
    claude = []
    for i, account in enumerate(data["accounts"]):
        where = f"accounts[{i}]"
        if _check_account(account, where, machine_ids, labels, report):
            _note_pending(account, where, require_real, report)
            if account["provider"] == "claude":
                claude.append(account)
    _check_claude_pins(claude, machine_ids, report)
    return report


def scan_comments(text: str, report: Report) -> None:
    """YAML comments are committed but dropped by the parser, so scan them as raw text."""
    for number, comment in comment_lines(text):
        if looks_secret_value(comment):
            report.error("SECRET_VALUE", f"line {number}: a comment looks like it holds a "
                         "credential; remove it, the map holds emails only")


def _load(path: Path, report: Report):
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.load(text, Loader=UniqueKeyLoader)  # noqa: S506 - SafeLoader subclass
    except DuplicateKeyError as exc:
        report.error("DUPLICATE_KEY", f"{path}: {exc}; the earlier value would be hidden")
    except OSError as exc:
        report.error("FILE", f"cannot read {path}: {exc.strerror or exc}")
    except yaml.YAMLError as exc:
        report.error("FILE", f"{path} is not valid YAML: {exc}")
    else:
        scan_comments(text, report)
        return data
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--require-real", action="store_true",
                        help="fail while any email is still a .invalid placeholder")
    args = parser.parse_args(argv)
    report = Report()
    data = _load(args.path, report)
    if not any(f.rule in ("FILE", "DUPLICATE_KEY") for f in report.errors):
        comment_findings = report.errors
        report = validate(data, require_real=args.require_real)
        report.errors[:0] = comment_findings
    for finding in report.errors:
        print(f"ERROR {finding.rule}: {finding.message}")
    for item in report.pending:
        print(f"PENDING: {item}")
    if report.errors:
        print(f"account map FAILED: {len(report.errors)} error(s) in {args.path}")
        return 1
    print(f"account map OK: {args.path} ({len(report.pending)} item(s) pending Phill)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
