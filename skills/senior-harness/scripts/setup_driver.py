#!/usr/bin/env python3
"""Deterministic startup admission for the Senior Harness.

This driver freezes the literal objective and binds it to a real Git checkout,
the installed control skills, and a truthful host-capability probe.  It performs
no model, provider, connector, or network calls.  Startup admission is not
mutation authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
CANONICAL_REPO_ROOT = Path(__file__).resolve().parents[3]
for import_root in (SCRIPT_DIR, CANONICAL_REPO_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from app.server.task_routing import decide_route  # noqa: E402
from app.server.routing_schema import RoutingValidationError  # noqa: E402
from senior_harness import ContractError, MUTATING_KINDS, digest, ready_moves, validate_contract  # noqa: E402


SETUP_SCHEMA_VERSION = "1.0"
REQUIRED_SKILLS = ("senior-harness", "model-router", "unlazy")
STARTUP_AUTHORITY = {
    "startup_admission": "pending",
    "mutation_authority": False,
    "business_authority": False,
    "irreversible_authority": False,
}
STARTUP_ADMISSION = {
    "startup_only": True,
    "objective_lock_on_mediated_tools": True,
    "dispatch_authority": "nonmutating-only",
    "mutation_authority": False,
    "business_authority": False,
    "irreversible_authority": False,
}
READ_ONLY_GIT = {
    ("rev-parse", "--show-toplevel"),
    ("rev-parse", "HEAD"),
    ("status", "--porcelain=v1", "--untracked-files=all"),
}


class SetupError(ValueError):
    """Raised when startup cannot be admitted safely."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _folder_digest(root: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        hasher.update(path.relative_to(root).as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return "sha256:" + hasher.hexdigest()


