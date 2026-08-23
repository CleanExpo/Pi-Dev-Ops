"""Repository, skill, host-capability, and routing intake for startup admission."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable

from app.server.task_routing import decide_route
from senior_harness import digest
from setup_common import (
    ADAPTER_RECEIPT_ENV,
    GRILL_INTERACTIONS,
    READ_ONLY_GIT,
    REQUIRED_ADAPTER_EVIDENCE,
    REQUIRED_SKILLS,
    SETUP_SCHEMA_VERSION,
    STARTUP_AUTHORITY,
    GitProbeError,
    SetupError,
    _folder_digest,
    _interaction_for_objective,
)


def _read_adapter_receipt(surface: str) -> dict[str, Any] | None:
    """Return structurally valid observed-adapter evidence, or fail closed."""
    raw_path = os.environ.get(ADAPTER_RECEIPT_ENV, "").strip()
    if not raw_path:
        return None
    try:
        payload = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("surface") != surface:
        return None
    if any(payload.get(name) is not True for name in REQUIRED_ADAPTER_EVIDENCE):
        return None
    signature = payload.get("adapter_signature")
    if not isinstance(signature, str) or not signature.strip():
        return None
    return payload


def _surface_capabilities(
    surface: str, *, hooks_configured: bool,
    adapter_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Declare only lifecycle capabilities backed by observed adapter evidence."""
    if surface not in {"codex", "claude", "vscode-openrouter"}:
        raise SetupError([f"unsupported surface: {surface}"])
    lifecycle_state = "configured" if hooks_configured else "explicit-driver"
    adapter_evidence = {
        "codex": "codex-collaboration-spawn-and-interrupt",
        "claude": "claude-lifecycle-hooks-without-signed-dispatch-adapter",
        "vscode-openrouter": "no-probed-lifecycle-adapter",
    }
    probed = adapter_receipt is not None
    lifecycle_parallel = hooks_configured and surface == "codex" and probed
    return {
        "lifecycle_hooks": lifecycle_state,
        "pre_tool_use": lifecycle_state if hooks_configured else "explicit-driver",
        "specialized_tool_interception": "unknown",
        "supports_parallel": lifecycle_parallel,
        "supports_model_override": False,
        "supports_cancellation": lifecycle_parallel,
        "capability_probe": "observed-adapter-receipt" if probed else "unprobed",
        "evidence": adapter_evidence[surface],
    }


