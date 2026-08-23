"""Fail-closed tool classification for recovery and parallel dispatch lanes."""
from __future__ import annotations

import shlex
import shutil
import sys
from pathlib import Path
from typing import Any

from setup_common import (
    SCRIPT_DIR,
    _normalise_tool_name,
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


def _has_signed_dispatch_admission(
    payload: dict[str, Any], project_root: Path, current_receipt: dict[str, Any]
) -> bool:
    """No signed dispatcher ships in this slice, so dispatch is never admitted."""
    del payload, project_root, current_receipt
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
    return False


def _trusted_python(token: str) -> bool:
    candidate = shutil.which(token) if Path(token).name == token else token
    if not candidate:
        return False
    try:
        return Path(candidate).resolve() == Path(sys.executable).resolve()
    except OSError:
        return False


def _single_option(argv: list[str], name: str) -> str | None:
    if any(token.startswith(f"{name}=") for token in argv):
        return None
    positions = [index for index, token in enumerate(argv) if token == name]
    if len(positions) != 1 or positions[0] + 1 >= len(argv):
        return None
    return argv[positions[0] + 1]


def _bound_grill_state(receipt: dict[str, Any]) -> Path | None:
    contract = receipt.get("setup_contract")
    control = contract.get("grill_control") if isinstance(contract, dict) else None
    raw_path = control.get("state_path") if isinstance(control, dict) else None
    if not isinstance(raw_path, str) or not raw_path:
        return None
    return Path(raw_path).expanduser().resolve()


def _tool_is_grill_driver(payload: dict[str, Any], receipt: dict[str, Any]) -> bool:
    """Admit exact machine transitions bound to this startup receipt."""
    name = _normalise_tool_name(payload.get("tool_name") or payload.get("tool") or "")
    if not any(marker in name for marker in ("bash", "exec", "command", "shell")):
        return False
    argv = _command_argv(payload)
    if argv is None or len(argv) < 3:
        return False
    if not _trusted_python(argv[0]):
        return False
    script = Path(argv[1]).expanduser().resolve()
    bound_state = _bound_grill_state(receipt)
    supplied_state = _single_option(argv, "--state")
    if script == (SCRIPT_DIR / "grill_session.py").resolve():
        if argv[2] not in {"start", "show", "validate", "evidence", "materialize"}:
            return False
        return bool(bound_state and supplied_state and Path(supplied_state).resolve() == bound_state)
    if script != (SCRIPT_DIR / "setup_driver.py").resolve() or argv[2] != "guard-dispatch":
        return False
    grill_session = _single_option(argv, "--grill-session")
    return bool(bound_state and grill_session and Path(grill_session).resolve() == bound_state)
