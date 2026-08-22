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
import hmac
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
CANONICAL_REPO_ROOT = Path(__file__).resolve().parents[3]
for import_root in (SCRIPT_DIR, CANONICAL_REPO_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from app.server.task_routing import decide_route  # noqa: E402
from app.server.routing_schema import RoutingValidationError  # noqa: E402
from grill_session import (  # noqa: E402
    GrillSessionError,
    file_digest as grill_file_digest,
    validate_receipt as validate_grill_receipt,
    validate_session as validate_grill_session,
)
from senior_harness import ContractError, MUTATING_KINDS, digest, ready_moves, validate_contract  # noqa: E402


SETUP_SCHEMA_VERSION = "1.0"
REQUIRED_SKILLS = ("senior-harness", "model-router", "unlazy")
GRILL_INTERACTIONS = ("grill-me", "grill-with-docs")
SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
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
    ("diff", "--binary", "--no-ext-diff", "HEAD", "--"),
    ("ls-files", "--others", "--exclude-standard", "-z"),
}


def _surface_capabilities(surface: str, *, hooks_configured: bool) -> dict[str, Any]:
    """Declare only lifecycle capabilities backed by a configured host adapter."""
    if surface not in {"codex", "claude", "vscode-openrouter"}:
        raise SetupError([f"unsupported surface: {surface}"])
    lifecycle_state = "configured" if hooks_configured else "explicit-driver"
    adapter_evidence = {
        "codex": "codex-collaboration-spawn-and-interrupt",
        "claude": "claude-lifecycle-hooks-without-signed-dispatch-adapter",
        "vscode-openrouter": "no-probed-lifecycle-adapter",
    }
    # Claude's lifecycle hook can observe generic Agent calls but cannot attach
    # the signed Unlazy dispatch envelope required by the parallel root gate.
    # Advertising parallel capacity therefore deadlocks a fresh Claude delivery
    # session: the root is denied mutation and no admissible leaf can exist.
    lifecycle_parallel = hooks_configured and surface == "codex"
    return {
        "lifecycle_hooks": lifecycle_state,
        "pre_tool_use": lifecycle_state if hooks_configured else "explicit-driver",
        "specialized_tool_interception": "unknown",
        "supports_parallel": lifecycle_parallel,
        "supports_model_override": False,
        "supports_cancellation": lifecycle_parallel,
        "evidence": adapter_evidence[surface],
    }