def _git(project: Path, *args: str) -> str:
    if tuple(args) not in READ_ONLY_GIT:
        raise SetupError([f"setup driver refused non-read-only git probe: {' '.join(args)}"])
    try:
        result = subprocess.run(
            ["git", "-C", str(project), *args], check=True, capture_output=True,
            text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitProbeError([f"git probe failed for {project}: {exc}"]) from exc
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


def _candidate_skill_dirs(
    name: str, project_root: Path, search_roots: Iterable[Path] | None
) -> list[Path]:
    roots = list(search_roots or ())
    if not roots:
        roots.extend([
            project_root / "skills", Path.home() / ".codex" / "skills",
            Path.home() / ".claude" / "skills", Path.home() / ".agents" / "skills",
        ])
    candidates: list[Path] = []
    for root in roots:
        candidate = root if root.name == name else root / name
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _resolve_skill(
    name: str, project_root: Path, search_roots: Iterable[Path] | None
) -> dict[str, str]:
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
        return {"name": name, "path": str(resolved), "folder_digest": _folder_digest(resolved)}
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
    dirty_hasher.update(status.encode())
    dirty_hasher.update(_git(root, "diff", "--binary", "--no-ext-diff", "HEAD", "--").encode())
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    for relative in sorted(item for item in untracked if item):
        path = root / relative
        dirty_hasher.update(relative.encode() + b"\0")
        if path.is_symlink():
            dirty_hasher.update(os.readlink(path).encode())
        elif path.is_file():
            dirty_hasher.update(path.read_bytes())
        dirty_hasher.update(b"\0")
    return {
        "worktree": str(root), "head_sha": head, "dirty": bool(status),
        "worktree_state_digest": "sha256:" + dirty_hasher.hexdigest(),
    }


def _routing_request(
    objective: str, repository: dict[str, Any], surface: str,
    interaction: str, capabilities: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "request_id": digest({
            "objective": objective, "worktree": repository["worktree"],
            "head_sha": repository["head_sha"], "surface": surface,
        })[7:39],
        "task": objective,
        "harness": "claude-code" if surface == "claude" else surface,
        "signals": {
            "determinism": "medium", "ambiguity": "high", "scope": "project",
            "dependency_count": 2, "reasoning_depth": "deep", "stakes": ["none"],
            "volume": 3, "expected_minutes": 180, "context_tokens_estimate": 12000,
            "modalities": ["text"] if interaction in GRILL_INTERACTIONS else ["text", "code"],
            "required_tools": ["read", "research"] if interaction in GRILL_INTERACTIONS else ["read", "edit", "test"],
            "sensitivity": "internal", "prior_failures": 0, "ownership_disjoint": False,
        },
        "limits": {
            "max_cost_usd": None, "max_quota_units": None,
            "deadline_seconds": 1800, "max_parallel_workers": 4,
        },
        "capabilities": {
            "local_quality_floors": list(capabilities.get("local_quality_floors", [])),
            "supports_parallel": capabilities.get("supports_parallel") is True,
            "supports_model_override": capabilities.get("supports_model_override") is True,
            "supports_cancellation": capabilities.get("supports_cancellation") is True,
        },
    }


def _default_capabilities() -> dict[str, str]:
    return {
        "lifecycle_hooks": "unknown", "pre_tool_use": "unknown",
        "specialized_tool_interception": "unknown", "evidence": "not-probed",
    }


def build_setup_contract(
    literal_objective: str, project: str | Path, *, surface: str,
    interaction: str = "delivery", strict_clean: bool = False,
    skill_search_roots: Iterable[str | Path] | None = None,
    host_capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(literal_objective, str) or not literal_objective.strip():
        raise SetupError(["literal objective must be non-empty"])
    if surface not in {"codex", "claude", "vscode-openrouter"}:
        raise SetupError([f"unsupported surface: {surface}"])
    if interaction not in {"delivery", *GRILL_INTERACTIONS}:
        raise SetupError([f"unsupported interaction: {interaction}"])
    expected = _interaction_for_objective(literal_objective)
    if interaction != expected:
        raise SetupError([f"setup interaction does not match the frozen literal objective: expected={expected}, observed={interaction}"])
    project_root = Path(project).resolve()
    roots = [Path(item).resolve() for item in skill_search_roots or ()]
    repository = _repository_snapshot(project_root, strict_clean=strict_clean)
    capabilities = host_capabilities or _default_capabilities()
    return _assemble_contract(literal_objective, surface, interaction, repository, roots, capabilities)


def _assemble_contract(
    objective: str, surface: str, interaction: str, repository: dict[str, Any],
    roots: list[Path], capabilities: dict[str, Any],
) -> dict[str, Any]:
    skill_names = REQUIRED_SKILLS + (("grill-me",) if interaction in GRILL_INTERACTIONS else ())
    skills = {name: _resolve_skill(name, Path(repository["worktree"]), roots) for name in skill_names}
    routing_request = _routing_request(objective, repository, surface, interaction, capabilities)
    contract: dict[str, Any] = {
        "schema_version": SETUP_SCHEMA_VERSION, "stage": "setup-contract",
        "literal_objective": objective, "task_id": digest({"task": objective})[7:23],
        "objective_digest": digest({"task": objective}), "surface": surface,
        "interaction": interaction, "repository": repository, "required_skills": skills,
        "host_capabilities": capabilities, "routing_request": routing_request,
        "route_decision": decide_route(routing_request).to_dict(),
        "delivery_controller": {
            "skill_id": "unlazy", "required": True,
            "owns": ["decomposition", "leaf-gates", "integration-gates", "exact-candidate-receipts"],
            "dispatch_after": "valid-delivery-contract-and-guard-dispatch",
        },
        "orchestration_policy": {
            "parallel_required": interaction == "delivery" and capabilities.get("supports_parallel") is True and capabilities.get("supports_cancellation") is True,
            "max_parallel_workers": 4, "requires_disjoint_ownership_proof": True,
            "root_mutation_authority": False,
        },
        "secondary_objectives": [], "authority": dict(STARTUP_AUTHORITY),
    }
    contract["setup_contract_digest"] = digest(contract)
    return contract
