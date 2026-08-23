#!/usr/bin/env python3
"""Executable/import facade for deterministic Senior Harness startup admission."""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from setup_common import SCRIPT_DIR as SCRIPT_DIR

from app.server.routing_schema import RoutingValidationError as RoutingValidationError
from app.server.task_routing import decide_route as decide_route
from grill_session import GrillSessionError as GrillSessionError
from grill_session import file_digest as grill_file_digest
from grill_session import validate_receipt as validate_grill_receipt
from grill_session import validate_session as validate_grill_session
from senior_harness import ContractError as ContractError
from senior_harness import MUTATING_KINDS as MUTATING_KINDS
from senior_harness import digest as digest
from senior_harness import ready_moves as ready_moves
from senior_harness import validate_contract as validate_contract
from setup_common import ADAPTER_RECEIPT_ENV as ADAPTER_RECEIPT_ENV
from setup_common import CANONICAL_REPO_ROOT as CANONICAL_REPO_ROOT
from setup_common import GIT_SHA_PATTERN as GIT_SHA_PATTERN
from setup_common import GRILL_INTERACTIONS as GRILL_INTERACTIONS
from setup_common import GRILL_READ_ONLY_COMMANDS as GRILL_READ_ONLY_COMMANDS
from setup_common import GRILL_STATE_COMMANDS as GRILL_STATE_COMMANDS
from setup_common import READ_ONLY_GIT as READ_ONLY_GIT
from setup_common import REQUIRED_ADAPTER_EVIDENCE as REQUIRED_ADAPTER_EVIDENCE
from setup_common import REQUIRED_SKILLS as REQUIRED_SKILLS
from setup_common import SEAL_KEY_ENV as SEAL_KEY_ENV
from setup_common import SEAL_PREFIX as SEAL_PREFIX
from setup_common import SETUP_SCHEMA_VERSION as SETUP_SCHEMA_VERSION
from setup_common import SHA256_DIGEST_PATTERN as SHA256_DIGEST_PATTERN
from setup_common import STARTUP_ADMISSION as STARTUP_ADMISSION
from setup_common import STARTUP_AUTHORITY as STARTUP_AUTHORITY
from setup_common import ControlBindingResult as ControlBindingResult
from setup_common import GitProbeError as GitProbeError
from setup_common import SetupError as SetupError
from setup_common import _canonical_json as _canonical_json
from setup_common import _file_digest as _file_digest
from setup_common import _folder_digest as _folder_digest
from setup_common import _hook_output as _hook_output
from setup_common import _interaction_for_objective as _interaction_for_objective
from setup_common import _is_sha256_digest as _is_sha256_digest
from setup_common import _normalise_tool_name as _normalise_tool_name
from setup_common import _read_json as _read_json
from setup_delivery import guard_dispatch as guard_dispatch
from setup_hooks import handle_hook as handle_hook
from setup_receipts import _check_control_bindings as _check_control_bindings
from setup_receipts import _control_binding_errors as _control_binding_errors
from setup_receipts import _receipt_seal as _receipt_seal
from setup_receipts import _seal_key as _seal_key
from setup_receipts import _seal_key_path as _seal_key_path
from setup_receipts import admit_startup as admit_startup
from setup_repository import _candidate_skill_dirs as _candidate_skill_dirs
from setup_repository import _frontmatter_name as _frontmatter_name
from setup_repository import _git as _git
from setup_repository import _read_adapter_receipt as _read_adapter_receipt
from setup_repository import _repository_snapshot as _repository_snapshot
from setup_repository import _resolve_skill as _resolve_skill
from setup_repository import _surface_capabilities as _surface_capabilities
from setup_repository import build_setup_contract as build_setup_contract
from setup_state import _pending_objective_seal as _pending_objective_seal
from setup_state import _pending_quarantine_reason as _pending_quarantine_reason
from setup_state import _pending_reconciliation_reason as _pending_reconciliation_reason
from setup_state import _pending_state_path as _pending_state_path
from setup_state import _read_pending_objective as _read_pending_objective
from setup_state import _record_pending_objective as _record_pending_objective
from setup_state import _session_key as _session_key
from setup_state import _state_path as _state_path
from setup_state import _state_root as _state_root
from setup_state import _write_state as _write_state
from setup_tools import _has_signed_dispatch_admission as _has_signed_dispatch_admission
from setup_tools import _is_parallel_control_tool as _is_parallel_control_tool
from setup_tools import _is_parallel_dispatch_tool as _is_parallel_dispatch_tool
from setup_tools import _is_parallel_verification_tool as _is_parallel_verification_tool
from setup_tools import _parallel_dispatch_context as _parallel_dispatch_context
from setup_tools import _safe_repo_argument as _safe_repo_argument
from setup_tools import _safe_test_argument as _safe_test_argument
from setup_tools import _tool_is_grill_driver as _tool_is_grill_driver
from setup_tools import _tool_is_recovery_safe as _tool_is_recovery_safe
from setup_validation import validate_startup_receipt as validate_startup_receipt