class SetupError(ValueError):
    """Raised when startup cannot be admitted safely."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class ControlBindingResult:
    """Classify binding evidence without deriving policy from message text."""

    drift: tuple[str, ...] = ()
    integrity_failures: tuple[str, ...] = ()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _is_sha256_digest(value: Any) -> bool:
    return isinstance(value, str) and SHA256_DIGEST_PATTERN.fullmatch(value) is not None


def _interaction_for_objective(literal_objective: Any) -> str | None:
    if not isinstance(literal_objective, str) or not literal_objective.strip():
        return None
    match = re.match(
        r"^\s*[/\$](grill-with-docs|grill-me)",
        literal_objective,
        flags=re.IGNORECASE,
    )
    return match.group(1).lower() if match else "delivery"


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
    except (OSError, UnicodeDecodeError):
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
                Path.home() / ".agents" / "skills",
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
    dirty_hasher = hashlib.sha256()
    dirty_hasher.update(status.encode("utf-8"))
    dirty_hasher.update(_git(root, "diff", "--binary", "--no-ext-diff", "HEAD", "--").encode("utf-8"))
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    for relative in sorted(item for item in untracked if item):
        path = root / relative
        dirty_hasher.update(relative.encode("utf-8"))
        dirty_hasher.update(b"\0")
        if path.is_symlink():
            dirty_hasher.update(os.readlink(path).encode("utf-8"))
        elif path.is_file():
            dirty_hasher.update(path.read_bytes())
        dirty_hasher.update(b"\0")
    return {
        "worktree": str(root),
        "head_sha": head,
        "dirty": bool(status),
        "worktree_state_digest": "sha256:" + dirty_hasher.hexdigest(),
    }


def build_setup_contract(
    literal_objective: str,
    project: str | Path,
    *,
    surface: str,
    interaction: str = "delivery",
    strict_clean: bool = False,
    skill_search_roots: Iterable[str | Path] | None = None,
    host_capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze startup inputs without dispatching or mutating the project."""
    if not isinstance(literal_objective, str) or not literal_objective.strip():
        raise SetupError(["literal objective must be non-empty"])
    if surface not in {"codex", "claude", "vscode-openrouter"}:
        raise SetupError([f"unsupported surface: {surface}"])
    if interaction not in {"delivery", *GRILL_INTERACTIONS}:
        raise SetupError([f"unsupported interaction: {interaction}"])
    expected_interaction = _interaction_for_objective(literal_objective)
    if interaction != expected_interaction:
        raise SetupError(
            [
                "setup interaction does not match the frozen literal objective: "
                f"expected={expected_interaction}, observed={interaction}"
            ]
        )
    project_root = Path(project).resolve()
    search_roots = [Path(item).resolve() for item in skill_search_roots or ()]
    repository = _repository_snapshot(project_root, strict_clean=strict_clean)
    required_skill_names = REQUIRED_SKILLS + (("grill-me",) if interaction in GRILL_INTERACTIONS else ())
    skills = {
        name: _resolve_skill(name, project_root, search_roots)
        for name in required_skill_names
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
            "modalities": ["text"] if interaction in GRILL_INTERACTIONS else ["text", "code"],
            "required_tools": ["read", "research"] if interaction in GRILL_INTERACTIONS else ["read", "edit", "test"],
            "sensitivity": "internal",
            "prior_failures": 0,
            # Startup has not run Unlazy yet, so disjoint ownership is not a
            # fact the router may assume. The orchestration policy below makes
            # decomposition-before-root-implementation mandatory.
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
        "interaction": interaction,
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
        "orchestration_policy": {
            "parallel_required": (
                interaction == "delivery"
                and capabilities.get("supports_parallel") is True
                and capabilities.get("supports_cancellation") is True
            ),
            "max_parallel_workers": 4,
            "requires_disjoint_ownership_proof": True,
            "root_mutation_authority": False,
        },
        "secondary_objectives": [],
        "authority": dict(STARTUP_AUTHORITY),
    }
    contract["setup_contract_digest"] = digest(contract)
    return contract


SEAL_PREFIX = "hmac-sha256:"
SEAL_KEY_ENV = "SENIOR_HARNESS_SEAL_KEY_FILE"


