"""Fail-closed tool classification for recovery and parallel dispatch lanes."""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any

from setup_common import (
    GRILL_READ_ONLY_COMMANDS,
    GRILL_STATE_COMMANDS,
    SCRIPT_DIR,
    SetupError,
    _normalise_tool_name,
    _read_json,
    _tool_command,
)


def _parallel_dispatch_context(contract: dict[str, Any]) -> str:
    policy = contract.get("orchestration_policy", {})
    if not isinstance(policy, dict) or policy.get("parallel_required") is not True:
        return ""
    return (
        " Parallel fanout is mandatory. First load Unlazy and produce a valid delivery contract "
        "with disjoint ownership; once its dispatch guard admits the leaves, dispatch independent "
        "workers immediately up to the admitted capacity. Do not begin root implementation first; "
        "root owns coordination and final proof; leaf and integration workers own every mutation."
    )


def _is_parallel_control_tool(payload: dict[str, Any]) -> bool:
    name = _normalise_tool_name(payload.get("tool_name") or payload.get("tool") or "")
    return name in {
        "wait_agent", "list_agents", "interrupt_agent", "send_message",
        "update_plan", "get_goal",
    }


def _is_parallel_dispatch_tool(payload: dict[str, Any]) -> bool:
    name = _normalise_tool_name(payload.get("tool_name") or payload.get("tool") or "")
    return name == "senior_harness_dispatch"


def _dispatch_fields(tool_input: dict[str, Any]) -> tuple[str, ...] | None:
    names = (
        "receipt_path", "plan_path", "routing_request_path", "state_path",
        "node_id", "worker_context_id",
    )
    if any(not isinstance(tool_input.get(key), str) or not tool_input[key] for key in names):
        return None
    return names


def _dispatch_receipt_matches(
    supplied: dict[str, Any], current: dict[str, Any], project_root: Path
) -> bool:
    supplied_contract = supplied.get("setup_contract", {})
    current_contract = current.get("setup_contract", {})
    if not isinstance(supplied_contract, dict) or not isinstance(current_contract, dict):
        return False
    fields = ("literal_objective", "task_id", "setup_contract_digest")
    if any(supplied_contract.get(field) != current_contract.get(field) for field in fields):
        return False
    if supplied.get("receipt_seal") != current.get("receipt_seal"):
        return False
    repository = supplied_contract.get("repository", {})
    if not isinstance(repository, dict):
        return False
    worktree = Path(str(repository.get("worktree", ""))).expanduser().resolve()
    return worktree == project_root.resolve()


def _has_signed_dispatch_admission(
    payload: dict[str, Any], project_root: Path, current_receipt: dict[str, Any]
) -> bool:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict) or _dispatch_fields(tool_input) is None:
        return False
    try:
        from control_plane import authorize_event

        receipt = _read_json(tool_input["receipt_path"])
        if not _dispatch_receipt_matches(receipt, current_receipt, project_root):
            return False
        result = authorize_event(
            receipt,
            _read_json(tool_input["plan_path"]),
            _read_json(tool_input["routing_request_path"]),
            {"tool_name": "senior-harness.dispatch", "tool_input": tool_input},
            state_path=tool_input["state_path"],
        )
        return result.get("status") == "admitted"
    except (ImportError, OSError, ValueError, KeyError, TypeError, SetupError):
        return False


def _safe_repo_argument(token: str) -> bool:
    if not token or token.startswith(("-", "/")) or any(char in token for char in "{}[]*?"):
        return False
    return ".." not in Path(token).parts


def _safe_test_argument(token: str, payload: dict[str, Any]) -> bool:
    if not _safe_repo_argument(token):
        return False
    raw_input = payload.get("tool_input")
    if not isinstance(raw_input, dict):
        raw_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    raw_cwd = payload.get("cwd") or "."
    requested = raw_input.get("workdir")
    try:
        checkout = Path(str(raw_cwd)).expanduser().resolve()
        if requested is not None and Path(str(requested)).expanduser().resolve() != checkout:
            return False
        candidate = (checkout / token.split("::", 1)[0]).resolve()
        candidate.relative_to((checkout / "tests").resolve())
    except (OSError, ValueError):
        return False
    return True


def _verification_argv(payload: dict[str, Any]) -> list[str] | None:
    command = _tool_command(payload)
    if command is None:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    requested = tool_input.get("workdir")
    bound = payload.get("cwd")
    try:
        if requested is not None and (
            not isinstance(bound, str)
            or not bound
            or Path(str(requested)).expanduser().resolve() != Path(bound).expanduser().resolve()
        ):
            return None
        return shlex.split(command)
    except (OSError, ValueError):
        return None