__all__ = [
    "grill_file_digest",
    "validate_grill_receipt",
    "validate_grill_session",
    "time",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze and verify Senior Harness startup admission."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("objective")
    start.add_argument("--project", required=True)
    start.add_argument(
        "--surface", choices=("codex", "claude", "vscode-openrouter"), required=True
    )
    start.add_argument("--interaction", choices=("delivery", *GRILL_INTERACTIONS), default="delivery")
    start.add_argument("--strict-clean", action="store_true")
    start.add_argument("--skill-root", action="append", default=[])
    verify = sub.add_parser("verify")
    verify.add_argument("receipt")
    verify.add_argument("--objective")
    verify.add_argument("--project")
    guard = sub.add_parser("guard-dispatch")
    guard.add_argument("contract")
    guard.add_argument("receipt")
    guard.add_argument("--move-id", required=True)
    guard.add_argument("--problem-id")
    guard.add_argument("--grill-session")
    hook = sub.add_parser("hook")
    hook.add_argument("--surface", choices=("codex", "claude"), required=True)
    hook.add_argument(
        "--event", choices=("SessionStart", "UserPromptSubmit", "PreToolUse"), required=True
    )
    hook.add_argument("--allow-non-git", action="store_true")
    hook.add_argument("--skill-root", action="append", default=[])
    return parser


def _run_hook(args: argparse.Namespace) -> dict[str, Any]:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        return _hook_output(
            args.event, f"Senior Harness rejected malformed hook input: {exc}", deny=True
        )
    try:
        return handle_hook(
            payload, surface=args.surface, event=args.event,
            skill_search_roots=args.skill_root,
        )
    except SetupError as exc:
        if args.allow_non_git and isinstance(exc, GitProbeError):
            return _record_pending_objective(
                payload, surface=args.surface, event=args.event
            )
        return _hook_output(
            args.event,
            f"Senior Harness rejected hook input: {'; '.join(exc.errors)}",
            deny=True,
        )


def _run_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "start":
        contract = build_setup_contract(
            args.objective, args.project, surface=args.surface,
            interaction=args.interaction, strict_clean=args.strict_clean,
            skill_search_roots=args.skill_root,
        )
        return admit_startup(contract)
    if args.command == "verify":
        return validate_startup_receipt(
            _read_json(args.receipt), literal_objective=args.objective,
            project=args.project,
        )
    if args.command == "guard-dispatch":
        return guard_dispatch(
            _read_json(args.contract), _read_json(args.receipt), args.move_id,
            problem_id=args.problem_id,
            grill_session=_read_json(args.grill_session) if args.grill_session else None,
        )
    return _run_hook(args)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _run_command(args)
    except (SetupError, ContractError) as exc:
        errors = exc.errors if hasattr(exc, "errors") else [str(exc)]
        print(
            json.dumps({"status": "invalid", "errors": errors}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
