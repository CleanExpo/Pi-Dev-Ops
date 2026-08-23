#!/usr/bin/env python3
"""Executable facade for deterministic Senior Harness contract validation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from senior_harness_attempts import validate_attempts
from senior_harness_core import (
    REPO_ROOT,
    SCHEMA_VERSION,
    ContractError,
    attempt_fingerprint,
    bind_attempt,
    digest,
    intake,
    skill_folder_digest,
)
from senior_harness_moves import MUTATING_KINDS, validate_moves
from senior_harness_policy import (
    validate_authority,
    validate_capability_pack,
    validate_discovery_and_forecasts,
    validate_routing_and_verification,
)
from senior_harness_repository import validate_repository


__all__ = [
    "ContractError",
    "MUTATING_KINDS",
    "attempt_fingerprint",
    "bind_attempt",
    "digest",
    "intake",
    "ready_moves",
    "skill_folder_digest",
    "validate_contract",
]


def validate_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Validate the complete contract through each responsibility-specific module."""
    errors: list[str] = []
    if contract.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if contract.get("stage") != "delivery-contract":
        errors.append("stage must be delivery-contract")
    expected_task_id = digest({"task": contract.get("literal_request")})[7:23]
    if contract.get("task_id") != expected_task_id:
        errors.append("task_id must be derived from the exact literal_request")
    moves, longest_path = validate_moves(contract, errors)
    validate_authority(contract, moves, errors)
    validate_discovery_and_forecasts(contract, moves, errors)
    validate_repository(contract, errors)
    validate_routing_and_verification(contract, errors)
    validate_attempts(contract, errors)
    validate_capability_pack(contract, errors)
    if errors:
        raise ContractError(errors)
    return {
        "status": "valid",
        "schema_version": SCHEMA_VERSION,
        "task_id": contract["task_id"],
        "contract_digest": digest(contract),
        "move_count": len(moves),
        "longest_path": longest_path,
        "horizon_required": contract["classification"]["horizon_required"],
    }


def ready_moves(contract: dict[str, Any]) -> list[str]:
    """Return admitted nonmutating delivery moves whose dependencies passed."""
    validate_contract(contract)
    moves = {move["move_id"]: move for move in contract["move_graph"]}
    terminal = {move_id for move_id, move in moves.items() if move["status"] == "passed"}
    ready = [
        move_id
        for move_id, move in moves.items()
        if move["plane"] == "delivery"
        and move["kind"] != "admit"
        and move["kind"] not in MUTATING_KINDS
        and move["status"] in {"admitted", "ready"}
        and all(parent in terminal for parent in move["parents"])
        and all(prerequisite in terminal for prerequisite in move["prerequisites"])
    ]
    return ready[: contract["limits"]["max_parallel_workers"]]


def _read_json(path: str | None) -> dict[str, Any]:
    try:
        raw = sys.stdin.read() if not path or path == "-" else Path(path).read_text(encoding="utf-8")
        value = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        raise ContractError([f"unable to read JSON: {exc}"]) from exc
    if not isinstance(value, dict):
        raise ContractError(["top-level JSON must be an object"])
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile and gate Senior Harness task contracts.")
    sub = parser.add_subparsers(dest="command", required=True)
    intake_parser = sub.add_parser("intake", help="Create a bounded intake envelope from a literal request.")
    intake_parser.add_argument("task")
    intake_parser.add_argument("--horizon-required", action="store_true")
    sub.add_parser("where", help="Show the physical canonical skill and Pi-Dev-Ops source paths.")
    bind_parser = sub.add_parser("bind-attempt", help="Bind an attempt to a frozen task before fingerprinting.")
    bind_parser.add_argument("contract_path")
    bind_parser.add_argument("attempt_path")
    for command in ("lint", "ready", "fingerprint"):
        child = sub.add_parser(command)
        child.add_argument("path", nargs="?", default="-")
    return parser


def _command_result(args: argparse.Namespace) -> Any:
    if args.command == "intake":
        return intake(args.task, args.horizon_required)
    if args.command == "where":
        return {
            "skill_root": str(Path(__file__).resolve().parents[1]),
            "skill_folder_digest": skill_folder_digest(),
            "repository_root": str(REPO_ROOT),
            "model_router": str(REPO_ROOT / "skills" / "model-router" / "SKILL.md"),
            "unlazy": str(REPO_ROOT / "skills" / "unlazy" / "SKILL.md"),
        }
    if args.command == "bind-attempt":
        return bind_attempt(_read_json(args.contract_path), _read_json(args.attempt_path))
    payload = _read_json(args.path)
    if args.command == "lint":
        return validate_contract(payload)
    if args.command == "ready":
        return {"status": "valid", "ready": ready_moves(payload)}
    return {"fingerprint": attempt_fingerprint(payload)}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        print(json.dumps(_command_result(args), indent=2, sort_keys=True))
        return 0
    except ContractError as exc:
        print(json.dumps({"status": "invalid", "errors": exc.errors}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