def _git(project: Path, *args: str) -> str:
    if tuple(args) not in READ_ONLY_GIT:
        raise SetupError([f"setup driver refused non-read-only git probe: {' '.join(args)}"])
    try:
        result = subprocess.run(
            ["git", "-C", str(project), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SetupError([f"git probe failed for {project}: {exc}"]) from exc
    return result.stdout


def _frontmatter_name(skill_file: Path) -> str | None:
    try:
        lines = skill_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip('"\'')
    return None


def _candidate_skill_dirs(name: str, project_root: Path, search_roots: Iterable[Path] | None) -> list[Path]:
    roots = list(search_roots or ())
    if not roots:
        roots.extend(
            [
                project_root / "skills",
                Path.home() / ".codex" / "skills",
                Path.home() / ".claude" / "skills",
            ]
        )
    candidates: list[Path] = []
    for root in roots:
        candidate = root if root.name == name else root / name
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _resolve_skill(name: str, project_root: Path, search_roots: Iterable[Path] | None) -> dict[str, str]:
    errors: list[str] = []
    for candidate in _candidate_skill_dirs(name, project_root, search_roots):
        if candidate.is_symlink() and not candidate.exists():
            errors.append(f"broken skill symlink: {candidate}")
            continue
        skill_file = candidate / "SKILL.md"
        if not skill_file.is_file():
            continue
        observed_name = _frontmatter_name(skill_file)
        if observed_name != name:
            errors.append(f"skill {candidate} declares name={observed_name!r}, expected {name!r}")
            continue
        resolved = candidate.resolve()
        return {
            "name": name,
            "path": str(resolved),
            "folder_digest": _folder_digest(resolved),
        }
    if errors:
        raise SetupError(errors)
    raise SetupError([f"required skill is unavailable: {name}"])


def _repository_snapshot(project: Path, *, strict_clean: bool) -> dict[str, Any]:
    requested = project.resolve()
    root = Path(_git(requested, "rev-parse", "--show-toplevel").strip()).resolve()
    if requested != root:
        raise SetupError([f"project must be the exact Git checkout root: requested={requested}, root={root}"])
    head = _git(root, "rev-parse", "HEAD").strip()
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if strict_clean and status:
        raise SetupError(["strict startup requires a clean Git checkout"])
    return {
        "worktree": str(root),
        "head_sha": head,
        "dirty": bool(status),
        "worktree_state_digest": "sha256:" + hashlib.sha256(status.encode("utf-8")).hexdigest(),
    }


def build_setup_contract(
    literal_objective: str,
    project: str | Path,
    *,
    surface: str,
    strict_clean: bool = False,
    skill_search_roots: Iterable[str | Path] | None = None,
    host_capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze startup inputs without dispatching or mutating the project."""
    if not isinstance(literal_objective, str) or not literal_objective.strip():
        raise SetupError(["literal objective must be non-empty"])
    if surface not in {"codex", "claude", "vscode-openrouter"}:
        raise SetupError([f"unsupported surface: {surface}"])
    project_root = Path(project).resolve()
    search_roots = [Path(item).resolve() for item in skill_search_roots or ()]
    repository = _repository_snapshot(project_root, strict_clean=strict_clean)
    skills = {
        name: _resolve_skill(name, project_root, search_roots)
        for name in REQUIRED_SKILLS
    }
    capabilities = host_capabilities or {
        "lifecycle_hooks": "unknown",
        "pre_tool_use": "unknown",
        "specialized_tool_interception": "unknown",
        "evidence": "not-probed",
    }
    router_harness = "claude-code" if surface == "claude" else surface
    routing_request = {
        "schema_version": "1.0",
        "request_id": digest(
            {
                "objective": literal_objective,
                "worktree": repository["worktree"],
                "head_sha": repository["head_sha"],
                "surface": surface,
            }
        )[7:39],
        "task": literal_objective,
        "harness": router_harness,
        "signals": {
            "determinism": "medium",
            "ambiguity": "high",
            "scope": "project",
            "dependency_count": 2,
            "reasoning_depth": "deep",
            "stakes": ["none"],
            "volume": 3,
            "expected_minutes": 180,
            "context_tokens_estimate": 12000,
            "modalities": ["text", "code"],
            "required_tools": ["read", "edit", "test"],
            "sensitivity": "internal",
            "prior_failures": 0,
            "ownership_disjoint": False,
        },
        "limits": {
            "max_cost_usd": None,
            "max_quota_units": None,
            "deadline_seconds": 1800,
            "max_parallel_workers": 4,
        },
        "capabilities": {
            "local_quality_floors": list(capabilities.get("local_quality_floors", [])),
            "supports_parallel": capabilities.get("supports_parallel") is True,
            "supports_model_override": capabilities.get("supports_model_override") is True,
            "supports_cancellation": capabilities.get("supports_cancellation") is True,
        },
    }
    route_decision = decide_route(routing_request).to_dict()
    contract: dict[str, Any] = {
        "schema_version": SETUP_SCHEMA_VERSION,
        "stage": "setup-contract",
        "literal_objective": literal_objective,
        "task_id": digest({"task": literal_objective})[7:23],
        "objective_digest": digest({"task": literal_objective}),
        "surface": surface,
        "repository": repository,
        "required_skills": skills,
        "host_capabilities": capabilities,
        "routing_request": routing_request,
        "route_decision": route_decision,
        "delivery_controller": {
            "skill_id": "unlazy",
            "required": True,
            "owns": ["decomposition", "leaf-gates", "integration-gates", "exact-candidate-receipts"],
            "dispatch_after": "valid-delivery-contract-and-guard-dispatch",
        },
        "secondary_objectives": [],
        "authority": dict(STARTUP_AUTHORITY),
    }
    contract["setup_contract_digest"] = digest(contract)
    return contract


def admit_startup(contract: dict[str, Any]) -> dict[str, Any]:
    """Issue an integrity-bound startup receipt; never issue mutation authority."""
    expected = dict(contract)
    observed_digest = expected.pop("setup_contract_digest", None)
    if observed_digest != digest(expected):
        raise SetupError(["setup contract digest is invalid"])
    if contract.get("stage") != "setup-contract":
        raise SetupError(["setup contract stage is invalid"])
    if contract.get("authority") != STARTUP_AUTHORITY:
        raise SetupError(["setup contract cannot grant mutation, business, or irreversible authority"])
    objective = contract.get("literal_objective")
    if not isinstance(objective, str) or not objective.strip():
        raise SetupError(["setup contract literal objective is invalid"])
    if contract.get("task_id") != digest({"task": objective})[7:23]:
        raise SetupError(["setup contract task id is not bound to its literal objective"])
    if contract.get("objective_digest") != digest({"task": objective}):
        raise SetupError(["setup contract objective digest is invalid"])
    if contract.get("secondary_objectives") != []:
        raise SetupError(["setup contract cannot pre-authorize secondary objectives"])
    receipt: dict[str, Any] = {
        "schema_version": SETUP_SCHEMA_VERSION,
        "stage": "startup-admitted",
        "setup_contract": contract,
        "driver_digest": _file_digest(Path(__file__).resolve()),
        "admission": dict(STARTUP_ADMISSION),
    }
    receipt["receipt_integrity_digest"] = digest(receipt)
    return receipt


def validate_startup_receipt(
    receipt: dict[str, Any],
    *,
    literal_objective: str | None = None,
    project: str | Path | None = None,
    verify_repository: bool = True,
) -> dict[str, Any]:
    """Re-probe all bound local evidence and reject stale or altered receipts."""
    errors: list[str] = []
    candidate = dict(receipt)
    observed_digest = candidate.pop("receipt_integrity_digest", None)
    if observed_digest != digest(candidate):
        errors.append("startup receipt integrity digest is invalid")
    if receipt.get("stage") != "startup-admitted":
        errors.append("startup receipt stage is invalid")
    if receipt.get("admission") != STARTUP_ADMISSION:
        errors.append("startup receipt cannot grant mutation, business, or irreversible authority")
    contract = receipt.get("setup_contract")
    if not isinstance(contract, dict):
        errors.append("startup receipt is missing its setup contract")
        contract = {}
    embedded = dict(contract)
    embedded_digest = embedded.pop("setup_contract_digest", None)
    if embedded_digest != digest(embedded):
        errors.append("embedded setup contract digest is invalid")
    if literal_objective is not None and contract.get("literal_objective") != literal_objective:
        errors.append("literal objective differs from the frozen startup objective")
    objective = contract.get("literal_objective")
    if contract.get("schema_version") != SETUP_SCHEMA_VERSION or contract.get("stage") != "setup-contract":
        errors.append("embedded setup contract schema or stage is invalid")
    if not isinstance(objective, str) or not objective.strip():
        errors.append("embedded setup contract literal objective is invalid")
    else:
        if contract.get("task_id") != digest({"task": objective})[7:23]:
            errors.append("embedded setup contract task id is invalid")
        if contract.get("objective_digest") != digest({"task": objective}):
            errors.append("embedded setup contract objective digest is invalid")
    if contract.get("secondary_objectives") != []:
        errors.append("embedded setup contract cannot pre-authorize secondary objectives")
    if contract.get("authority") != STARTUP_AUTHORITY:
        errors.append("setup contract cannot grant mutation, business, or irreversible authority")
    routing_request = contract.get("routing_request")
    if not isinstance(routing_request, dict) or routing_request.get("task") != contract.get("literal_objective"):
        errors.append("routing request does not preserve the frozen startup objective")
    else:
        try:
            current_route = decide_route(routing_request).to_dict()
        except RoutingValidationError as exc:
            errors.append(f"routing request is invalid: {exc}")
        else:
            if _canonical_json(current_route) != _canonical_json(contract.get("route_decision")):
                errors.append("route decision changed after startup admission")
    controller = contract.get("delivery_controller")
    if not isinstance(controller, dict) or controller.get("skill_id") != "unlazy" or controller.get("required") is not True:
        errors.append("startup receipt does not require Unlazy delivery control")
    repository = contract.get("repository") if isinstance(contract.get("repository"), dict) else {}
    if verify_repository:
        bound_project = Path(project or repository.get("worktree", "")).resolve()
        try:
            current = _repository_snapshot(bound_project, strict_clean=False)
        except SetupError as exc:
            errors.extend(exc.errors)
            current = {}
        for field in ("worktree", "head_sha", "dirty", "worktree_state_digest"):
            if repository.get(field) != current.get(field):
                errors.append(f"repository {field} changed after startup admission")
    skills = contract.get("required_skills")
    if not isinstance(skills, dict):
        errors.append("startup receipt has no required-skill evidence")
        skills = {}
    for name in REQUIRED_SKILLS:
        item = skills.get(name)
        if not isinstance(item, dict):
            errors.append(f"startup receipt is missing skill {name}")
            continue
        path = Path(str(item.get("path", "")))
        if not path.is_dir() or _frontmatter_name(path / "SKILL.md") != name:
            errors.append(f"bound skill is unavailable or invalid: {name}")
        elif item.get("folder_digest") != _folder_digest(path):
            errors.append(f"bound skill changed after startup admission: {name}")
    if receipt.get("driver_digest") != _file_digest(Path(__file__).resolve()):
        errors.append("setup driver changed after startup admission")
    if errors:
        raise SetupError(errors)
    return {
        "status": "valid",
        "task_id": contract["task_id"],
        "objective_digest": contract["objective_digest"],
        "head_sha": repository["head_sha"],
        "enforcement_scope": "mediated-nonmutating-dispatch",
    }


def _hook_output(event: str, context: str, *, deny: bool = False) -> dict[str, Any]:
    if event == "PreToolUse" and deny:
        return {
            "hookSpecificOutput": {
                "hookEventName": event,
                "permissionDecision": "deny",
                "permissionDecisionReason": context,
            }
        }
    if event in {"SessionStart", "UserPromptSubmit", "PreToolUse"}:
        return {
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": context,
            }
        }
    return {"continue": not deny, "stopReason": context if deny else None, "systemMessage": context}


def _state_path(project_root: Path, session_id: str) -> Path:
    safe_session = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)[:160]
    if not safe_session:
        raise SetupError(["hook payload has no usable session id"])
    override = os.environ.get("SENIOR_HARNESS_STATE_DIR")
    root = Path(override).resolve() if override else project_root / ".harness" / "senior-harness"
    return root / f"{safe_session}.json"


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def handle_hook(payload: dict[str, Any], *, surface: str, event: str) -> dict[str, Any]:
    """Adapt one Codex/Claude lifecycle event to the portable startup contract."""
    if surface not in {"codex", "claude"}:
        raise SetupError([f"hook surface is unsupported: {surface}"])
    if event not in {"SessionStart", "UserPromptSubmit", "PreToolUse"}:
        raise SetupError([f"hook event is unsupported: {event}"])
    if not isinstance(payload, dict):
        raise SetupError(["hook payload must be a JSON object"])
    observed_event = payload.get("hook_event_name")
    if observed_event and observed_event != event:
        raise SetupError([f"hook event mismatch: configured={event}, observed={observed_event}"])
    session_id = payload.get("session_id")
    cwd = payload.get("cwd")
    if not isinstance(session_id, str) or not session_id:
        raise SetupError(["hook payload is missing session_id"])
    if not isinstance(cwd, str) or not cwd:
        raise SetupError(["hook payload is missing cwd"])
    project_root = Path(_git(Path(cwd).resolve(), "rev-parse", "--show-toplevel").strip()).resolve()
    state_path = _state_path(project_root, session_id)

    if event == "SessionStart":
        if payload.get("source") == "clear" and state_path.is_file():
            state_path.unlink()
            return _hook_output(
                event,
                "Senior Harness cleared the prior objective lock. The next user prompt will become the new primary objective.",
            )
        return _hook_output(
            event,
            "Senior Harness setup driver is active. The first user prompt will be frozen as the primary objective before mediated tools run.",
        )

    if event == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise SetupError(["UserPromptSubmit payload is missing the literal prompt"])
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            receipt = state.get("receipt", {})
            validate_startup_receipt(receipt, project=project_root, verify_repository=False)
            primary = receipt["setup_contract"]["literal_objective"]
            return _hook_output(
                event,
                f"Senior Harness primary objective remains frozen byte-for-byte: {primary!r}. Treat this prompt as a subordinate instruction unless the user starts a new task.",
            )
        contract = build_setup_contract(
            prompt,
            project_root,
            surface=surface,
            host_capabilities={
                "lifecycle_hooks": "configured",
                "pre_tool_use": "configured",
                "specialized_tool_interception": "unknown",
                "supports_parallel": False,
                "supports_model_override": False,
                "supports_cancellation": False,
                "evidence": f"project-{surface}-hook",
            },
        )
        receipt = admit_startup(contract)
        _write_state(state_path, {"receipt": receipt, "first_tool_admitted": False})
        return _hook_output(
            event,
            f"Senior Harness froze the primary objective: {prompt!r}. Load model-router and unlazy before substantive delivery. Startup admission grants no mutation, business, or irreversible authority.",
        )

    if not state_path.is_file():
        return _hook_output(event, "Senior Harness denied the tool: no startup receipt exists for this session.", deny=True)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        receipt = state.get("receipt", {})
        first_tool = not bool(state.get("first_tool_admitted"))
        validate_startup_receipt(receipt, project=project_root, verify_repository=first_tool)
        if first_tool:
            state["first_tool_admitted"] = True
            _write_state(state_path, state)
        primary = receipt["setup_contract"]["literal_objective"]
    except (OSError, json.JSONDecodeError, KeyError, SetupError) as exc:
        return _hook_output(event, f"Senior Harness denied the tool: invalid startup state ({exc}).", deny=True)
    return _hook_output(
        event,
        f"Senior Harness objective lock: {primary!r}. Startup admission does not authorize this tool; normal host and repository policy still decide it. This hook covers mediated local tools only; hosted or specialized bypasses are not claimed.",
    )


def guard_dispatch(
    delivery_contract: dict[str, Any],
    receipt: dict[str, Any],
    move_id: str,
    *,
    problem_id: str | None = None,
) -> dict[str, Any]:
    """Admit one nonmutating move after startup and anti-spin checks."""
    setup = receipt.get("setup_contract", {})
    validate_startup_receipt(
        receipt,
        literal_objective=delivery_contract.get("literal_request"),
        project=setup.get("repository", {}).get("worktree"),
    )
    validate_contract(delivery_contract)
    if delivery_contract.get("task_id") != setup.get("task_id"):
        raise SetupError(["delivery task id differs from the frozen startup task"])
    moves = {move["move_id"]: move for move in delivery_contract.get("move_graph", [])}
    move = moves.get(move_id)
    if not move:
        raise SetupError([f"unknown delivery move: {move_id}"])
    if move.get("kind") in MUTATING_KINDS:
        raise SetupError([f"startup admission cannot authorize mutating move {move_id}"])
    stopped = {
        case.get("problem_id")
        for case in delivery_contract.get("uncertainty_cases", [])
        if case.get("status") == "open" and case.get("stop_current_path") is True
    }
    move_problem = problem_id or move.get("problem_id")
    if move_problem and move_problem in stopped:
        raise SetupError([f"problem {move_problem} is stopped by an open uncertainty case"])
    if move_id not in ready_moves(delivery_contract):
        raise SetupError([f"move {move_id} is not dispatch-ready"])
    return {
        "status": "admitted",
        "move_id": move_id,
        "task_id": setup["task_id"],
        "mutation_authority": False,
    }


def _read_json(path: str) -> dict[str, Any]:
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError([f"unable to read JSON: {exc}"]) from exc
    if not isinstance(value, dict):
        raise SetupError(["top-level JSON must be an object"])
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze and verify Senior Harness startup admission.")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("objective")
    start.add_argument("--project", required=True)
    start.add_argument("--surface", choices=("codex", "claude", "vscode-openrouter"), required=True)
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
    hook = sub.add_parser("hook")
    hook.add_argument("--surface", choices=("codex", "claude"), required=True)
    hook.add_argument("--event", choices=("SessionStart", "UserPromptSubmit", "PreToolUse"), required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "start":
            contract = build_setup_contract(
                args.objective,
                args.project,
                surface=args.surface,
                strict_clean=args.strict_clean,
                skill_search_roots=args.skill_root,
            )
            result: Any = admit_startup(contract)
        elif args.command == "verify":
            result = validate_startup_receipt(
                _read_json(args.receipt), literal_objective=args.objective, project=args.project
            )
        elif args.command == "guard-dispatch":
            result = guard_dispatch(
                _read_json(args.contract),
                _read_json(args.receipt),
                args.move_id,
                problem_id=args.problem_id,
            )
        else:
            try:
                payload = json.load(sys.stdin)
            except (json.JSONDecodeError, OSError) as exc:
                result = _hook_output(args.event, f"Senior Harness rejected malformed hook input: {exc}", deny=True)
            else:
                try:
                    result = handle_hook(payload, surface=args.surface, event=args.event)
                except SetupError as exc:
                    result = _hook_output(args.event, f"Senior Harness rejected hook input: {'; '.join(exc.errors)}", deny=True)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (SetupError, ContractError) as exc:
        errors = exc.errors if hasattr(exc, "errors") else [str(exc)]
        print(json.dumps({"status": "invalid", "errors": errors}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