def _seal_key_path() -> Path:
    """Where the seal key lives — deliberately NOT under the state root.

    The state root is the surface an attacker in this threat model already
    controls. A key stored beside the state file would be readable by exactly
    whoever we are defending against, so the key lives under a separate config
    root instead.
    """
    override = os.environ.get(SEAL_KEY_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "senior-harness" / "receipt-seal.key"


def _seal_key() -> bytes:
    """Read the machine-local seal key, creating it 0600 on first use."""
    path = _seal_key_path()
    try:
        existing = path.read_bytes()
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise SetupError([f"startup receipt seal key cannot be read: {exc}"]) from exc
    if existing is not None:
        if len(existing) < 32:
            raise SetupError([f"startup receipt seal key is too short: {path}"])
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    key = os.urandom(32)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Another process won the create race; its key is authoritative.
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise SetupError([f"startup receipt seal key cannot be read after creation race: {exc}"]) from exc
        if len(existing) < 32:
            raise SetupError([f"startup receipt seal key is too short: {path}"])
        return existing
    try:
        os.write(descriptor, key)
    finally:
        os.close(descriptor)
    return key


def _receipt_seal(receipt: Any) -> str:
    """HMAC the receipt with a key the state-file holder cannot recompute.

    Every other digest on the receipt is derived FROM the receipt by a public
    function, so a holder of the state file can rewrite any field and recompute
    all of them. Review round 1 confirmed that by execution: re-deriving every
    objective-driven field converted a grill session to delivery and admitted
    Write. The seal is the one value that cannot be regenerated from the file
    alone.

    Bounded claim, stated precisely: this does not make the receipt
    unforgeable by any local process — a process that reads the key file can
    still forge one. It removes forgery-by-recomputation, which is the confirmed
    attack, and forces an attacker to reach a second, separately-located secret.
    """
    unsealed = {key: value for key, value in dict(receipt).items() if key != "receipt_seal"}
    payload = json.dumps(
        unsealed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return SEAL_PREFIX + hmac.new(_seal_key(), payload, hashlib.sha256).hexdigest()


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
    expected_interaction = _interaction_for_objective(objective)
    if contract.get("interaction") != expected_interaction:
        raise SetupError(["setup contract interaction does not match its frozen literal objective"])
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
    receipt["receipt_seal"] = _receipt_seal(receipt)
    return receipt


def _check_control_bindings(
    receipt: Any,
    *,
    verify_current: bool = True,
) -> ControlBindingResult:
    """Validate binding evidence and structurally separate drift from integrity failure."""
    drift: list[str] = []
    integrity_failures: list[str] = []
    if not isinstance(receipt, dict):
        return ControlBindingResult(integrity_failures=("startup receipt must be a JSON object",))
    contract = receipt.get("setup_contract")
    if not isinstance(contract, dict):
        return ControlBindingResult(integrity_failures=("startup receipt is missing its setup contract",))
    skills = contract.get("required_skills")
    if not isinstance(skills, dict):
        return ControlBindingResult(integrity_failures=("startup receipt has no required-skill evidence",))
    expected_interaction = _interaction_for_objective(contract.get("literal_objective"))
    required_skill_names = REQUIRED_SKILLS + (
        ("grill-me",) if expected_interaction in GRILL_INTERACTIONS else ()
    )
    for name in required_skill_names:
        item = skills.get(name)
        if not isinstance(item, dict):
            integrity_failures.append(f"startup receipt is missing skill {name}")
            continue
        if item.get("name") != name:
            integrity_failures.append(f"bound skill name is missing or invalid: {name}")
        path_value = item.get("path")
        path: Path | None = None
        if not isinstance(path_value, str) or not path_value or not Path(path_value).is_absolute():
            integrity_failures.append(f"bound skill path is missing or invalid: {name}")
        else:
            path = Path(path_value)
        stored_digest = item.get("folder_digest")
        digest_valid = _is_sha256_digest(stored_digest)
        if not digest_valid:
            integrity_failures.append(f"bound skill folder digest is missing or malformed: {name}")
        if not verify_current or path is None:
            continue
        try:
            skill_valid = path.is_dir() and _frontmatter_name(path / "SKILL.md") == name
        except OSError:
            skill_valid = False
        if not skill_valid:
            integrity_failures.append(f"bound skill is unavailable or invalid: {name}")
            continue
        if digest_valid:
            try:
                current_digest = _folder_digest(path)
            except OSError:
                integrity_failures.append(f"bound skill is unavailable or invalid: {name}")
            else:
                if stored_digest != current_digest:
                    drift.append(f"bound skill changed after startup admission: {name}")
    stored_driver_digest = receipt.get("driver_digest")
    if not _is_sha256_digest(stored_driver_digest):
        integrity_failures.append("setup driver digest is missing or malformed")
    elif verify_current:
        try:
            current_driver_digest = _file_digest(Path(__file__).resolve())
        except OSError:
            integrity_failures.append("setup driver is unavailable or invalid")
        else:
            if stored_driver_digest != current_driver_digest:
                drift.append("setup driver changed after startup admission")
    return ControlBindingResult(
        drift=tuple(drift),
        integrity_failures=tuple(integrity_failures),
    )


def _control_binding_errors(receipt: dict[str, Any]) -> list[str]:
    """Return all installed control-binding failures for compatibility and reporting."""
    result = _check_control_bindings(receipt)
    return [*result.integrity_failures, *result.drift]


def validate_startup_receipt(
    receipt: dict[str, Any],
    *,
    literal_objective: str | None = None,
    project: str | Path | None = None,
    verify_repository: bool = True,
    verify_control_bindings: bool = True,
) -> dict[str, Any]:
    """Re-probe all bound local evidence and reject stale or altered receipts."""
    if not isinstance(receipt, dict):
        raise SetupError(["startup receipt must be a JSON object"])
    errors: list[str] = []
    # The seal is checked first and with hmac.compare_digest, because it is the
    # only field on the receipt that a holder of the state file cannot recompute.
    # Every check below it compares a public digest against a public function and
    # therefore survives a consistent re-forge on its own.
    #
    # PAIRING, load-bearing: a receipt issued by an older driver has no seal and
    # can never gain one, so this check alone would strand every in-flight session
    # on the machine — observed for real on 2026-08-22. What makes it survivable is
    # the re-admission path in handle_hook's UserPromptSubmit branch, which
    # replaces an unverifiable prior receipt from the next prompt instead of
    # propagating the failure. Never add a receipt requirement here without that
    # path; `test_a_receipt_from_an_older_driver_heals_on_the_next_prompt` pins it.
    observed_seal = receipt.get("receipt_seal")
    if not isinstance(observed_seal, str) or not observed_seal.startswith(SEAL_PREFIX):
        errors.append("startup receipt seal is missing or malformed")
    elif not hmac.compare_digest(observed_seal, _receipt_seal(receipt)):
        errors.append("startup receipt seal does not match this machine's harness key")
    candidate = {key: value for key, value in receipt.items() if key != "receipt_seal"}
    observed_digest = candidate.pop("receipt_integrity_digest", None)
    if not _is_sha256_digest(observed_digest):
        errors.append("startup receipt integrity digest is missing or malformed")
    elif observed_digest != digest(candidate):
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
    if not _is_sha256_digest(embedded_digest):
        errors.append("embedded setup contract digest is missing or malformed")
    elif embedded_digest != digest(embedded):
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
    interaction = contract.get("interaction")
    if interaction not in {"delivery", *GRILL_INTERACTIONS}:
        errors.append("embedded setup contract interaction is invalid")
    expected_interaction = _interaction_for_objective(objective)
    if expected_interaction is not None and interaction != expected_interaction:
        errors.append("embedded setup contract interaction does not match the frozen literal objective")
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
    repository_value = contract.get("repository")
    if not isinstance(repository_value, dict):
        errors.append("embedded setup contract repository is invalid")
        repository: dict[str, Any] = {}
    else:
        repository = repository_value
    worktree = repository.get("worktree")
    worktree_valid = isinstance(worktree, str) and bool(worktree) and Path(worktree).is_absolute()
    if not worktree_valid:
        errors.append("repository worktree path is missing or invalid")
    if not isinstance(repository.get("head_sha"), str) or GIT_SHA_PATTERN.fullmatch(repository["head_sha"]) is None:
        errors.append("repository head SHA is missing or malformed")
    if not isinstance(repository.get("dirty"), bool):
        errors.append("repository dirty flag is invalid")
    if not _is_sha256_digest(repository.get("worktree_state_digest")):
        errors.append("repository state digest is missing or malformed")
    if verify_repository:
        bound_project_value = project if project is not None else worktree
        if bound_project_value is not None and (project is not None or worktree_valid):
            try:
                bound_project = Path(bound_project_value).resolve()
                current = _repository_snapshot(bound_project, strict_clean=False)
            except (OSError, TypeError, SetupError) as exc:
                errors.extend(exc.errors if isinstance(exc, SetupError) else [f"repository path is invalid: {exc}"])
                current = {}
            for field in ("worktree", "head_sha", "dirty", "worktree_state_digest"):
                if repository.get(field) != current.get(field):
                    errors.append(f"repository {field} changed after startup admission")
    binding_result = _check_control_bindings(receipt, verify_current=verify_control_bindings)
    errors.extend(binding_result.integrity_failures)
    if verify_control_bindings:
        errors.extend(binding_result.drift)
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


def _normalise_tool_name(raw_name: Any) -> str:
    """Map host tool labels to the portable snake_case control vocabulary."""
    if isinstance(raw_name, dict):
        raw_name = raw_name.get("name", "")
    name = str(raw_name).replace("-", "_").replace(".", "_")
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


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
    """Allow only exact host orchestration controls on a parallel-required root."""
    raw_name = payload.get("tool_name") or payload.get("tool") or ""
    name = _normalise_tool_name(raw_name)
    return name in {
        "wait_agent",
        "list_agents",
        "interrupt_agent",
        "send_message",
        "update_plan",
        "get_goal",
    }


def _is_parallel_dispatch_tool(payload: dict[str, Any]) -> bool:
    """Identify dispatch controls that require an independently signed admission.

    Generic host labels such as ``spawn_agent`` are intentionally not treated as
    proof of Unlazy admission.  The signed control-plane wrapper owns dispatch;
    this hook only recognises its exact event name so an unwrapped root cannot
    turn a tool label into mutation authority.
    """
    raw_name = payload.get("tool_name") or payload.get("tool") or ""
    return _normalise_tool_name(raw_name) == "senior_harness_dispatch"


def _has_signed_dispatch_admission(
    payload: dict[str, Any], project_root: Path, current_receipt: dict[str, Any]
) -> bool:
    """Ask the signed Unlazy control plane to admit this exact dispatch.

    The hook never trusts a model-supplied ``admitted: true`` field.  The
    wrapper must provide the bound receipt/plan/route/state files, and the
    control plane revalidates their exact SHA/HMAC and atomically reserves the
    leaf before this hook permits the host event.
    """
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return False
    required = ("receipt_path", "plan_path", "routing_request_path", "state_path", "node_id", "worker_context_id")
    if any(not isinstance(tool_input.get(key), str) or not tool_input[key] for key in required):
        return False
    try:
        from control_plane import authorize_event  # imported lazily to avoid module-load cycles

        receipt = _read_json(tool_input["receipt_path"])
        current_contract = current_receipt.get("setup_contract", {})
        supplied_contract = receipt.get("setup_contract", {})
        if not isinstance(current_contract, dict) or not isinstance(supplied_contract, dict):
            return False
        # A valid receipt for another objective in this checkout cannot be
        # replayed into the current session. Bind the proof before asking the
        # control plane to reserve any leaf.
        if any(
            supplied_contract.get(field) != current_contract.get(field)
            for field in ("literal_objective", "task_id", "setup_contract_digest")
        ) or receipt.get("receipt_seal") != current_receipt.get("receipt_seal"):
            return False
        supplied_worktree = Path(
            str(supplied_contract.get("repository", {}).get("worktree", ""))
        ).expanduser().resolve()
        if supplied_worktree != project_root.resolve():
            return False
        plan = _read_json(tool_input["plan_path"])
        route = _read_json(tool_input["routing_request_path"])
        result = authorize_event(
            receipt,
            plan,
            route,
            {"tool_name": "senior-harness.dispatch", "tool_input": tool_input},
            state_path=tool_input["state_path"],
        )
        return result.get("status") == "admitted"
    except (OSError, ValueError, KeyError, TypeError, SetupError):
        return False


def _safe_repo_argument(token: str) -> bool:
    """Accept only simple repository-relative verification paths."""
    if not token or token.startswith(("-", "/")) or any(char in token for char in "{}[]*?"):
        return False
    return ".." not in Path(token).parts


def _safe_test_argument(token: str, payload: dict[str, Any]) -> bool:
    """Resolve a test selector and keep it under the real checkout tests tree."""
    if not _safe_repo_argument(token):
        return False
    raw_input = payload.get("tool_input")
    if not isinstance(raw_input, dict):
        raw_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    raw_cwd = payload.get("cwd") or "."
    requested_workdir = raw_input.get("workdir")
    if requested_workdir is not None:
        try:
            if Path(str(requested_workdir)).expanduser().resolve() != Path(str(raw_cwd)).expanduser().resolve():
                return False
        except OSError:
            return False
    try:
        checkout = Path(str(raw_cwd)).expanduser().resolve()
        candidate = (checkout / token.split("::", 1)[0]).resolve()
        candidate.relative_to((checkout / "tests").resolve())
    except (OSError, ValueError):
        return False
    return True


def _is_parallel_verification_tool(payload: dict[str, Any]) -> bool:
    """Permit narrowly bounded, read-only proof commands while denying writes."""
    raw_name = payload.get("tool_name") or payload.get("tool") or ""
    name = _normalise_tool_name(raw_name)
    if not any(marker in name for marker in ("bash", "exec", "command", "shell")):
        return False
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    command = tool_input.get("cmd") or tool_input.get("command")
    if not isinstance(command, str) or not command.strip() or re.search(r"[\n;&|<>`]|\$\(", command):
        return False
    requested_workdir = tool_input.get("workdir")
    if requested_workdir is not None:
        bound_cwd = payload.get("cwd")
        if not isinstance(bound_cwd, str) or not bound_cwd:
            return False
        try:
            if Path(str(requested_workdir)).expanduser().resolve() != Path(bound_cwd).expanduser().resolve():
                return False
        except OSError:
            return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if not argv:
        return False
    executable = Path(argv[0]).name
    if argv[0] != executable:
        return False
    if executable == "pytest":
        # Pytest is admitted only for the repository's own tests.  In
        # particular, reject arbitrary paths, plugins, output files, basetemp,
        # pdb/trace hooks, and every option that can redirect or write output.
        allowed_options = {"-q", "-x", "-v", "-vv", "--disable-warnings", "--tb=short", "--tb=long"}
        for token in argv[1:]:
            if token.startswith("-"):
                if token not in allowed_options:
                    return False
            elif not _safe_test_argument(token, payload):
                return False
        return True
    if executable == "ruff":
        # Only the non-mutating checker is allowed.  ``format`` and every fix,
        # output, or config-redirection flag stay behind the root deny.
        if len(argv) < 2 or argv[1] != "check":
            return False
        for token in argv[2:]:
            if token.startswith("-") or not _safe_repo_argument(token):
                return False
        return True
    if executable in {"mypy", "pyright"}:
        return all(_safe_repo_argument(token) for token in argv[1:])
    return False


def _state_path(project_root: Path, session_id: str) -> Path:
    if not session_id:
        raise SetupError(["hook payload has no usable session id"])
    override = os.environ.get("SENIOR_HARNESS_STATE_DIR")
    root = Path(override).resolve() if override else Path.home() / ".local" / "state" / "senior-harness" / "sessions"
    project_key = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:20]
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return root / project_key / f"{session_key}.json"


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _tool_is_recovery_safe(payload: dict[str, Any]) -> bool:
    """Recognise exact read-only discovery tools; never infer safety from a substring."""
    raw_name = payload.get("tool_name") or payload.get("tool") or ""
    tool_name = _normalise_tool_name(raw_name)
    safe_names = {
        "read",
        "grep",
        "glob",
        "webfetch",
        "web_fetch",
        "websearch",
        "web_search",
        "toolsearch",
        "tool_search",
        "web__run",
        "view_image",
        "list_mcp_resources",
        "list_mcp_resource_templates",
        "read_mcp_resource",
        "request_user_input",
    }
    if tool_name in safe_names:
        return True
    read_only_exa_tools = {
        "mcp__exa__web_search_exa",
        "mcp__exa__get_code_context_exa",
        "mcp__exa__research_paper",
        "mcp__exa__company_research_exa",
        "mcp__exa__people_search_exa",
        "mcp__exa__crawling_exa",
        "mcp__plugin_exa_exa__web_search_exa",
        "mcp__plugin_exa_exa__get_code_context_exa",
        "mcp__plugin_exa_exa__research_paper",
        "mcp__plugin_exa_exa__company_research_exa",
        "mcp__plugin_exa_exa__people_search_exa",
        "mcp__plugin_exa_exa__crawling_exa",
    }
    if tool_name in read_only_exa_tools:
        return True
    if not any(marker in tool_name for marker in ("bash", "exec", "command", "shell")):
        return False
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    command = tool_input.get("cmd") or tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return False
    if re.search(r"[\n;&|<>`]|\$\(", command):
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if not argv or any(token in {"&&", "||", ";", "|", ">", ">>", "<"} for token in argv):
        return False
    executable = Path(argv[0]).name
    if executable in {"python", "python3"}:
        if len(argv) < 2:
            return False
        script = Path(os.path.expandvars(argv[1])).expanduser().resolve()
        return script == (SCRIPT_DIR / "grill_session.py").resolve()
    if executable == "git":
        args = argv[1:]
        while len(args) >= 2 and args[0] == "-C":
            args = args[2:]
        unsafe_git = ("--config", "--exec", "--ext-diff", "--output", "--paginate", "--textconv")
        return (
            bool(args)
            and args[0] in {"diff", "grep", "log", "ls-files", "rev-parse", "show", "status"}
            and not any(any(arg == token or arg.startswith(token + "=") for token in unsafe_git) for arg in args)
        )
    if executable == "find" and any(arg in {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint"} for arg in argv):
        return False
    if executable == "rg" and any(arg == "--pre" or arg.startswith("--pre=") for arg in argv[1:]):
        return False
    return executable in {"file", "find", "head", "ls", "pwd", "rg", "stat", "tail", "wc"}


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
            # A prior receipt that cannot be verified must NOT strand the session.
            # A prompt is the one moment a fresh admission can legitimately be
            # issued, so an unverifiable receipt falls through to re-admission
            # below instead of propagating and denying every subsequent tool.
            #
            # This is the recovery path for a receipt issued by an OLDER driver —
            # e.g. one predating the receipt seal, which has no seal field and can
            # never satisfy the check no matter how many prompts arrive. Without
            # this, shipping any new receipt requirement instantly denies every
            # in-flight session on the machine with no way back. That failure was
            # observed for real on 2026-08-22 and is what this branch prevents.
            #
            # Re-admission grants nothing: the new receipt is bound to the current
            # prompt, the current checkout and the current control digests, and
            # carries the same zero-authority admission block as any other. The
            # cost is that a party who can corrupt the state file can force the
            # objective lock to be re-taken from the next prompt — strictly less
            # power than the tool denial it replaces, and they must already be able
            # to write the state root to try it.
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if not isinstance(state, dict):
                    raise SetupError(["startup state must be a JSON object"])
                receipt = state.get("receipt", {})
                validate_startup_receipt(
                    receipt,
                    project=project_root,
                    verify_repository=False,
                    verify_control_bindings=False,
                )
                primary = receipt["setup_contract"]["literal_objective"]
                parallel_context = _parallel_dispatch_context(receipt["setup_contract"])
                binding_result = _check_control_bindings(receipt)
                if binding_result.integrity_failures:
                    raise SetupError([*binding_result.integrity_failures, *binding_result.drift])
                control_drift = binding_result.drift
            except (OSError, json.JSONDecodeError, KeyError, TypeError, SetupError):
                control_drift = None  # signal: re-admit from this prompt
            if control_drift is not None:
                drift_context = (
                    " Control-code drift is present and must be revalidated in a fresh session: "
                    + "; ".join(control_drift)
                    + "."
                    if control_drift
                    else ""
                )
                return _hook_output(
                    event,
                    f"Senior Harness primary objective remains frozen byte-for-byte: {primary!r}. Treat this prompt as a subordinate instruction unless the user starts a new task.{parallel_context}{drift_context}",
                )
        interaction = _interaction_for_objective(prompt)
        if interaction is None:
            raise SetupError(["UserPromptSubmit payload is missing the literal prompt"])
        contract = build_setup_contract(
            prompt,
            project_root,
            surface=surface,
            interaction=interaction,
            host_capabilities=_surface_capabilities(surface, hooks_configured=True),
        )
        receipt = admit_startup(contract)
        _write_state(state_path, {"receipt": receipt, "first_tool_admitted": False})
        grill_context = (
            " Grill interaction is active: use the governed Grill session controller; project mutation and worker dispatch remain denied until its shared-understanding receipt validates."
            if interaction in GRILL_INTERACTIONS
            else ""
        )
        return _hook_output(
            event,
            f"Senior Harness froze the primary objective: {prompt!r}. Load model-router and unlazy before substantive delivery.{_parallel_dispatch_context(contract)} Startup admission grants no mutation, business, or irreversible authority.{grill_context}",
        )

    recovery_safe = _tool_is_recovery_safe(payload)
    if not state_path.is_file():
        if recovery_safe:
            return _hook_output(
                event,
                "Senior Harness recovery-only read: no startup receipt exists for this session. This permits evidence discovery only and grants no mutation, provider, worker, business, or irreversible authority.",
            )
        return _hook_output(event, "Senior Harness denied the tool: no startup receipt exists for this session.", deny=True)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise SetupError(["startup state must be a JSON object"])
        receipt = state.get("receipt", {})
        if not isinstance(receipt, dict):
            raise SetupError(["startup state receipt must be a JSON object"])
        first_tool_admitted = state.get("first_tool_admitted")
        if not isinstance(first_tool_admitted, bool):
            raise SetupError(["startup state first_tool_admitted flag is invalid"])
        first_tool = not first_tool_admitted
        contract = receipt.get("setup_contract")
        if not isinstance(contract, dict):
            raise SetupError(["startup receipt is missing its setup contract"])
        interaction = contract.get("interaction")
        strict_bindings = interaction in GRILL_INTERACTIONS
        validate_startup_receipt(
            receipt,
            project=project_root,
            verify_repository=first_tool or interaction in GRILL_INTERACTIONS,
            verify_control_bindings=False,
        )
        binding_result = _check_control_bindings(receipt)
        if binding_result.integrity_failures:
            raise SetupError([*binding_result.integrity_failures, *binding_result.drift])
        control_drift = binding_result.drift
        if control_drift and (first_tool or strict_bindings):
            raise SetupError(list(control_drift))
        if first_tool:
            state["first_tool_admitted"] = True
            _write_state(state_path, state)
        primary = receipt["setup_contract"]["literal_objective"]
        parallel_context = _parallel_dispatch_context(receipt["setup_contract"])
    except (OSError, json.JSONDecodeError, KeyError, SetupError) as exc:
        if recovery_safe:
            return _hook_output(
                event,
                f"Senior Harness recovery-only read: startup state is invalid ({exc}). This permits evidence discovery only and grants no mutation, provider, worker, business, or irreversible authority.",
            )
        return _hook_output(event, f"Senior Harness denied the tool: invalid startup state ({exc}).", deny=True)
    if interaction in GRILL_INTERACTIONS and not recovery_safe:
        return _hook_output(
            event,
            "Senior Harness denied the tool: Grill-Me permits evidence discovery and its control-state driver only until shared understanding is explicitly confirmed.",
            deny=True,
        )
    policy = receipt["setup_contract"].get("orchestration_policy", {})
    dispatch_admitted = _is_parallel_dispatch_tool(payload) and _has_signed_dispatch_admission(
        payload, project_root, receipt
    )
    if (
        isinstance(policy, dict)
        and policy.get("parallel_required") is True
        and not recovery_safe
        and not _is_parallel_control_tool(payload)
        and not dispatch_admitted
        and not _is_parallel_verification_tool(payload)
    ):
        reason = (
            "Senior Harness denied dispatch: generic agent spawning is not Unlazy admission; use the signed "
            "senior-harness.dispatch control wrapper with a bound receipt, plan, route, and state path."
            if _is_parallel_dispatch_tool(payload)
            else "Senior Harness denied root implementation: this parallel-required root may coordinate, read, dispatch, wait, and verify, but every mutation must be owned by a bounded leaf or integration worker."
        )
        return _hook_output(
            event,
            reason,
            deny=True,
        )
    drift_context = ""
    if control_drift:
        drift_context = (
            " Senior Harness control-code drift detected: "
            + "; ".join(control_drift)
            + ". Delivery may continue under normal host and repository policy, but this startup receipt cannot be reused as fresh control-code evidence."
        )
    return _hook_output(
        event,
        f"Senior Harness objective lock: {primary!r}.{parallel_context} Startup admission does not authorize this tool; normal host and repository policy still decide it. This hook covers mediated local tools only; hosted or specialized bypasses are not claimed.{drift_context}",
    )


def guard_dispatch(
    delivery_contract: dict[str, Any],
    receipt: dict[str, Any],
    move_id: str,
    *,
    problem_id: str | None = None,
    grill_session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Admit one nonmutating move after startup and anti-spin checks."""
    setup = receipt.get("setup_contract", {})
    validate_startup_receipt(
        receipt,
        literal_objective=delivery_contract.get("literal_request"),
        project=setup.get("repository", {}).get("worktree"),
    )
    if setup.get("interaction") in GRILL_INTERACTIONS:
        if not isinstance(grill_session, dict):
            raise SetupError(["Grill delivery remains stopped until a shared-understanding session is supplied"])
        if grill_session.get("state") != "confirmed":
            raise SetupError(["Grill delivery remains stopped until shared understanding is confirmed"])
        try:
            validate_grill_session(grill_session)
            validate_grill_receipt(grill_session.get("receipt", {}))
        except GrillSessionError as exc:
            raise SetupError([f"invalid Grill shared-understanding session: {exc}"]) from exc
        if grill_session.get("objective") != setup.get("literal_objective"):
            raise SetupError(["Grill objective differs from the frozen startup objective"])
        sketch = grill_session.get("sketch", {})
        sketch_path = Path(str(sketch.get("path", "")))
        if not sketch_path.is_file() or sketch.get("sha256") != grill_file_digest(sketch_path):
            raise SetupError(["Grill sketch changed after shared understanding was confirmed"])
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
    hook.add_argument("--event", choices=("SessionStart", "UserPromptSubmit", "PreToolUse"), required=True)
    hook.add_argument("--allow-non-git", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "start":
            contract = build_setup_contract(
                args.objective,
                args.project,
                surface=args.surface,
                interaction=args.interaction,
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
                grill_session=_read_json(args.grill_session) if args.grill_session else None,
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
                    outside_git = args.allow_non_git and any(
                        error.startswith("git probe failed for") for error in exc.errors
                    )
                    if outside_git:
                        result = _hook_output(
                            args.event,
                            "Senior Harness global hook is inactive because this task is outside a Git project. No admission or authority claim was made.",
                        )
                    else:
                        result = _hook_output(
                            args.event,
                            f"Senior Harness rejected hook input: {'; '.join(exc.errors)}",
                            deny=True,
                        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (SetupError, ContractError) as exc:
        errors = exc.errors if hasattr(exc, "errors") else [str(exc)]
        print(json.dumps({"status": "invalid", "errors": errors}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