def _pytest_is_safe(argv: list[str], payload: dict[str, Any]) -> bool:
    allowed = {"-q", "-x", "-v", "-vv", "--disable-warnings", "--tb=short", "--tb=long"}
    return all(
        token in allowed if token.startswith("-") else _safe_test_argument(token, payload)
        for token in argv[1:]
    )


def _is_parallel_verification_tool(payload: dict[str, Any]) -> bool:
    name = _normalise_tool_name(payload.get("tool_name") or payload.get("tool") or "")
    if not any(marker in name for marker in ("bash", "exec", "command", "shell")):
        return False
    argv = _verification_argv(payload)
    if not argv or argv[0] != Path(argv[0]).name:
        return False
    executable = argv[0]
    if executable == "pytest":
        return _pytest_is_safe(argv, payload)
    if executable == "ruff":
        return len(argv) >= 2 and argv[1] == "check" and all(
            not token.startswith("-") and _safe_repo_argument(token) for token in argv[2:]
        )
    if executable in {"mypy", "pyright"}:
        return all(_safe_repo_argument(token) for token in argv[1:])
    return False


def _command_argv(payload: dict[str, Any]) -> list[str] | None:
    command = _tool_command(payload)
    if command is None:
        return None
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if not argv or any(token in {"&&", "||", ";", "|", ">", ">>", "<"} for token in argv):
        return None
    return argv


def _git_read_is_safe(args: list[str]) -> bool:
    while len(args) >= 2 and args[0] == "-C":
        args = args[2:]
    unsafe = ("--config", "--exec", "--ext-diff", "--output", "--paginate", "--textconv")
    return bool(args) and args[0] in {
        "diff", "log", "ls-files", "rev-parse", "show", "status",
    } and not any(
        any(arg == token or arg.startswith(token + "=") for token in unsafe) for arg in args
    )


def _python_grill_read_is_safe(argv: list[str]) -> bool:
    if len(argv) < 3:
        return False
    script = Path(os.path.expandvars(argv[1])).expanduser().resolve()
    return script == (SCRIPT_DIR / "grill_session.py").resolve() and argv[2] in GRILL_READ_ONLY_COMMANDS


def _recovery_command_is_safe(payload: dict[str, Any]) -> bool:
    argv = _command_argv(payload)
    if argv is None:
        return False
    executable = Path(argv[0]).name
    if executable in {"python", "python3"}:
        return _python_grill_read_is_safe(argv)
    if executable == "git":
        return _git_read_is_safe(argv[1:])
    if executable == "find" and any(
        arg in {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint"} for arg in argv
    ):
        return False
    if executable == "rg" and any(arg == "--pre" or arg.startswith("--pre=") for arg in argv[1:]):
        return False
    return executable in {"file", "find", "head", "ls", "pwd", "rg", "stat", "tail", "wc"}


def _tool_is_recovery_safe(payload: dict[str, Any]) -> bool:
    """Recognise exact read-only discovery tools; never infer safety from a substring."""
    name = _normalise_tool_name(payload.get("tool_name") or payload.get("tool") or "")
    safe = {
        "read", "grep", "glob", "webfetch", "web_fetch", "websearch", "web_search",
        "toolsearch", "tool_search", "web__run", "view_image", "list_mcp_resources",
        "list_mcp_resource_templates", "read_mcp_resource",
    }
    exa = {
        "mcp__exa__web_search_exa", "mcp__exa__get_code_context_exa",
        "mcp__exa__research_paper", "mcp__exa__company_research_exa",
        "mcp__exa__people_search_exa", "mcp__exa__crawling_exa",
    }
    if name in safe or name in exa or name.replace("mcp__plugin_exa_exa__", "mcp__exa__") in exa:
        return True
    if not any(marker in name for marker in ("bash", "exec", "command", "shell")):
        return False
    return _recovery_command_is_safe(payload)


def _tool_is_grill_driver(payload: dict[str, Any]) -> bool:
    """Admit only a direct invocation of the shipped Grill state controller."""
    name = _normalise_tool_name(payload.get("tool_name") or payload.get("tool") or "")
    if not any(marker in name for marker in ("bash", "exec", "command", "shell")):
        return False
    argv = _command_argv(payload)
    if argv is None or len(argv) < 3:
        return False
    executable = Path(argv[0]).name
    if re.fullmatch(r"python(?:3(?:\.\d+)*)?", executable) is None:
        return False
    script = Path(os.path.expandvars(argv[1])).expanduser().resolve()
    return script == (SCRIPT_DIR / "grill_session.py").resolve() and argv[2] in GRILL_STATE_COMMANDS
